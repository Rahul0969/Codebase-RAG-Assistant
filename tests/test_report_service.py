import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app import report_service


class ReportServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "sample-repo"
        self.root.mkdir()
        (self.root / "src").mkdir()
        (self.root / "src" / "main.py").write_text(
            "def greet(name):\n    return f'Hello {name}'\n", encoding="utf-8"
        )
        (self.root / "package.json").write_text(json.dumps({
            "dependencies": {"react": "^19.0.0"},
            "devDependencies": {"vite": "^7.0.0"},
        }), encoding="utf-8")
        (self.root / ".env").write_text("API_KEY='do-not-read-this-secret'\n", encoding="utf-8")
        self.reports = Path(self.temp.name) / "reports"
        self.chunks = {
            "chunk_count": 1,
            "chunks": [{"file_path": "src/main.py", "start_line": 1, "end_line": 2,
                        "content": "def greet(name):\n    return f'Hello {name}'", "language": "python"}],
            "skipped_files": [], "truncated": False,
        }

    def generate(self, fmt="md", ai=False):
        with patch.object(report_service, "chunk_repository", return_value=self.chunks):
            return report_service.generate_report(str(self.root), fmt, ai, self.reports)

    def test_markdown_report_has_real_statistics_and_dependencies(self):
        result = self.generate("md")
        self.assertEqual(result["format"], "md")
        self.assertIn("Files inspected: 2", result["content"])
        self.assertIn("react (^19.0.0)", result["content"])
        self.assertIn("src/main.py", result["content"])
        self.assertNotIn("do-not-read-this-secret", result["content"])

    def test_html_output_escapes_source_and_has_html_document(self):
        result = self.generate("html")
        self.assertTrue(result["content"].startswith("<!doctype html>"))
        self.assertIn("<body>", result["content"])

    def test_json_output_is_valid_and_has_limitations(self):
        result = self.generate("json")
        parsed = json.loads(result["content"])
        self.assertEqual(parsed["repository_name"], "sample-repo")
        self.assertTrue(parsed["limitations"])
        self.assertEqual(parsed["statistics"]["chunks_generated"], 1)

    def test_html_renderer_escapes_untrusted_repository_text(self):
        rendered = report_service._build_html("<script>alert(1)</script>", {"repository_name": "<repo>"})
        self.assertNotIn("<script>alert(1)</script>", rendered)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", rendered)
        self.assertIn("&lt;repo&gt;", rendered)

    def test_invalid_format_rejected(self):
        with self.assertRaises(ValueError):
            self.generate("pdf")

    def test_reports_can_be_listed_and_read_by_opaque_id(self):
        result = self.generate("md")
        listed = report_service.list_reports(self.reports)
        self.assertEqual(listed[0]["report_id"], result["report_id"])
        content, mime, filename = report_service.read_report(result["report_id"], self.reports)
        self.assertEqual(content, result["content"])
        self.assertEqual(filename, result["filename"])
        self.assertIn("text/markdown", mime)

    def test_invalid_or_traversal_report_id_rejected(self):
        with self.assertRaises(FileNotFoundError):
            report_service.read_report("../../README.md", self.reports)

    def test_ai_summary_failure_falls_back_to_deterministic(self):
        with patch.object(report_service, "chunk_repository", return_value=self.chunks), \
             patch.object(report_service, "get_settings", side_effect=report_service.LLMError("offline")):
            result = report_service.generate_report(str(self.root), "md", True, self.reports)
        self.assertEqual(result["summary_source"], "deterministic")
        self.assertIn("Ollama summary generation was unavailable", result["content"])


if __name__ == "__main__":
    unittest.main()
