"""Tree-sitter based, syntax-aware source-code chunking."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .repository import inspect_repository

try:
    from tree_sitter_language_pack import get_parser
except ImportError:  # Keep API importable and provide a helpful setup error.
    get_parser = None

# Keep this list deliberately focused on common programming languages.
# Unsupported repository file types are reported instead of guessed.
EXTENSION_LANGUAGES = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cs": "c_sharp",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
}

# Tree-sitter node names that represent useful, independently meaningful units.
DEFINITION_NODES = {
    "function_definition", "async_function_definition", "class_definition",
    "function_declaration", "generator_function_declaration", "class_declaration",
    "method_definition", "method_declaration", "constructor_declaration",
    "interface_declaration", "struct_item", "enum_item", "trait_item",
    "impl_item", "function_item", "function", "method", "class",
    "struct_specifier", "enum_specifier", "namespace_definition",
}

MAX_SOURCE_BYTES = 1_000_000
MAX_CHUNKS = 2_000
DEFAULT_MAX_CHARS = 6_000
MIN_MAX_CHARS = 500
MAX_MAX_CHARS = 12_000


def _node_children(node: Any) -> list[Any]:
    return list(getattr(node, "children", []) or [])


def _definition_nodes(root_node: Any) -> list[Any]:
    """Return definition nodes, preferring inner definitions over containers.

    If a class contains methods, methods are emitted as separate chunks and the
    class container is omitted to avoid indexing the same source lines twice.
    Classes without nested definitions remain useful chunks themselves.
    """
    found: list[Any] = []

    def walk(node: Any) -> bool:
        children = _node_children(node)
        descendant_has_definition = False
        for child in children:
            if walk(child):
                descendant_has_definition = True

        if getattr(node, "type", "") in DEFINITION_NODES:
            if not descendant_has_definition:
                found.append(node)
            return True
        return descendant_has_definition

    walk(root_node)
    found.sort(key=lambda item: (item.start_byte, item.end_byte))
    return found


def _symbol_name(node: Any, source: bytes) -> str | None:
    """Read a definition's name field where the grammar provides one."""
    try:
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            return source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
    except (AttributeError, TypeError):
        pass
    return None


def _make_chunk(path: str, language: str, kind: str, symbol: str | None,
                start_line: int, end_line: int, content: str,
                parse_has_error: bool) -> dict:
    digest_input = f"{path}:{start_line}:{end_line}:{content}".encode("utf-8")
    return {
        "chunk_id": hashlib.sha256(digest_input).hexdigest()[:16],
        "file_path": path,
        "language": language,
        "kind": kind,
        "symbol": symbol,
        "start_line": start_line,
        "end_line": end_line,
        "content": content,
        "parse_has_error": parse_has_error,
    }


def _emit_chunk(path: str, language: str, kind: str, symbol: str | None,
                first_line: int, lines: list[str], parse_has_error: bool) -> list[dict]:
    """Build one chunk, trimming blank edge lines while keeping line numbers exact.

    Trimming must move start_line/end_line together with the content. Otherwise
    the stored range would not match the stored text, and citations would point
    at the wrong lines.
    """
    start = 0
    end = len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    if start >= end:
        return []
    content = "".join(lines[start:end]).rstrip("\r\n")
    return [_make_chunk(path, language, kind, symbol,
                        first_line + start, first_line + end - 1,
                        content, parse_has_error)]


def _split_text(path: str, language: str, kind: str, symbol: str | None,
                start_line: int, text: str, max_chars: int,
                parse_has_error: bool) -> list[dict]:
    """Split oversized syntax nodes on line boundaries, preserving line numbers."""
    lines = text.splitlines(keepends=True)
    if not lines:
        return []
    chunks: list[dict] = []
    current: list[str] = []
    current_length = 0
    chunk_start = start_line

    for index, line in enumerate(lines):
        if current and current_length + len(line) > max_chars:
            chunks.extend(_emit_chunk(path, language, kind, symbol, chunk_start,
                                      current, parse_has_error))
            current = []
            current_length = 0
            chunk_start = start_line + index
        # A single exceptionally long line is retained as one chunk.
        current.append(line)
        current_length += len(line)

    chunks.extend(_emit_chunk(path, language, kind, symbol, chunk_start,
                              current, parse_has_error))
    return chunks


def chunk_source_file(file_path: Path, relative_path: str,
                      max_chars: int = DEFAULT_MAX_CHARS) -> list[dict]:
    """Parse one source file and return AST-aware chunks with line metadata."""
    if max_chars < MIN_MAX_CHARS or max_chars > MAX_MAX_CHARS:
        raise ValueError(f"max_chars must be between {MIN_MAX_CHARS} and {MAX_MAX_CHARS}.")

    language = EXTENSION_LANGUAGES.get(file_path.suffix.lower())
    if language is None:
        return []
    if get_parser is None:
        raise RuntimeError(
            "Tree-sitter is not installed. Run 'python -m pip install -r backend/requirements.txt'."
        )

    raw = file_path.read_bytes()
    if not raw or len(raw) > MAX_SOURCE_BYTES:
        return []
    # Ignore files that are not valid UTF-8 rather than indexing binary data.
    try:
        source_text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return []
    source = source_text.encode("utf-8")

    try:
        parser = get_parser(language)
        tree = parser.parse(source)
    except Exception as error:
        # Unknown grammar names or parser errors should not crash the whole scan.
        raise ValueError(f"Could not parse {relative_path} as {language}: {error}") from error

    root_node = tree.root_node
    parse_has_error = bool(getattr(root_node, "has_error", False))
    definitions = _definition_nodes(root_node)
    chunks: list[dict] = []

    for node in definitions:
        start_byte = node.start_byte
        end_byte = node.end_byte
        if end_byte <= start_byte:
            continue
        snippet = source[start_byte:end_byte].decode("utf-8", errors="replace")
        start_line = node.start_point.row + 1
        kind = node.type
        symbol = _symbol_name(node, source)
        chunks.extend(_split_text(relative_path, language, kind, symbol,
                                  start_line, snippet, max_chars, parse_has_error))

    # Files without recognized definitions (scripts, config-like code, etc.)
    # still get useful line-based chunks rather than disappearing.
    if not chunks:
        chunks = _split_text(relative_path, language, "module", None, 1,
                             source_text, max_chars, parse_has_error)
    return chunks


def chunk_repository(repository_path: str,
                     max_chars: int = DEFAULT_MAX_CHARS) -> dict:
    """Inspect and chunk a repository without following links or leaving its root."""
    if max_chars < MIN_MAX_CHARS or max_chars > MAX_MAX_CHARS:
        raise ValueError(f"max_chars must be between {MIN_MAX_CHARS} and {MAX_MAX_CHARS}.")

    inspection = inspect_repository(repository_path)
    root = Path(repository_path).expanduser().resolve(strict=True)
    chunks: list[dict] = []
    skipped_files: list[dict[str, str]] = []

    for item in inspection["files"]:
        relative_path = item["path"]
        candidate = root / Path(relative_path)
        try:
            # Re-check every path immediately before reading it. This protects
            # against links and path escapes introduced after initial inspection.
            if candidate.is_symlink():
                skipped_files.append({"path": relative_path, "reason": "symbolic link"})
                continue
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
            if not resolved.is_file():
                continue
            if resolved.stat().st_size > MAX_SOURCE_BYTES:
                skipped_files.append({"path": relative_path, "reason": "file exceeds 1 MB limit"})
                continue
            language = EXTENSION_LANGUAGES.get(resolved.suffix.lower())
            if language is None:
                skipped_files.append({"path": relative_path, "reason": "language not supported by chunker"})
                continue
            file_chunks = chunk_source_file(resolved, relative_path, max_chars)
            chunks.extend(file_chunks)
        except (OSError, ValueError) as error:
            skipped_files.append({"path": relative_path, "reason": str(error)[:200]})
        if len(chunks) >= MAX_CHUNKS:
            chunks = chunks[:MAX_CHUNKS]
            break

    return {
        "repository_name": inspection["repository_name"],
        "file_count_scanned": len(inspection["files"]),
        "chunk_count": len(chunks),
        "truncated": inspection["truncated"] or len(chunks) >= MAX_CHUNKS,
        "max_chars": max_chars,
        "chunks": chunks,
        "skipped_files": skipped_files,
    }
