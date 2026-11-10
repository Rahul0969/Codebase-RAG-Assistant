"""Tests for the C12 refinement pass: redaction, sensitive paths, embedding reuse and limits.

These tests use fakes only (no model download, no ChromaDB, no network).
"""
import os
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app import embedding_service as emb
from backend.app.repository import inspect_repository
from backend.app.security import REDACTED, redact_secrets


class RedactionTests(unittest.TestCase):
    def test_json_yaml_env_properties_url_and_bearer_secrets_are_masked(self):
        samples = {
            '{"password": "hunter2hunter2"}': "hunter2hunter2",
            "api_key: abcd1234efgh5678": "abcd1234efgh5678",
            "export API_KEY=abcd1234efgh5678": "abcd1234efgh5678",
            "set DB_PWD=abc12345xyz": "abc12345xyz",
            "spring.datasource.password=hunter2hunter2": "hunter2hunter2",
            'URL = "postgres://user:pass1234@host/db"': "pass1234",
            'h = {"Authorization": "Bearer abcdefghijklmnop1234"}': "abcdefghijklmnop1234",
            '"    API_KEY = \\"abcd1234efgh5678\\"\\n",': "abcd1234efgh5678",
            "key = AIza" + "A" * 35: "A" * 35,
        }
        for text, secret in samples.items():
            with self.subTest(text=text):
                cleaned = redact_secrets(text)
                self.assertNotIn(secret, cleaned)
                self.assertIn(REDACTED, cleaned)
                self.assertEqual(cleaned.count("\n"), text.count("\n"))

    def test_ordinary_code_is_not_masked(self):
        for line in ("token = get_token(request)", "password: str", "token: Optional[str]",
                     "secret: SecretStr", "check(password=password_hash)",
                     "    password=user_password_value,", "TOKEN=$OTHER", "def f(token, secret):",
                     "password = request.form['pw']"):
            with self.subTest(line=line):
                self.assertEqual(redact_secrets(line), line)

    def test_multiline_input_keeps_line_numbers(self):
        text = "a: 1\npassword: hunter2hunter2\nb: 2\n"
        self.assertEqual(redact_secrets(text).splitlines()[0], "a: 1")
        self.assertEqual(len(redact_secrets(text).splitlines()), 3)


class SensitivePathTests(unittest.TestCase):
    def test_secret_directories_and_credential_files_are_excluded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for relative in ("src/app.py", "secrets/prod.yaml", ".aws/config.json", "cfg/client_secret_1.json",
                             "cfg/service-account-prod.json", "cfg/settings.json", "docs/readme.md"):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("x", encoding="utf-8")
            paths = {item["path"] for item in inspect_repository(str(root))["files"]}
        self.assertEqual(paths, {"src/app.py", "cfg/settings.json", "docs/readme.md"})


class FakeModel:
    def __init__(self):
        self.calls = 0
        self.max_inflight = 0
        self.inflight = 0
        self.guard = threading.Lock()

    def encode(self, texts, **kwargs):
        with self.guard:
            self.inflight += 1
            self.max_inflight = max(self.max_inflight, self.inflight)
        self.calls += 1
        with self.guard:
            self.inflight -= 1
        return [[float(len(t)), 1.0, 0.5] for t in texts]


class FakeCollection:
    def __init__(self, existing=()):
        self.ids = list(existing)
        self.upserts = []
        self.deletes = []

    def upsert(self, **kwargs):
        self.upserts.append(len(kwargs["ids"]))
        self.ids = list(dict.fromkeys(self.ids + kwargs["ids"]))

    def get(self, include=None, limit=None, offset=0):
        return {"ids": list(self.ids)}

    def delete(self, ids):
        self.deletes.append(len(ids))
        self.ids = [i for i in self.ids if i not in set(ids)]


def _chunk(i):
    return {"chunk_id": f"c{i}", "content": f"def f{i}(): pass", "file_path": "a.py", "language": "python",
            "kind": "function_definition", "start_line": i, "end_line": i}


class EmbeddingBehaviourTests(unittest.TestCase):
    def test_large_index_is_written_in_slices_and_stale_ids_removed_in_batches(self):
        collection = FakeCollection(existing=[f"old{i}" for i in range(1200)])
        result = emb.index_chunks([_chunk(i) for i in range(150)], collection, FakeModel(), batch_size=8)
        self.assertEqual(sum(collection.upserts), 150)
        self.assertTrue(all(size <= max(8, emb.WRITE_SLICE) for size in collection.upserts))
        self.assertGreater(len(collection.upserts), 1)
        self.assertEqual(result["removed_stale_count"], 1200)
        self.assertEqual(collection.deletes, [500, 500, 200])
        self.assertEqual(len(collection.ids), 150)
        self.assertEqual(result["embedding_dimensions"], 3)

    def test_failed_embedding_keeps_existing_entries(self):
        class Boom(FakeModel):
            def encode(self, texts, **kw):
                raise RuntimeError("model failed")
        collection = FakeCollection(existing=["old"])
        with self.assertRaises(RuntimeError):
            emb.index_chunks([_chunk(1)], collection, Boom())
        self.assertEqual(collection.ids, ["old"])
        self.assertEqual(collection.deletes, [])

    def test_embedding_model_is_loaded_once_and_reused(self):
        loads = []

        class FakeST:
            def __init__(self, name, device=None):
                loads.append(name)

        module = types.SimpleNamespace(SentenceTransformer=FakeST)
        emb._MODEL_CACHE.clear()
        with patch.dict(sys.modules, {"sentence_transformers": module}), patch.dict(os.environ, {"RAG_EMBEDDING_CACHE": "1"}):
            first = emb._load_embedding_model("m")
            second = emb._load_embedding_model("m")
        self.assertIs(first, second)
        self.assertEqual(loads, ["m"])
        emb._MODEL_CACHE.clear()

    def test_cache_can_be_disabled_for_tiny_machines(self):
        loads = []

        class FakeST:
            def __init__(self, name, device=None):
                loads.append(name)

        module = types.SimpleNamespace(SentenceTransformer=FakeST)
        emb._MODEL_CACHE.clear()
        with patch.dict(sys.modules, {"sentence_transformers": module}), patch.dict(os.environ, {"RAG_EMBEDDING_CACHE": "0"}):
            emb._load_embedding_model("m")
            emb._load_embedding_model("m")
        self.assertEqual(loads, ["m", "m"])

    def test_second_concurrent_indexing_job_is_refused_politely(self):
        self.assertTrue(emb._INDEX_SLOT.acquire(blocking=False))
        try:
            with self.assertRaises(RuntimeError) as caught:
                emb.index_repository("/does/not/matter")
            self.assertIn("Another repository is being indexed", str(caught.exception))
        finally:
            emb._INDEX_SLOT.release()

    def test_slot_is_released_after_a_failed_job(self):
        with patch.object(emb, "chunk_repository", side_effect=ValueError("bad repo")):
            with self.assertRaises(ValueError):
                emb.index_repository("/x")
        self.assertTrue(emb._INDEX_SLOT.acquire(blocking=False))
        emb._INDEX_SLOT.release()

    def test_chroma_client_is_shared_per_folder(self):
        created = []
        fake = types.SimpleNamespace(PersistentClient=lambda path: created.append(path) or object())
        emb._CLIENTS.clear()
        with patch.dict(sys.modules, {"chromadb": fake}):
            a = emb._chroma_client(Path("/tmp/one"))
            b = emb._chroma_client(Path("/tmp/one"))
            c = emb._chroma_client(Path("/tmp/two"))
        self.assertIs(a, b)
        self.assertIsNot(a, c)
        self.assertEqual(len(created), 2)
        emb._CLIENTS.clear()

    def test_index_info_reads_every_page_of_metadata(self):
        rows = [{"file_path": f"f{i}.py", "language": "python", "kind": "function_definition", "symbol": "s"}
                for i in range(2500)]

        class Coll:
            metadata = {"embedding_model": "m"}
            def count(self): return len(rows)
            def get(self, include=None, limit=None, offset=0):
                return {"metadatas": rows[offset:offset + limit]}

        class Client:
            def get_collection(self, name): return Coll()

        with tempfile.TemporaryDirectory() as temp, patch.object(emb, "DEFAULT_PERSIST_DIRECTORY", Path(temp)), \
                patch.dict(sys.modules, {"chromadb": types.SimpleNamespace(PersistentClient=lambda path: Client())}):
            emb._CLIENTS.clear()
            info = emb.get_index_info(temp)
            emb._CLIENTS.clear()
        self.assertEqual(info["chunk_count"], 2500)
        self.assertEqual(info["file_count"], 2500)
        self.assertEqual(info["symbol_count"], 2500)


if __name__ == "__main__":
    unittest.main()
