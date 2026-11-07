"""Plain-Python implementations of the MCP tools.

Keeping the logic here (not inside the MCP server module) means it can be tested
without the MCP SDK, and the server stays a thin registration layer. Every tool:
validates its inputs, reuses the existing service functions, returns small
JSON-friendly dicts, and raises McpToolError with a message that is safe to show.
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from .chunker import DEFAULT_MAX_CHARS, MAX_MAX_CHARS, MIN_MAX_CHARS
from .embedding_service import (
    DEFAULT_BATCH_SIZE, get_index_info, index_repository, search_repository,
)
from .llm_service import LLMError
from .rag_service import MAX_QUESTION_CHARS, MAX_TOP_K as ASK_MAX_TOP_K, ask_repository
from .repository import inspect_repository
from .security import PathNotAllowedError, redact_secrets, validate_repository_path

logger = logging.getLogger(__name__)

MAX_FILES_RETURNED = 300
MAX_SKIPPED_RETURNED = 50
MAX_SEARCH_CONTENT_CHARS = 1500
MAX_QUERY_CHARS = 4000
SEARCH_MAX_TOP_K = 20
NOTABLE_FILENAMES = {
    "readme.md", "readme.rst", "readme.txt", "main.py", "app.py", "manage.py", "__main__.py",
    "index.js", "index.ts", "main.js", "main.ts", "server.js", "app.js", "main.go", "main.rs",
    "program.cs", "pom.xml", "package.json", "pyproject.toml", "requirements.txt", "cargo.toml",
    "go.mod", "dockerfile", "makefile",
}


class McpToolError(Exception):
    """An error whose message is safe to return to an MCP client."""


def _int_in_range(name: str, value: Any, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise McpToolError(f"{name} must be a whole number.")
    if value < minimum or value > maximum:
        raise McpToolError(f"{name} must be between {minimum} and {maximum}.")
    return value


def _text(name: str, value: Any, max_chars: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise McpToolError(f"{name} must not be empty.")
    cleaned = value.strip()
    if len(cleaned) > max_chars:
        raise McpToolError(f"{name} must be {max_chars} characters or fewer.")
    return cleaned


def _repo(repository_path: Any) -> str:
    try:
        return str(validate_repository_path(repository_path))
    except PathNotAllowedError as error:
        raise McpToolError(str(error)) from None


def _guard(action: str, call):
    """Run a service call and convert any failure into a safe McpToolError."""
    try:
        return call()
    except McpToolError:
        raise
    except (ValueError, LLMError, RuntimeError) as error:
        # Service-layer messages were written to be shown to users (no paths, no traces).
        raise McpToolError(str(error)) from None
    except Exception as error:  # noqa: BLE001 - never leak internals to the client
        logger.error("MCP tool %s failed: %s", action, type(error).__name__)
        raise McpToolError(f"{action} failed unexpectedly. Check the server's terminal output.") from None


def inspect_repository_tool(repository_path: str) -> dict:
    """List supported source files (paths only; file contents are not read)."""
    repo = _repo(repository_path)
    result = _guard("inspect_repository", lambda: inspect_repository(repo))
    files = result["files"]
    extensions = Counter(item["extension"] for item in files)
    return {
        "repository_name": result["repository_name"],
        "file_count": result["file_count"],
        "truncated": result["truncated"],
        "extension_counts": dict(extensions.most_common()),
        "files": files[:MAX_FILES_RETURNED],
        "files_omitted": max(0, len(files) - MAX_FILES_RETURNED),
        "skipped_directories": result["skipped_directories"][:MAX_SKIPPED_RETURNED],
    }


def index_repository_tool(repository_path: str, max_chars: int = DEFAULT_MAX_CHARS,
                          batch_size: int = DEFAULT_BATCH_SIZE) -> dict:
    """Chunk, embed and store a repository in the local ChromaDB index."""
    repo = _repo(repository_path)
    max_chars = _int_in_range("max_chars", max_chars, MIN_MAX_CHARS, MAX_MAX_CHARS)
    batch_size = _int_in_range("batch_size", batch_size, 1, 32)
    result = _guard("index_repository",
                    lambda: index_repository(repo, max_chars=max_chars, batch_size=batch_size))
    skipped = result.get("skipped_files", [])
    return {**result, "skipped_files": skipped[:MAX_SKIPPED_RETURNED],
            "skipped_files_omitted": max(0, len(skipped) - MAX_SKIPPED_RETURNED)}


def search_code_tool(repository_path: str, query: str, top_k: int = 5) -> dict:
    """Semantic search over the indexed repository (secrets masked, long code shortened)."""
    repo = _repo(repository_path)
    query = _text("query", query, MAX_QUERY_CHARS)
    top_k = _int_in_range("top_k", top_k, 1, SEARCH_MAX_TOP_K)
    result = _guard("search_code", lambda: search_repository(repo, query=query, top_k=top_k))
    matches = []
    for match in result["matches"]:
        content = redact_secrets(match.get("content", ""))
        shortened = len(content) > MAX_SEARCH_CONTENT_CHARS
        matches.append({
            "file_path": match.get("file_path"),
            "language": match.get("language"),
            "symbol": match.get("symbol"),
            "kind": match.get("kind"),
            "start_line": match.get("start_line"),
            "end_line": match.get("end_line"),
            "citation": f"{match.get('file_path')}:{match.get('start_line')}-{match.get('end_line')}",
            "similarity": round(float(match.get("similarity", 0.0)), 4),
            "content": content[:MAX_SEARCH_CONTENT_CHARS],
            "content_shortened": shortened,
        })
    return {"repository_name": result["repository_name"], "query": result["query"],
            "result_count": len(matches), "matches": matches}


def ask_codebase_tool(repository_path: str, question: str, top_k: int = 5) -> dict:
    """Ask a question; the local model answers from retrieved code with checked citations."""
    repo = _repo(repository_path)
    question = _text("question", question, MAX_QUESTION_CHARS)
    top_k = _int_in_range("top_k", top_k, 1, ASK_MAX_TOP_K)
    result = _guard("ask_codebase", lambda: ask_repository(repo, question, top_k=top_k))
    return {
        "answer": result["answer"],
        "evidence_status": result["evidence_status"],
        "validation_passed": result["validation_passed"],
        "evidence_summary": result["evidence_summary"],
        "citations": [{"text": c["text"], "valid": c["valid"], "reason": c["reason"]}
                      for c in result["citations"]],
        "unsupported_citations": [c["text"] for c in result["unsupported_citations"]],
        "unsupported_identifiers": result["unsupported_identifiers"],
        "sources": result["sources"],
        "model": result["model"],
        "repository_name": result["repository_name"],
    }


def get_repository_summary_tool(repository_path: str) -> dict:
    """Facts only: file layout from inspection plus index statistics. No AI-written text."""
    repo = _repo(repository_path)
    inspection = _guard("get_repository_summary", lambda: inspect_repository(repo))
    index = _guard("get_repository_summary", lambda: get_index_info(repo))
    files = inspection["files"]
    top_level = Counter(item["path"].split("/", 1)[0] if "/" in item["path"] else "(root files)"
                        for item in files)
    notable = [item["path"] for item in files
               if item["path"].rsplit("/", 1)[-1].lower() in NOTABLE_FILENAMES][:30]
    return {
        "repository_name": inspection["repository_name"],
        "file_count": inspection["file_count"],
        "scan_truncated": inspection["truncated"],
        "extension_counts": dict(Counter(item["extension"] for item in files).most_common()),
        "top_level_entries": dict(top_level.most_common(30)),
        "notable_files_by_name": notable,
        "index": index,
        "note": ("Counts come from file names and the vector index. File contents are not summarized "
                 "here; use ask_codebase for explanations." if index["indexed"] else
                 "This repository is not indexed yet. Run index_repository to enable search_code and ask_codebase."),
    }
