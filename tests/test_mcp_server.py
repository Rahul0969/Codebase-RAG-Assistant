import asyncio
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from backend.app import mcp_server
except ImportError:  # the MCP SDK is installed with: pip install -r backend/requirements.txt
    mcp_server = None

EXPECTED_TOOLS = {"inspect_repository", "index_repository", "search_code", "ask_codebase",
                  "get_repository_summary"}


@unittest.skipIf(mcp_server is None, "mcp package is not installed")
class TestMcpServer(unittest.TestCase):
    def test_server_initializes_with_name_and_instructions(self):
        self.assertEqual(mcp_server.mcp.name, "codebase-rag-assistant")
        self.assertIn("absolute path", mcp_server.INSTRUCTIONS)

    def test_all_five_tools_are_registered_with_descriptions(self):
        tools = asyncio.run(mcp_server.mcp.list_tools())
        self.assertEqual({tool.name for tool in tools}, EXPECTED_TOOLS)
        for tool in tools:
            self.assertTrue(tool.description and len(tool.description) > 20, tool.name)
            self.assertIn("repository_path", tool.inputSchema["required"], tool.name)

    def test_tool_call_reaches_the_service_layer(self):
        expected = {"result_count": 0, "matches": [], "marker": "from-mocked-tool"}
        with patch("backend.app.mcp_tools.search_code_tool", return_value=expected) as mocked:
            result = asyncio.run(mcp_server.mcp.call_tool(
                "search_code", {"repository_path": "C:/repo", "query": "login", "top_k": 3}))
        mocked.assert_called_once_with("C:/repo", "login", 3)
        self.assertIn("from-mocked-tool", str(result))

    def test_invalid_argument_is_rejected(self):
        # Rejected either by the SDK's schema validation or by the tool layer's own checks.
        with patch("backend.app.mcp_tools.validate_repository_path", return_value=Path("repo")), \
             patch("backend.app.mcp_tools.search_repository") as search:
            with self.assertRaises(Exception):
                asyncio.run(mcp_server.mcp.call_tool(
                    "search_code", {"repository_path": "C:/repo", "query": "x", "top_k": 99}))
        search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
