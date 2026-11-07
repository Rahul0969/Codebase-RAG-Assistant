import tempfile
import unittest

from path_guard_helper import bypass_path_guard
from pathlib import Path

from fastapi import HTTPException

from backend.app.main import RepositoryRequest, inspect_repository_endpoint
from backend.app.repository import inspect_repository


class TestRepositoryInspection(unittest.TestCase):
    def setUp(self):
        bypass_path_guard(self)

    def test_lists_supported_files_without_reading_other_file_types(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "main.py").write_text("print('hello')", encoding="utf-8")
            (root / "README.md").write_text("# Demo", encoding="utf-8")
            (root / "image.png").write_bytes(b"not source")

            result = inspect_repository(str(root))
            paths = {item["path"] for item in result["files"]}

            self.assertEqual(paths, {"main.py", "README.md"})
            self.assertEqual(result["file_count"], 2)
            self.assertFalse(result["truncated"])

    def test_skips_ignored_directories(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            ignored = root / "node_modules"
            ignored.mkdir()
            (ignored / "package.js").write_text("ignored", encoding="utf-8")
            (root / "app.js").write_text("included", encoding="utf-8")

            result = inspect_repository(str(root))
            paths = {item["path"] for item in result["files"]}

            self.assertEqual(paths, {"app.js"})

    def test_skips_environment_and_sensitive_files(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for name in (".env", ".env.local", "id_rsa", "server.pem", "safe.py"):
                (root / name).write_text("example", encoding="utf-8")

            result = inspect_repository(str(root))
            paths = {item["path"] for item in result["files"]}

            self.assertEqual(paths, {"safe.py"})

    def test_rejects_relative_path(self):
        with self.assertRaisesRegex(ValueError, "absolute"):
            inspect_repository("some-folder")

    def test_rejects_empty_path(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            inspect_repository("   ")

    def test_rejects_missing_directory(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            missing = str(Path(temporary_directory) / "missing")
            with self.assertRaisesRegex(ValueError, "does not exist"):
                inspect_repository(missing)

    def test_rejects_file_instead_of_directory(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            file_path = Path(temporary_directory) / "app.py"
            file_path.write_text("print('hello')", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must be a directory"):
                inspect_repository(str(file_path))

    def test_api_endpoint_returns_inspection_result(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "main.py").write_text("print('hello')", encoding="utf-8")

            result = inspect_repository_endpoint(
                RepositoryRequest(repository_path=str(root))
            )

            self.assertEqual(result["file_count"], 1)
            self.assertEqual(result["files"][0]["path"], "main.py")

    def test_api_endpoint_converts_invalid_path_to_http_400(self):
        with self.assertRaises(HTTPException) as context:
            inspect_repository_endpoint(RepositoryRequest(repository_path="relative"))

        self.assertEqual(context.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
