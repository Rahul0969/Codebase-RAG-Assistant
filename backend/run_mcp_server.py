r"""Launcher so an MCP client can start the server without setting a working directory.

Usage (PowerShell):  .\.venv\Scripts\python.exe run_mcp_server.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.mcp_server import main  # noqa: E402

if __name__ == "__main__":
    main()
