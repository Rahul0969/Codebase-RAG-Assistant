import tempfile
import unittest

from path_guard_helper import bypass_path_guard
from pathlib import Path
from unittest.mock import patch

from backend.app.embedding_service import search_repository
from backend.app.main import SearchRequest, search_repository_endpoint


class FakeModel:
    def encode(self, texts, **kwargs):
        return [[0.25, 0.5, 0.75] for _ in texts]


class FakeCollection:
    def __init__(self, count=1):
        self.item_count = count
        self.query_args = None

    def count(self):
        return self.item_count

    def query(self, **kwargs):
        self.query_args = kwargs
        return {
            "ids": [["chunk-1"]],
            "documents": [["def login(): return True"]],
            "metadatas": [[{"file_path": "auth.py", "language": "python",
                             "kind": "function_definition", "symbol": "login",
                             "start_line": 3, "end_line": 3,
                             "parse_has_error": False}]],
            "distances": [[0.12]],
        }


class FakeClient:
    def __init__(self, collection):
        self.collection = collection

    def get_collection(self, name):
        return self.collection


class TestSemanticSearch(unittest.TestCase):
    def setUp(self):
        bypass_path_guard(self)

    def test_search_returns_source_metadata_and_similarity(self):
        with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as db:
            collection = FakeCollection()
            fake_chroma = type("FakeChroma", (), {
                "PersistentClient": lambda **kwargs: FakeClient(collection)
            })
            with patch("backend.app.embedding_service.DEFAULT_PERSIST_DIRECTORY", Path(db)), \
                 patch.dict("sys.modules", {"chromadb": fake_chroma}), \
                 patch("backend.app.embedding_service._load_embedding_model", return_value=FakeModel()):
                result = search_repository(repo, "where is login handled?", top_k=3)
            self.assertEqual(result["result_count"], 1)
            self.assertEqual(result["matches"][0]["file_path"], "auth.py")
            self.assertEqual(result["matches"][0]["symbol"], "login")
            self.assertAlmostEqual(result["matches"][0]["similarity"], 0.88)
            self.assertEqual(collection.query_args["n_results"], 1)  # capped at indexed collection size

    def test_search_redacts_secrets_before_returning_source_to_client(self):
        with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as db:
            collection = FakeCollection()
            collection.query = lambda **kwargs: {
                "ids": [["chunk-1"]],
                "documents": [["API_TOKEN = 'ghp_" + "A" * 36 + "\'\n"]],
                "metadatas": [[{"file_path": "settings.py", "language": "python", "kind": "module",
                                 "symbol": None, "start_line": 1, "end_line": 1, "parse_has_error": False}]],
                "distances": [[0.1]],
            }
            fake_chroma = type("FakeChroma", (), {
                "PersistentClient": lambda **kwargs: FakeClient(collection)
            })
            with patch("backend.app.embedding_service.DEFAULT_PERSIST_DIRECTORY", Path(db)), \
                 patch.dict("sys.modules", {"chromadb": fake_chroma}), \
                 patch("backend.app.embedding_service._load_embedding_model", return_value=FakeModel()):
                result = search_repository(repo, "find API token")
            content = result["matches"][0]["content"]
            self.assertIn("[REDACTED]", content)
            self.assertNotIn("ghp_", content)

    def test_empty_collection_returns_no_matches_without_loading_model(self):
        with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as db:
            fake_chroma = type("FakeChroma", (), {
                "PersistentClient": lambda **kwargs: FakeClient(FakeCollection(count=0))
            })
            with patch("backend.app.embedding_service.DEFAULT_PERSIST_DIRECTORY", Path(db)), \
                 patch.dict("sys.modules", {"chromadb": fake_chroma}), \
                 patch("backend.app.embedding_service._load_embedding_model") as load_model:
                result = search_repository(repo, "find login")
            self.assertEqual(result["matches"], [])
            load_model.assert_not_called()

    def test_search_rejects_blank_query_and_invalid_top_k(self):
        with self.assertRaises(ValueError):
            search_repository(".", "   ")
        with self.assertRaises(ValueError):
            search_repository(".", "find code", top_k=21)

    def test_endpoint_calls_search_service(self):
        expected = {"result_count": 0, "matches": []}
        request = SearchRequest(repository_path="C:/repo", query="find authentication", top_k=4)
        with patch("backend.app.main.search_repository", return_value=expected) as mocked:
            result = search_repository_endpoint(request)
        self.assertEqual(result, expected)
        mocked.assert_called_once_with("C:/repo", query="find authentication", top_k=4)

    def test_endpoint_maps_missing_index_to_400(self):
        from fastapi import HTTPException
        request = SearchRequest(repository_path="C:/repo", query="find authentication")
        with patch("backend.app.main.search_repository", side_effect=ValueError("No index")):
            with self.assertRaises(HTTPException) as context:
                search_repository_endpoint(request)
        self.assertEqual(context.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
