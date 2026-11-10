import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from backend.app import main, report_service


class ReportApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        (self.root / "hello.py").write_text("def hello():\n    return 'hi'\n", encoding="utf-8")
        self.reports = Path(self.temp.name) / "reports"
        self.patches = [
            patch.object(main, "validate_repository_path", side_effect=lambda value: Path(value)),
            patch.object(report_service, "REPORT_DIR", self.reports),
            patch.object(main, "REPORT_DIR", self.reports),
            patch.object(report_service, "chunk_repository", return_value={"chunks": [], "chunk_count": 0,
                                                                            "skipped_files": [], "truncated": False}),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_generate_list_get_and_download_report(self):
        generated = main.generate_repository_report_endpoint(
            main.ReportRequest(repository_path=str(self.root), format="json", use_ai_summary=False)
        )
        self.assertEqual(generated["format"], "json")
        listed = main.list_repository_reports_endpoint()
        self.assertEqual(listed["reports"][0]["report_id"], generated["report_id"])
        retrieved = main.get_repository_report_endpoint(generated["report_id"])
        self.assertEqual(retrieved["content"], generated["content"])
        download = main.download_repository_report_endpoint(generated["report_id"])
        self.assertTrue(Path(download.path).is_file())

    def test_unknown_report_returns_404(self):
        with self.assertRaises(HTTPException) as caught:
            main.get_repository_report_endpoint("0" * 32)
        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(caught.exception.headers["X-Error-Code"], "report_not_found")


if __name__ == "__main__":
    unittest.main()

try:
    from fastapi.testclient import TestClient
except ImportError:
    TestClient = None


@unittest.skipIf(TestClient is None, "fastapi TestClient/httpx not installed")
class ReportHttpTests(unittest.TestCase):
    def test_http_generate_and_download_routes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            root.mkdir()
            (root / "hello.py").write_text("def hello():\n    return 'hi'\n", encoding="utf-8")
            report_dir = Path(temp) / "reports"
            with patch.object(main, "validate_repository_path", side_effect=lambda value: Path(value)), \
                 patch.object(main, "REPORT_DIR", report_dir), \
                 patch.object(report_service, "REPORT_DIR", report_dir), \
                 patch.object(report_service, "chunk_repository", return_value={"chunks": [], "chunk_count": 0,
                                                                                  "skipped_files": [], "truncated": False}):
                client = TestClient(main.app, base_url="http://127.0.0.1:8000")
                response = client.post("/api/reports/generate", json={
                    "repository_path": str(root), "format": "md", "use_ai_summary": False,
                })
                self.assertEqual(response.status_code, 200, response.text)
                report_id = response.json()["report_id"]
                download = client.get(f"/api/reports/{report_id}/download")
                self.assertEqual(download.status_code, 200)
                self.assertIn("Repository Intelligence Report", download.text)
                self.assertEqual(client.get("/api/reports").status_code, 200)
