import tempfile
import unittest
from pathlib import Path

from backend.app.chunker import _split_text
from backend.app.repository import inspect_repository
from backend.app.security import redact_secrets


class TestChunkLineNumbers(unittest.TestCase):
    def test_leading_and_trailing_blank_lines_do_not_shift_line_numbers(self):
        chunk = _split_text("a.py", "python", "module", None, 1, "\n\nimport os\nx = 1\n\n", 6000, False)[0]
        self.assertEqual((chunk["start_line"], chunk["end_line"]), (3, 4))
        self.assertEqual(chunk["content"], "import os\nx = 1")

    def test_crlf_and_split_chunks_keep_exact_ranges(self):
        chunks = _split_text("a.py", "python", "module", None, 10, "a\r\nb\r\n\r\nc\r\n", 4, False)
        self.assertEqual([(c["start_line"], c["end_line"], c["content"]) for c in chunks],
                         [(10, 10, "a"), (11, 11, "b"), (13, 13, "c")])


class TestSensitiveNames(unittest.TestCase):
    def test_secret_names_with_extensions_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("secrets.py", "credentials.json", "id_rsa.txt", ".npmrc", "app.py"):
                (root / name).write_text("x", encoding="utf-8")
            paths = {item["path"] for item in inspect_repository(str(root))["files"]}
        self.assertEqual(paths, {"app.py"})


class TestRedaction(unittest.TestCase):
    def test_redacts_common_secret_shapes_and_keeps_line_count(self):
        text = ('password = "hunter2hunter2"\naws = "AKIAABCDEFGHIJKLMNOP"\n'
                "-----BEGIN RSA PRIVATE KEY-----\nabc\ndef\n-----END RSA PRIVATE KEY-----\nok = 1")
        cleaned = redact_secrets(text)
        for leaked in ("hunter2hunter2", "AKIAABCDEFGHIJKLMNOP", "abc"):
            self.assertNotIn(leaked, cleaned)
        self.assertEqual(cleaned.count("\n"), text.count("\n"))
        self.assertIn("ok = 1", cleaned)

    def test_normal_code_is_unchanged(self):
        code = 'token_count = len(items)\nname = "alice"'
        self.assertEqual(redact_secrets(code), code)


if __name__ == "__main__":
    unittest.main()
