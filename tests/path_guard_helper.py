"""Test helper: endpoint tests use fake paths such as C:/repo, so the API path guard is bypassed.

The guard itself is tested in test_api_security.py.
"""
from unittest.mock import patch


def bypass_path_guard(testcase):
    patcher = patch("backend.app.main.validate_repository_path", side_effect=lambda path: path)
    patcher.start()
    testcase.addCleanup(patcher.stop)
