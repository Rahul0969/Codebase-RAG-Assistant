"""Workflow tests: inspect -> index -> status -> search -> ask, across the real service modules.

Heavy parts are replaced by small fakes: the embedding model (bag-of-words vectors),
ChromaDB (an in-memory store with cosine search), Tree-sitter chunking, and Ollama.
Everything else (inspection, indexing logic, search, context building, RAG,
evidence validation, API error translation) is the real code.
"""
import math
import re
import sys
import zlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from backend.app import main
from backend.app.llm_service import OllamaTimeoutError, OllamaUnavailableError

DIMS = 1024

AUTH_CODE = ("def authenticate_user(username, password):\n"
             "    user = find_user(username)\n"
             "    return verify_password(user, password)")
TOKEN_CODE = ("def create_access_token(user):\n"
              "    return sign_token(user.id)")


def embed(text):
    vector = [0.0] * DIMS
    for word in re.findall(r"[a-z]+", text.lower()):
        vector[zlib.crc32(word.encode()) % DIMS] += 1.0  # deterministic across runs
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


class FakeModel:
    def encode(self, texts, **kwargs):
        return [embed(t) for t in texts]


class FakeCollection:
    def __init__(self, metadata):
        self.metadata = metadata
        self.rows = {}

    def upsert(self, ids, documents, metadatas, embeddings):
        for i, doc, meta, vec in zip(ids, documents, metadatas, embeddings):
            self.rows[i] = (doc, meta, vec)

    def get(self, include=None, limit=None):
        ids = list(self.rows)
        return {"ids": ids, "metadatas": [self.rows[i][1] for i in ids]}

    def delete(self, ids):
        for i in ids:
            self.rows.pop(i, None)

    def count(self):
        return len(self.rows)

    def query(self, query_embeddings, n_results, include=None):
        query = query_embeddings[0]
        scored = sorted(
            ((1.0 - sum(a * b for a, b in zip(query, vec)), i) for i, (_, _, vec) in self.rows.items()))
        top = scored[:n_results]
        return {"ids": [[i for _, i in top]],
                "documents": [[self.rows[i][0] for _, i in top]],
                "metadatas": [[self.rows[i][1] for _, i in top]],
                "distances": [[d for d, _ in top]]}


class FakeClient:
    collections = {}

    def __init__(self, path=None):
        pass

    def get_or_create_collection(self, name, metadata=None):
        return self.collections.setdefault(name, FakeCollection(metadata or {}))

    def get_collection(self, name):
        if name not in self.collections:
            raise Exception("collection not found")
        return self.collections[name]


class FakeChromaModule:
    PersistentClient = FakeClient


def chunk(path, symbol, code):
    return {"chunk_id": f"{path}:{symbol}", "content": code, "file_path": path, "language": "python",
            "kind": "function_definition", "symbol": symbol, "start_line": 1,
            "end_line": len(code.splitlines()), "parse_has_error": False}


class WorkflowCase(unittest.TestCase):
    def setUp(self):
        FakeClient.collections = {}
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.repo = root / "demo-repo"
        self.repo.mkdir()
        (self.repo / "auth.py").write_text(AUTH_CODE, encoding="utf-8")
        (self.repo / "token.py").write_text(TOKEN_CODE, encoding="utf-8")
        self.repo_path = str(self.repo)
        chunks = [chunk("auth.py", "authenticate_user", AUTH_CODE),
                  chunk("token.py", "create_access_token", TOKEN_CODE)]
        chunked = {"repository_name": "demo-repo", "file_count_scanned": 2, "chunk_count": 2,
                   "truncated": False, "skipped_files": [], "chunks": chunks}
        patches = [
            patch("backend.app.embedding_service.chunk_repository", return_value=chunked),
            patch("backend.app.embedding_service._load_embedding_model", return_value=FakeModel()),
            patch("backend.app.embedding_service.DEFAULT_PERSIST_DIRECTORY", root / "chroma"),
            patch.dict(sys.modules, {"chromadb": FakeChromaModule}),
            # Folders under the system temp directory are not valid for the C10 path guard.
            patch("backend.app.main.validate_repository_path", side_effect=lambda p: p, create=True),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def index(self):
        return main.index_repository_endpoint(main.IndexRequest(repository_path=self.repo_path, batch_size=2))

    def ask(self, question, answer, **kwargs):
        request = main.AskRequest(repository_path=self.repo_path, question=question, include_source_text=True)
        with patch("backend.app.rag_service.generate_chat", return_value={"text": answer, "model": "qwen2.5:3b"}):
            return main.ask_repository_endpoint(request)


class TestWorkflow(WorkflowCase):
    def test_health_reports_ollama_and_does_not_need_models(self):
        info = {"ollama_reachable": True, "model": "qwen2.5:3b", "model_available": True, "installed_models": []}
        with patch("backend.app.main.check_ollama", return_value=info):
            result = main.health()
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["ollama"]["reachable"])
        self.assertEqual(result["ollama"]["model"], "qwen2.5:3b")
        self.assertFalse(result["embedding"]["loaded"])
        self.assertIn("installed", result["chromadb"])

    def test_health_when_ollama_is_down_still_returns_ok(self):
        with patch("backend.app.main.check_ollama", side_effect=OllamaUnavailableError("Cannot reach Ollama")):
            result = main.health()
        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["ollama"]["reachable"])
        self.assertIn("Cannot reach Ollama", result["ollama"]["message"])

    def test_health_when_model_missing(self):
        info = {"ollama_reachable": True, "model": "qwen2.5:3b", "model_available": False, "installed_models": []}
        with patch("backend.app.main.check_ollama", return_value=info):
            result = main.health()
        self.assertFalse(result["ollama"]["model_available"])
        self.assertIn("ollama pull", result["ollama"]["message"])

    def test_full_workflow(self):
        inspected = main.inspect_repository_endpoint(main.RepositoryRequest(repository_path=self.repo_path))
        self.assertEqual(inspected["file_count"], 2)

        before = main.repository_status_endpoint(main.RepositoryRequest(repository_path=self.repo_path))
        self.assertFalse(before["indexed"])

        indexed = self.index()
        self.assertEqual((indexed["chunk_count"], indexed["indexed_count"]), (2, 2))
        self.assertEqual(indexed["storage"], "local ChromaDB")

        after = main.repository_status_endpoint(main.RepositoryRequest(repository_path=self.repo_path))
        self.assertTrue(after["indexed"])
        self.assertEqual(after["chunk_count"], 2)

        found = main.search_repository_endpoint(main.SearchRequest(
            repository_path=self.repo_path, query="authenticate user password", top_k=2))
        self.assertEqual(found["matches"][0]["file_path"], "auth.py")
        self.assertEqual((found["matches"][0]["start_line"], found["matches"][0]["end_line"]), (1, 3))

        result = self.ask("How does authenticate user check the password?",
                          "`authenticate_user` looks up the user and verifies the password [auth.py:1-3].")
        self.assertTrue(result["success"])
        self.assertEqual(result["evidence_status"], "verified")
        self.assertTrue(result["validation_passed"])
        self.assertEqual(result["citations"][0]["text"], "auth.py:1-3")
        self.assertTrue(result["citations"][0]["valid"])
        self.assertTrue(any(c["cited"] and c["file_path"] == "auth.py" for c in result["retrieved_chunks"]))
        self.assertIn("verify_password", next(c["content"] for c in result["retrieved_chunks"]
                                              if c["file_path"] == "auth.py"))
        self.assertEqual(result["model"], "qwen2.5:3b")

    def test_invalid_citation_status_propagates(self):
        self.index()
        result = self.ask("How does authenticate user check the password?",
                          "It is handled in [other.py:1-9] by the login code.")
        self.assertEqual(result["evidence_status"], "invalid_citations")
        self.assertFalse(result["validation_passed"])
        self.assertEqual(result["unsupported_citations"][0]["reason"], "file_not_retrieved")

    def test_missing_citations_status_propagates(self):
        self.index()
        result = self.ask("How does authenticate user check the password?", "It verifies the password.")
        self.assertEqual(result["evidence_status"], "no_citations")

    def test_unrelated_question_is_insufficient_without_calling_the_llm(self):
        self.index()
        request = main.AskRequest(repository_path=self.repo_path, question="zebra quantum pineapple volcano")
        with patch("backend.app.rag_service.generate_chat") as chat:
            result = main.ask_repository_endpoint(request)
        chat.assert_not_called()
        self.assertEqual(result["evidence_status"], "insufficient_evidence")
        self.assertFalse(result["success"])

    def test_reindex_removes_stale_chunks(self):
        self.index()
        smaller = {"repository_name": "demo-repo", "file_count_scanned": 1, "chunk_count": 1,
                   "truncated": False, "skipped_files": [], "chunks": [chunk("auth.py", "authenticate_user", AUTH_CODE)]}
        with patch("backend.app.embedding_service.chunk_repository", return_value=smaller):
            result = self.index()
        self.assertEqual(result["removed_stale_count"], 1)


class TestErrorResponses(WorkflowCase):
    def raises(self, call):
        with self.assertRaises(HTTPException) as ctx:
            call()
        return ctx.exception

    def code(self, error):
        return error.headers["X-Error-Code"]

    def test_search_and_ask_before_indexing(self):
        error = self.raises(lambda: main.search_repository_endpoint(
            main.SearchRequest(repository_path=self.repo_path, query="login")))
        self.assertEqual((error.status_code, self.code(error)), (400, "not_indexed"))
        error = self.raises(lambda: main.ask_repository_endpoint(
            main.AskRequest(repository_path=self.repo_path, question="login?")))
        self.assertEqual((error.status_code, self.code(error)), (400, "not_indexed"))

    def test_invalid_repository_path(self):
        error = self.raises(lambda: main.inspect_repository_endpoint(
            main.RepositoryRequest(repository_path="relative/path")))
        self.assertEqual((error.status_code, self.code(error)), (400, "invalid_request"))

    def test_ollama_errors_have_distinct_codes(self):
        self.index()
        for exc, status, code in ((OllamaUnavailableError("down"), 503, "ollama_unavailable"),
                                  (OllamaTimeoutError("slow"), 504, "llm_timeout")):
            request = main.AskRequest(repository_path=self.repo_path, question="authenticate user password")
            with patch("backend.app.rag_service.generate_chat", side_effect=exc):
                error = self.raises(lambda: main.ask_repository_endpoint(request))
            self.assertEqual((error.status_code, self.code(error)), (status, code))

    def test_request_validation(self):
        bad = [
            lambda: main.AskRequest(repository_path=self.repo_path, question=""),
            lambda: main.AskRequest(repository_path=self.repo_path, question="q", top_k=11),
            lambda: main.SearchRequest(repository_path=self.repo_path, query="q", top_k=0),
            lambda: main.IndexRequest(repository_path=self.repo_path, batch_size=33),
            lambda: main.RepositoryRequest(repository_path=""),
        ]
        for build in bad:
            with self.assertRaises(Exception):
                build()


try:
    from fastapi.testclient import TestClient
except Exception:  # pragma: no cover - needs fastapi and httpx (see backend/requirements-dev.txt)
    TestClient = None


@unittest.skipIf(TestClient is None, "fastapi TestClient/httpx not installed (pip install -r backend/requirements-dev.txt)")
class TestHttpLayer(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app, base_url="http://127.0.0.1:8000")

    def test_all_routes_registered(self):
        paths = set(self.client.get("/openapi.json").json()["paths"])
        expected = {"/health", "/repository/inspect", "/repository/chunk", "/repository/index",
                    "/repository/status", "/repository/search", "/repository/ask", "/llm/status"}
        self.assertTrue(expected <= paths)

    def test_health_shape(self):
        data = self.client.get("/health").json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("ollama", data)

    def test_validation_errors_are_422(self):
        response = self.client.post("/repository/ask", json={"repository_path": "C:/x", "question": ""})
        self.assertEqual(response.status_code, 422)

    def test_error_code_header_is_sent_and_exposed(self):
        response = self.client.post("/repository/inspect", json={"repository_path": "relative"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.headers.get("x-error-code"), "invalid_request")


if __name__ == "__main__":
    unittest.main()
