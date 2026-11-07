import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app import mcp_tools
from backend.app.embedding_service import get_index_info
from backend.app.llm_service import OllamaUnavailableError
from backend.app.mcp_tools import McpToolError
from backend.app.security import PathNotAllowedError, validate_repository_path

TESTS_DIR = Path(__file__).resolve().parent
FAKE_REPO = Path("repo-for-tests")


def allow_path():
    return patch("backend.app.mcp_tools.validate_repository_path", return_value=FAKE_REPO)


class TestPathGuard(unittest.TestCase):
    def setUp(self):
        # Temp folders live inside the tests folder: system temp folders on Windows are under AppData.
        self.tmp = tempfile.TemporaryDirectory(dir=TESTS_DIR)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_accepts_normal_directory(self):
        self.assertEqual(validate_repository_path(str(self.root)), self.root.resolve())

    def test_rejects_bad_input(self):
        file_path = self.root / "a.py"
        file_path.write_text("x", encoding="utf-8")
        for bad in ("", "   ", "relative/path", str(self.root / "missing"), str(file_path), "a\x00b"):
            with self.assertRaises(PathNotAllowedError, msg=repr(bad)):
                validate_repository_path(bad)

    def test_rejects_root_and_home(self):
        for risky in (self.root.resolve().anchor, str(Path.home())):
            with self.assertRaises(PathNotAllowedError):
                validate_repository_path(risky)

    def test_rejects_credential_folders(self):
        folder = self.root / ".ssh" / "project"
        folder.mkdir(parents=True)
        with self.assertRaises(PathNotAllowedError):
            validate_repository_path(str(folder))

    def test_rejects_system_folder(self):
        candidate = os.environ.get("SystemRoot") or "/etc"
        if not os.path.isdir(candidate):
            self.skipTest("no system folder available")
        with self.assertRaises(PathNotAllowedError):
            validate_repository_path(candidate)

    def test_allowed_roots_restrict_location(self):
        inside = self.root / "inside"
        inside.mkdir()
        with patch.dict(os.environ, {"RAG_ALLOWED_ROOTS": str(inside)}):
            self.assertEqual(validate_repository_path(str(inside)), inside.resolve())
            with self.assertRaises(PathNotAllowedError):
                validate_repository_path(str(self.root))

    def test_rejects_symlink_root(self):
        target = self.root / "real"
        target.mkdir()
        link = self.root / "link"
        try:
            os.symlink(target, link, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not available")
        with self.assertRaises(PathNotAllowedError):
            validate_repository_path(str(link))

    def test_error_messages_do_not_echo_the_path(self):
        secret_path = str(self.root / "very-private-name")
        with self.assertRaises(PathNotAllowedError) as ctx:
            validate_repository_path(secret_path)
        self.assertNotIn("very-private-name", str(ctx.exception))


class TestTools(unittest.TestCase):
    def test_inspect_summarizes_and_caps_files(self):
        files = [{"path": f"src/f{i}.py", "extension": ".py"} for i in range(350)]
        files.append({"path": "README.md", "extension": ".md"})
        inspection = {"repository_name": "demo", "file_count": 351, "truncated": False,
                      "skipped_directories": [], "files": files}
        with allow_path(), patch("backend.app.mcp_tools.inspect_repository", return_value=inspection):
            result = mcp_tools.inspect_repository_tool("ignored")
        self.assertEqual(result["extension_counts"], {".py": 350, ".md": 1})
        self.assertEqual(len(result["files"]), 300)
        self.assertEqual(result["files_omitted"], 51)

    def test_index_passes_validated_options(self):
        stats = {"indexed_count": 3, "skipped_files": [{"path": str(i), "reason": "x"} for i in range(60)]}
        with allow_path(), patch("backend.app.mcp_tools.index_repository", return_value=stats) as mocked:
            result = mcp_tools.index_repository_tool("ignored", max_chars=4000, batch_size=4)
        mocked.assert_called_once_with(str(FAKE_REPO), max_chars=4000, batch_size=4)
        self.assertEqual(len(result["skipped_files"]), 50)
        self.assertEqual(result["skipped_files_omitted"], 10)

    def test_input_validation(self):
        bad_calls = [
            lambda: mcp_tools.index_repository_tool("p", max_chars=10),
            lambda: mcp_tools.index_repository_tool("p", batch_size=0),
            lambda: mcp_tools.index_repository_tool("p", batch_size=True),
            lambda: mcp_tools.search_code_tool("p", "   "),
            lambda: mcp_tools.search_code_tool("p", "q", top_k=21),
            lambda: mcp_tools.ask_codebase_tool("p", "", top_k=3),
            lambda: mcp_tools.ask_codebase_tool("p", "q", top_k=11),
            lambda: mcp_tools.ask_codebase_tool("p", "x" * 2001),
        ]
        with allow_path():
            for call in bad_calls:
                with self.assertRaises(McpToolError):
                    call()

    def test_search_masks_secrets_and_shortens(self):
        match = {"file_path": "a.py", "language": "python", "symbol": "f", "kind": "function_definition",
                 "start_line": 3, "end_line": 9, "similarity": 0.91234,
                 "content": 'api_key = "topsecretvalue99"\n' + "x = 1\n" * 600}
        found = {"repository_name": "demo", "query": "q", "result_count": 1, "matches": [match]}
        with allow_path(), patch("backend.app.mcp_tools.search_repository", return_value=found):
            result = mcp_tools.search_code_tool("p", " find it ", top_k=3)
        item = result["matches"][0]
        self.assertNotIn("topsecretvalue99", item["content"])
        self.assertEqual(item["citation"], "a.py:3-9")
        self.assertTrue(item["content_shortened"])
        self.assertLessEqual(len(item["content"]), 1500)

    def test_ask_returns_answer_and_evidence(self):
        rag = {"answer": "It checks [a.py:1-2].", "evidence_status": "verified", "validation_passed": True,
               "evidence_summary": "ok", "citations": [{"text": "a.py:1-2", "valid": True, "reason": "ok",
                                                         "file_path": "a.py"}],
               "unsupported_citations": [], "unsupported_identifiers": [], "sources": [{"source_id": 1}],
               "model": "qwen2.5:3b", "repository_name": "demo", "retrieved_chunks": []}
        with allow_path(), patch("backend.app.mcp_tools.ask_repository", return_value=rag) as mocked:
            result = mcp_tools.ask_codebase_tool("p", " Where? ", top_k=4)
        mocked.assert_called_once_with(str(FAKE_REPO), "Where?", top_k=4)
        self.assertEqual(result["evidence_status"], "verified")
        self.assertEqual(result["citations"], [{"text": "a.py:1-2", "valid": True, "reason": "ok"}])
        self.assertNotIn("retrieved_chunks", result)

    def test_summary_is_built_from_inspection_and_index(self):
        files = [{"path": "main.py", "extension": ".py"}, {"path": "src/a.py", "extension": ".py"},
                 {"path": "src/b.js", "extension": ".js"}]
        inspection = {"repository_name": "demo", "file_count": 3, "truncated": False,
                      "skipped_directories": [], "files": files}
        index = {"indexed": False, "chunk_count": 0}
        with allow_path(), patch("backend.app.mcp_tools.inspect_repository", return_value=inspection), \
             patch("backend.app.mcp_tools.get_index_info", return_value=index):
            result = mcp_tools.get_repository_summary_tool("p")
        self.assertEqual(result["top_level_entries"], {"src": 2, "(root files)": 1})
        self.assertEqual(result["notable_files_by_name"], ["main.py"])
        self.assertIn("not indexed", result["note"])

    def test_service_errors_become_safe_messages(self):
        with allow_path():
            with patch("backend.app.mcp_tools.search_repository",
                       side_effect=ValueError("No index exists for this repository. Run POST /repository/index first.")):
                with self.assertRaises(McpToolError) as ctx:
                    mcp_tools.search_code_tool("p", "q")
                self.assertIn("No index exists", str(ctx.exception))
            with patch("backend.app.mcp_tools.ask_repository", side_effect=OllamaUnavailableError("Ollama is down")):
                with self.assertRaises(McpToolError) as ctx:
                    mcp_tools.ask_codebase_tool("p", "q")
                self.assertIn("Ollama", str(ctx.exception))
            with patch("backend.app.mcp_tools.inspect_repository", side_effect=OSError("C:\\Users\\me\\secret")):
                with self.assertRaises(McpToolError) as ctx:
                    mcp_tools.inspect_repository_tool("p")
                self.assertNotIn("secret", str(ctx.exception))

    def test_invalid_paths_are_rejected_before_any_work(self):
        with patch("backend.app.mcp_tools.inspect_repository") as mocked:
            with self.assertRaises(McpToolError):
                mcp_tools.inspect_repository_tool("relative/path")
        mocked.assert_not_called()


class FakeCollection:
    metadata = {"embedding_model": "m"}

    def count(self):
        return 3

    def get(self, **kwargs):
        return {"metadatas": [
            {"file_path": "a.py", "language": "python", "kind": "function_definition", "symbol": "f"},
            {"file_path": "a.py", "language": "python", "kind": "module"},
            {"file_path": "b.js", "language": "javascript", "kind": "function_declaration", "symbol": "g"},
        ]}


class FakeClient:
    def __init__(self, collection):
        self.collection = collection

    def get_collection(self, name):
        if self.collection is None:
            raise Exception("missing")
        return self.collection


class TestIndexInfo(unittest.TestCase):
    def run_info(self, collection):
        with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as db:
            fake = type("FakeChroma", (), {"PersistentClient": lambda **kw: FakeClient(collection)})
            with patch("backend.app.embedding_service.DEFAULT_PERSIST_DIRECTORY", Path(db)), \
                 patch.dict("sys.modules", {"chromadb": fake}):
                return get_index_info(repo)

    def test_reports_statistics(self):
        info = self.run_info(FakeCollection())
        self.assertTrue(info["indexed"])
        self.assertEqual((info["chunk_count"], info["file_count"], info["symbol_count"]), (3, 2, 2))
        self.assertEqual(info["languages"], {"python": 2, "javascript": 1})

    def test_missing_collection_means_not_indexed(self):
        self.assertFalse(self.run_info(None)["indexed"])


if __name__ == "__main__":
    unittest.main()
