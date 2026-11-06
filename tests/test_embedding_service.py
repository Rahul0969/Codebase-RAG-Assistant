import unittest
from unittest.mock import patch

from backend.app.embedding_service import index_chunks
from backend.app.main import IndexRequest, index_repository_endpoint


class FakeModel:
    def encode(self, texts, **kwargs):
        # Deterministic, tiny stand-in vectors; no model download in unit tests.
        return [[float(len(text)), 1.0, 0.5] for text in texts]


class FakeCollection:
    def __init__(self):
        self.ids = ["old_chunk"]
        self.upsert_payload = None
        self.deleted = []

    def upsert(self, **kwargs):
        self.upsert_payload = kwargs
        self.ids = list(dict.fromkeys(self.ids + kwargs["ids"]))

    def get(self, include=None):
        return {"ids": list(self.ids)}

    def delete(self, ids):
        self.deleted.extend(ids)
        self.ids = [item for item in self.ids if item not in ids]


class TestEmbeddingIndexing(unittest.TestCase):
    def test_embeddings_are_batched_and_metadata_is_preserved(self):
        chunks = [
            {"chunk_id": "a", "content": "def a(): pass", "file_path": "a.py",
             "language": "python", "kind": "function_definition", "symbol": "a",
             "start_line": 1, "end_line": 1},
            {"chunk_id": "b", "content": "def b(): pass", "file_path": "b.py",
             "language": "python", "kind": "function_definition", "symbol": "b",
             "start_line": 2, "end_line": 2},
        ]
        collection = FakeCollection()
        result = index_chunks(chunks, collection, FakeModel(), batch_size=1)
        self.assertEqual(result["indexed_count"], 2)
        self.assertEqual(result["embedding_dimensions"], 3)
        self.assertEqual(result["removed_stale_count"], 1)
        self.assertEqual(collection.deleted, ["old_chunk"])
        self.assertEqual(collection.upsert_payload["metadatas"][0]["symbol"], "a")
        self.assertEqual(collection.upsert_payload["metadatas"][0]["start_line"], 1)

    def test_empty_chunks_do_not_call_model_or_collection(self):
        result = index_chunks([], object(), object())
        self.assertEqual(result["indexed_count"], 0)

    def test_invalid_batch_size_is_rejected(self):
        with self.assertRaises(ValueError):
            index_chunks([], object(), object(), batch_size=0)

    def test_index_endpoint_calls_service(self):
        expected = {"indexed_count": 2}
        with patch("backend.app.main.index_repository", return_value=expected) as mocked:
            result = index_repository_endpoint(IndexRequest(repository_path="C:/repo"))
        self.assertEqual(result, expected)
        mocked.assert_called_once_with("C:/repo", max_chars=6000, batch_size=8)

    def test_index_endpoint_maps_missing_dependencies_to_503(self):
        from fastapi import HTTPException
        with patch("backend.app.main.index_repository", side_effect=RuntimeError("dependency missing")):
            with self.assertRaises(HTTPException) as context:
                index_repository_endpoint(IndexRequest(repository_path="C:/repo"))
        self.assertEqual(context.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
