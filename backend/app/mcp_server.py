"""MCP server (stdio) exposing the Codebase RAG Assistant as tools.

Start it from the backend folder:  python -m app.mcp_server
or through the launcher:           python run_mcp_server.py

Trust boundary: the server speaks over stdin/stdout to the MCP client that
launched it (no network port is opened). Anything that client asks is limited to
five fixed tools; no tool runs commands or executes repository code. All
processing, embeddings and the LLM stay on this computer.
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Annotated

# Chroma sends anonymous usage statistics unless told otherwise; this app is local-first.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
# stdout carries the MCP protocol, so all logging must go to stderr.
logging.basicConfig(stream=sys.stderr, level=logging.WARNING)

from mcp.server.fastmcp import FastMCP  # noqa: E402
from pydantic import Field  # noqa: E402

from . import mcp_tools  # noqa: E402

SERVER_NAME = "codebase-rag-assistant"
INSTRUCTIONS = (
    "Local tools for understanding a code repository. Typical order: inspect_repository, "
    "index_repository (once, and again after code changes), then search_code or ask_codebase. "
    "repository_path must be an absolute path to a project folder on this computer. "
    "Answers from ask_codebase include citations like [src/app.py:10-25]; check evidence_status "
    "before trusting an answer."
)

mcp = FastMCP(SERVER_NAME, instructions=INSTRUCTIONS)

RepoPath = Annotated[str, Field(min_length=1, max_length=4096,
                                description="Absolute path of the repository folder on this computer.")]


@mcp.tool(description="List the supported source files in a local repository (paths and counts only; "
                      "file contents are not read). Skips dependency, build, secret and link paths.")
def inspect_repository(repository_path: RepoPath) -> dict:
    return mcp_tools.inspect_repository_tool(repository_path)


@mcp.tool(description="Parse, chunk, embed and index a repository into the local vector database so it "
                      "can be searched. Can take minutes on large repositories and the first run "
                      "downloads the embedding model. Re-run after code changes.")
def index_repository(
    repository_path: RepoPath,
    max_chars: Annotated[int, Field(ge=500, le=12000, description="Maximum characters per chunk.")] = 6000,
    batch_size: Annotated[int, Field(ge=1, le=32, description="Embedding batch size (keep small on low RAM).")] = 8,
) -> dict:
    return mcp_tools.index_repository_tool(repository_path, max_chars, batch_size)


@mcp.tool(description="Search the indexed repository with a natural-language query. Returns matching "
                      "code with file path, symbol, line range, a citation string and similarity.")
def search_code(
    repository_path: RepoPath,
    query: Annotated[str, Field(min_length=1, max_length=4000, description="What to look for, in plain language.")],
    top_k: Annotated[int, Field(ge=1, le=20, description="Number of matches to return.")] = 5,
) -> dict:
    return mcp_tools.search_code_tool(repository_path, query, top_k)


@mcp.tool(description="Ask a question about the repository. A local Ollama model answers using only "
                      "retrieved code and cites [file:start-end]; citations are verified against the "
                      "retrieved code. Requires indexing and a running Ollama. May take up to a minute or two.")
def ask_codebase(
    repository_path: RepoPath,
    question: Annotated[str, Field(min_length=1, max_length=2000, description="Your question about the code.")],
    top_k: Annotated[int, Field(ge=1, le=10, description="How many code chunks to retrieve as evidence.")] = 5,
) -> dict:
    return mcp_tools.ask_codebase_tool(repository_path, question, top_k)


@mcp.tool(description="Factual summary of a repository: file counts by type, top-level folders, notable "
                      "files by name, and whether/how it is indexed. No AI-generated content.")
def get_repository_summary(repository_path: RepoPath) -> dict:
    return mcp_tools.get_repository_summary_tool(repository_path)


def main() -> None:
    """Run the server over stdio (the transport MCP clients use for local servers)."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
