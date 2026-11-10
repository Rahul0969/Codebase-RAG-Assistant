"""FastAPI application: the local API used by the web UI.

Workflow: GET /health -> POST /repository/inspect -> /repository/index ->
/repository/search or /repository/ask. Every error response has a human-readable
`detail` string and an `X-Error-Code` header the UI can rely on.
"""
from __future__ import annotations

import importlib.util
from typing import Annotated

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import allowed_hosts, load_env_file, trusted_origins
from .repository import inspect_repository
from .chunker import chunk_repository, DEFAULT_MAX_CHARS, MIN_MAX_CHARS, MAX_MAX_CHARS
from .embedding_service import (
    index_repository, search_repository, get_index_info,
    DEFAULT_BATCH_SIZE, DEFAULT_EMBEDDING_MODEL,
)
from .llm_service import (
    LLMConfigError, LLMError, OllamaModelNotFoundError, OllamaResponseError,
    OllamaTimeoutError, OllamaUnavailableError, check_ollama, get_settings,
)
from .security import PathNotAllowedError, validate_repository_path
from .security_middleware import LocalAccessMiddleware
from .rag_service import ask_repository, DEFAULT_TOP_K as ASK_DEFAULT_TOP_K, MAX_TOP_K as ASK_MAX_TOP_K
from .report_service import REPORT_DIR, generate_report, list_reports, read_report
from .impact_service import analyze_change_impact

API_VERSION = "1.0.0"

load_env_file()  # optional backend/.env (OLLAMA_* and RAG_* names only)

app = FastAPI(
    title="Codebase RAG Assistant API",
    description="Local-first API for understanding and searching code repositories.",
    version=API_VERSION,
)

# CORS decides what a *browser page* may read. It is not the security boundary by itself:
# LocalAccessMiddleware (added last, so it runs first) also rejects bad Host and Origin headers.
# No cookies or credentials are used, so allow_credentials stays False.
app.add_middleware(
    CORSMiddleware,
    allow_origins=trusted_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
    expose_headers=["X-Error-Code"],
    max_age=600,
)
app.add_middleware(LocalAccessMiddleware, allowed_hosts=allowed_hosts(), trusted_origins=trusted_origins())


# ---------------------------------------------------------------------------
# Error translation
# ---------------------------------------------------------------------------
def _error(status_code: int, message: str, code: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=message, headers={"X-Error-Code": code})


def _safe_repo(repository_path: str) -> str:
    """Validate the folder (no system/credential folders, links, roots) and return its resolved path."""
    try:
        return str(validate_repository_path(repository_path))
    except PathNotAllowedError as error:
        raise _error(400, str(error), "repository_path_invalid") from error


def _translate(error: Exception) -> HTTPException:
    """Map service exceptions to an HTTP error. Messages are already safe to show."""
    message = str(error)
    if isinstance(error, OllamaTimeoutError):
        return _error(504, message, "llm_timeout")
    if isinstance(error, OllamaResponseError):
        return _error(502, message, "llm_bad_response")
    if isinstance(error, OllamaModelNotFoundError):
        return _error(503, message, "model_not_found")
    if isinstance(error, OllamaUnavailableError):
        return _error(503, message, "ollama_unavailable")
    if isinstance(error, LLMConfigError):
        return _error(503, message, "llm_config_invalid")
    if isinstance(error, LLMError):
        return _error(503, message, "llm_error")
    if isinstance(error, ValueError):
        if "no index" in message.lower():
            return _error(400, message, "not_indexed")
        return _error(400, message, "invalid_request")
    return _error(503, message, "service_unavailable")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
class OllamaHealth(BaseModel):
    reachable: bool
    model: str | None = None
    model_available: bool | None = None
    message: str | None = None


class EmbeddingHealth(BaseModel):
    model: str
    installed: bool
    loaded: bool = False
    note: str


class ChromaHealth(BaseModel):
    installed: bool


class HealthResponse(BaseModel):
    status: str
    version: str
    ollama: OllamaHealth
    embedding: EmbeddingHealth
    chromadb: ChromaHealth


@app.get("/", tags=["health"])
def root() -> dict[str, str]:
    """Basic welcome endpoint."""
    return {"message": "Codebase RAG Assistant API is running."}


def _is_installed(module_name: str) -> bool:
    """True if a package can be imported, without importing it (no heavy start-up)."""
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ValueError):
        return False


def _ollama_health() -> dict:
    try:
        settings = get_settings()
    except LLMError as error:
        return {"reachable": False, "model": None, "model_available": None, "message": str(error)}
    try:
        info = check_ollama(settings, timeout=2.0)
    except LLMError as error:
        return {"reachable": False, "model": settings.model, "model_available": None, "message": str(error)}
    message = None if info["model_available"] else (
        f"Model '{settings.model}' is not downloaded. Run: ollama pull {settings.model}")
    return {"reachable": True, "model": settings.model,
            "model_available": info["model_available"], "message": message}


@app.get("/health", tags=["health"], response_model=HealthResponse)
def health() -> dict:
    """Lightweight status check. Never loads models or opens the vector database."""
    return {
        "status": "ok",
        "version": API_VERSION,
        "ollama": _ollama_health(),
        "embedding": {
            "model": DEFAULT_EMBEDDING_MODEL,
            "installed": _is_installed("sentence_transformers"),
            "loaded": False,
            "note": "The embedding model is loaded the first time you index or search.",
        },
        "chromadb": {"installed": _is_installed("chromadb")},
    }


# ---------------------------------------------------------------------------
# Repository inspection and chunk preview
# ---------------------------------------------------------------------------
class RepositoryRequest(BaseModel):
    repository_path: str = Field(min_length=1, max_length=4096)


class FileEntry(BaseModel):
    path: str
    extension: str


class InspectResponse(BaseModel):
    repository_name: str
    file_count: int
    truncated: bool
    skipped_directories: list[str] = []
    files: list[FileEntry]


@app.post("/repository/inspect", tags=["repository"], response_model=InspectResponse)
def inspect_repository_endpoint(request: RepositoryRequest) -> dict:
    """List supported source-file paths in a selected local repository."""
    try:
        return inspect_repository(_safe_repo(request.repository_path))
    except (ValueError, RuntimeError) as error:
        raise _translate(error) from error


class ChunkRequest(BaseModel):
    repository_path: str = Field(min_length=1, max_length=4096)
    max_chars: int = Field(default=DEFAULT_MAX_CHARS, ge=MIN_MAX_CHARS, le=MAX_MAX_CHARS)


@app.post("/repository/chunk", tags=["repository"])
def chunk_repository_endpoint(request: ChunkRequest) -> dict:
    """Create syntax-aware chunks for supported source files in a repository."""
    try:
        return chunk_repository(_safe_repo(request.repository_path), request.max_chars)
    except (ValueError, RuntimeError) as error:
        raise _translate(error) from error


# ---------------------------------------------------------------------------
# Indexing and search
# ---------------------------------------------------------------------------
class IndexRequest(BaseModel):
    repository_path: str = Field(min_length=1, max_length=4096)
    max_chars: int = Field(default=DEFAULT_MAX_CHARS, ge=MIN_MAX_CHARS, le=MAX_MAX_CHARS)
    batch_size: int = Field(default=DEFAULT_BATCH_SIZE, ge=1, le=32)


class SkippedFile(BaseModel):
    path: str
    reason: str


class IndexResponse(BaseModel):
    repository_name: str
    file_count_scanned: int
    chunk_count: int
    indexed_count: int
    removed_stale_count: int
    embedding_model: str
    embedding_dimensions: int
    storage: str
    truncated: bool
    skipped_files: list[SkippedFile] = []


@app.post("/repository/index", tags=["indexing"], response_model=IndexResponse)
def index_repository_endpoint(request: IndexRequest) -> dict:
    """Create local embeddings for repository chunks and persist them in ChromaDB."""
    try:
        return index_repository(
            _safe_repo(request.repository_path),
            max_chars=request.max_chars,
            batch_size=request.batch_size,
        )
    except (ValueError, RuntimeError) as error:
        raise _translate(error) from error


class IndexStatusResponse(BaseModel):
    indexed: bool
    chunk_count: int
    file_count: int
    languages: dict[str, int] = {}
    kinds: dict[str, int] = {}
    symbol_count: int = 0
    embedding_model: str | None = None


@app.post("/repository/status", tags=["indexing"], response_model=IndexStatusResponse)
def repository_status_endpoint(request: RepositoryRequest) -> dict:
    """Report whether a repository already has a local index (does not load the model)."""
    try:
        return get_index_info(_safe_repo(request.repository_path))
    except (ValueError, RuntimeError) as error:
        raise _translate(error) from error


class SearchRequest(BaseModel):
    repository_path: str = Field(min_length=1, max_length=4096)
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=20)


class SearchMatch(BaseModel):
    chunk_id: str
    content: str
    file_path: str
    language: str
    kind: str
    symbol: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    parse_has_error: bool = False
    distance: float
    similarity: float


class SearchResponse(BaseModel):
    repository_name: str
    query: str
    result_count: int
    embedding_model: str
    matches: list[SearchMatch]


@app.post("/repository/search", tags=["search"], response_model=SearchResponse)
def search_repository_endpoint(request: SearchRequest) -> dict:
    """Search indexed code chunks using semantic similarity."""
    try:
        return search_repository(
            _safe_repo(request.repository_path), query=request.query, top_k=request.top_k
        )
    except (ValueError, RuntimeError) as error:
        raise _translate(error) from error


# ---------------------------------------------------------------------------
# RAG question answering
# ---------------------------------------------------------------------------
class SourceInfo(BaseModel):
    source_id: int
    file_path: str
    language: str
    symbol: str | None = None
    kind: str
    start_line: int
    end_line: int
    similarity: float


class Citation(BaseModel):
    text: str
    file_path: str
    start_line: int
    end_line: int
    valid: bool
    reason: str
    source_id: int | None = None


class RetrievedChunk(SourceInfo):
    context_start_line: int
    context_end_line: int
    cited: bool
    content: str | None = None


class EvidenceCoverage(BaseModel):
    retrieved_sources: int
    sources_cited: int
    cited_source_ids: list[int]
    claim_sentences: int
    cited_claim_sentences: int
    uncited_claim_examples: list[str]


class AskRequest(BaseModel):
    repository_path: str = Field(min_length=1, max_length=4096)
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=ASK_DEFAULT_TOP_K, ge=1, le=ASK_MAX_TOP_K)
    include_source_text: bool = False


class AskResponse(BaseModel):
    repository_name: str
    question: str
    answer: str
    model: str
    evidence_status: str
    success: bool
    retrieved_count: int
    used_chunk_count: int
    sources: list[SourceInfo]
    context_chars: int
    context_truncated: bool
    embedding_model: str
    validation_passed: bool
    citations: list[Citation]
    unsupported_citations: list[Citation]
    unsupported_identifiers: list[str]
    evidence_coverage: EvidenceCoverage
    evidence_summary: str
    retrieved_chunks: list[RetrievedChunk]


@app.post("/repository/ask", tags=["rag"], response_model=AskResponse)
def ask_repository_endpoint(request: AskRequest) -> dict:
    """Answer a question about an indexed repository using retrieved code and a local LLM."""
    try:
        return ask_repository(
            _safe_repo(request.repository_path), request.question, top_k=request.top_k,
            include_source_text=request.include_source_text,
        )
    except (ValueError, RuntimeError) as error:
        raise _translate(error) from error


@app.get("/llm/status", tags=["rag"])
def llm_status_endpoint() -> dict:
    """Check that Ollama is running locally and the configured model is downloaded."""
    try:
        return check_ollama()
    except LLMError as error:
        raise _translate(error) from error


# ---------------------------------------------------------------------------
# Repository intelligence reports (C11)
# ---------------------------------------------------------------------------
class ReportRequest(BaseModel):
    repository_path: str = Field(min_length=1, max_length=4096)
    format: str = Field(default="md", pattern=r"^(md|html|json)$")
    use_ai_summary: bool = True


class ReportResponse(BaseModel):
    report_id: str
    repository_name: str
    generated_at: str
    format: str
    filename: str
    mime_type: str
    content: str
    summary_source: str


@app.post("/api/reports/generate", tags=["reports"], response_model=ReportResponse)
def generate_repository_report_endpoint(request: ReportRequest) -> dict:
    """Generate a locally stored repository report in Markdown, HTML or JSON."""
    try:
        return generate_report(
            _safe_repo(request.repository_path),
            report_format=request.format,
            use_ai_summary=request.use_ai_summary,
        )
    except (ValueError, RuntimeError) as error:
        raise _translate(error) from error


@app.get("/api/reports", tags=["reports"])
def list_repository_reports_endpoint() -> dict:
    """List report metadata without exposing local storage paths."""
    return {"reports": list_reports()}


@app.get("/api/reports/{report_id}", tags=["reports"])
def get_repository_report_endpoint(report_id: str) -> dict:
    """Retrieve a generated report's text content and safe metadata."""
    try:
        content, mime_type, filename = read_report(report_id)
    except FileNotFoundError as error:
        raise _error(404, str(error), "report_not_found") from error
    return {"report_id": report_id, "filename": filename, "mime_type": mime_type, "content": content}


@app.get("/api/reports/{report_id}/download", tags=["reports"])
def download_repository_report_endpoint(report_id: str) -> FileResponse:
    """Download a generated report by its opaque ID."""
    try:
        _content, mime_type, filename = read_report(report_id)
        path = (REPORT_DIR / filename).resolve(strict=True)
        path.relative_to(REPORT_DIR.resolve())
    except (FileNotFoundError, OSError, ValueError) as error:
        raise _error(404, "Report not found.", "report_not_found") from error
    return FileResponse(path, media_type=mime_type, filename=filename)


# ---------------------------------------------------------------------------
# Code change impact analysis (C12)
# ---------------------------------------------------------------------------
class ImpactRequest(BaseModel):
    repository_path: str = Field(min_length=1, max_length=4096)
    changed_files: list[Annotated[str, Field(min_length=1, max_length=1024)]] = Field(min_length=1, max_length=20)


@app.post("/repository/impact", tags=["analysis"])
def repository_impact_endpoint(request: ImpactRequest) -> dict:
    """Find likely direct/transitive dependents and related tests for changed files."""
    try:
        return analyze_change_impact(_safe_repo(request.repository_path), request.changed_files)
    except (ValueError, RuntimeError) as error:
        raise _translate(error) from error
