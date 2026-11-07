import tempfile
import unittest

from path_guard_helper import bypass_path_guard
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.app.chunker import (
    _definition_nodes,
    chunk_source_file,
    chunk_repository,
    DEFAULT_MAX_CHARS,
)
from backend.app.main import ChunkRequest, chunk_repository_endpoint


class FakeNode:
    def __init__(self, node_type, start_byte, end_byte, start_row=0,
                 children=None, name_node=None, has_error=False):
        self.type = node_type
        self.start_byte = start_byte
        self.end_byte = end_byte
        self.start_point = SimpleNamespace(row=start_row, column=0)
        self.end_point = SimpleNamespace(row=start_row, column=0)
        self.children = children or []
        self._name_node = name_node
        self.has_error = has_error

    def child_by_field_name(self, field):
        return self._name_node if field == "name" else None


class FakeParser:
    def __init__(self, root):
        self.root = root

    def parse(self, source):
        return SimpleNamespace(root_node=self.root)


class TestTreeSitterChunking(unittest.TestCase):
    def setUp(self):
        bypass_path_guard(self)

    def test_definition_nodes_prefer_nested_methods_over_class_container(self):
        method = FakeNode("function_definition", 10, 30, start_row=2)
        klass = FakeNode("class_definition", 0, 40, children=[method])
        root = FakeNode("module", 0, 40, children=[klass])
        self.assertEqual(_definition_nodes(root), [method])

    def test_chunks_python_function_with_line_metadata(self):
        source = "def hello():\n    return 'hi'\n"
        encoded = source.encode()
        name_start = encoded.index(b"hello")
        name = FakeNode("identifier", name_start, name_start + 5)
        fn = FakeNode("function_definition", 0, len(encoded), start_row=0, name_node=name)
        root = FakeNode("module", 0, len(encoded), children=[fn])
        tree_parser = FakeParser(root)
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "sample.py"
            file_path.write_text(source, encoding="utf-8")
            with patch("backend.app.chunker.get_parser", return_value=tree_parser):
                chunks = chunk_source_file(file_path, "sample.py")
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["symbol"], "hello")
        self.assertEqual(chunks[0]["start_line"], 1)
        self.assertEqual(chunks[0]["end_line"], 2)
        self.assertIn("return 'hi'", chunks[0]["content"])
        self.assertEqual(chunks[0]["language"], "python")

    def test_module_fallback_when_no_definitions(self):
        source = "print('hello')\nprint('world')\n"
        root = FakeNode("module", 0, len(source.encode()))
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "script.py"
            file_path.write_text(source, encoding="utf-8")
            with patch("backend.app.chunker.get_parser", return_value=FakeParser(root)):
                chunks = chunk_source_file(file_path, "script.py")
        self.assertEqual(chunks[0]["kind"], "module")
        self.assertEqual(chunks[0]["start_line"], 1)

    def test_oversized_node_is_split_on_line_boundaries(self):
        source = "def f():\n" + "    value = 1234567890\n" * 80
        root = FakeNode("module", 0, len(source.encode()), children=[
            FakeNode("function_definition", 0, len(source.encode()), start_row=0)
        ])
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "large.py"
            file_path.write_text(source, encoding="utf-8")
            with patch("backend.app.chunker.get_parser", return_value=FakeParser(root)):
                chunks = chunk_source_file(file_path, "large.py", max_chars=500)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(chunks[0]["start_line"], 1)
        for previous, current in zip(chunks, chunks[1:]):
            self.assertEqual(previous["end_line"] + 1, current["start_line"])

    def test_rejects_invalid_chunk_size(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "sample.py"
            file_path.write_text("pass", encoding="utf-8")
            with self.assertRaises(ValueError):
                chunk_source_file(file_path, "sample.py", max_chars=10)

    def test_repository_chunks_supported_files_and_skips_unsupported(self):
        source = "def hello():\n    return 1\n"
        encoded = source.encode()
        root_node = FakeNode("module", 0, len(encoded), children=[
            FakeNode("function_definition", 0, len(encoded), start_row=0)
        ])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text(source, encoding="utf-8")
            (root / "notes.md").write_text("Notes", encoding="utf-8")
            with patch("backend.app.chunker.get_parser", return_value=FakeParser(root_node)):
                result = chunk_repository(str(root))
        self.assertEqual(result["chunk_count"], 1)
        self.assertEqual(result["chunks"][0]["file_path"], "main.py")
        self.assertTrue(any(item["path"] == "notes.md" for item in result["skipped_files"]))

    def test_api_endpoint_returns_chunks(self):
        with patch("backend.app.main.chunk_repository", return_value={"chunk_count": 0, "chunks": []}) as mocked:
            result = chunk_repository_endpoint(ChunkRequest(repository_path="C:/repo"))
        self.assertEqual(result["chunk_count"], 0)
        mocked.assert_called_once_with("C:/repo", DEFAULT_MAX_CHARS)


if __name__ == "__main__":
    unittest.main()
