from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .repository import inspect_repository
from .chunker import chunk_repository, DEFAULT_MAX_CHARS, MIN_MAX_CHARS, MAX_MAX_CHARS
from .embedding_service import index_repository, search_repository, DEFAULT_BATCH_SIZE
from .llm_service import (
    LLMError, OllamaResponseError, OllamaTimeoutError,
    check_ollama,
)
from .rag_service import ask_repository, DEFAULT_TOP_K as ASK_DEFAULT_TOP_K, MAX_TOP_K as ASK_MAX_TOP_K

app = FastAPI(
    title="Codebase RAG Assistant API",
    description="Local-first API for understanding and searching code repositories.",
    version="0.6.0",
)

# Vite's development server runs on port 5173 by default.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class RepositoryRequest(BaseModel):
    repository_path: str = Field(min_length=1, max_length=4096)


@app.get("/", tags=["health"])
def root() -> dict[str, str]:
    """Basic welcome endpoint."""
    return {"message": "Codebase RAG Assistant API is running."}


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Lightweight health check for local development."""
    return {"status": "ok"}


@app.post("/repository/inspect", tags=["repository"])
def inspect_repository_endpoint(request: RepositoryRequest) -> dict:
    """List supported source-file paths in a selected local repository."""
    try:
        return inspect_repository(request.repository_path)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


class ChunkRequest(BaseModel):
    repository_path: str = Field(min_length=1, max_length=4096)
    max_chars: int = Field(default=DEFAULT_MAX_CHARS, ge=MIN_MAX_CHARS, le=MAX_MAX_CHARS)


@app.post("/repository/chunk", tags=["repository"])
def chunk_repository_endpoint(request: ChunkRequest) -> dict:
    """Create syntax-aware chunks for supported source files in a repository."""
    try:
        return chunk_repository(request.repository_path, request.max_chars)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


class IndexRequest(BaseModel):
    repository_path: str = Field(min_length=1, max_length=4096)
    max_chars: int = Field(default=DEFAULT_MAX_CHARS, ge=MIN_MAX_CHARS, le=MAX_MAX_CHARS)
    batch_size: int = Field(default=DEFAULT_BATCH_SIZE, ge=1, le=32)


@app.post("/repository/index", tags=["indexing"])
def index_repository_endpoint(request: IndexRequest) -> dict:
    """Create local embeddings for repository chunks and persist them in ChromaDB."""
    try:
        return index_repository(
            request.repository_path,
            max_chars=request.max_chars,
            batch_size=request.batch_size,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


class SearchRequest(BaseModel):
    repository_path: str = Field(min_length=1, max_length=4096)
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=20)


@app.post("/repository/search", tags=["search"])
def search_repository_endpoint(request: SearchRequest) -> dict:
    """Search indexed code chunks using semantic similarity."""
    try:
        return search_repository(
            request.repository_path, query=request.query, top_k=request.top_k
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


class SourceInfo(BaseModel):
    source_id: int
    file_path: str
    language: str
    symbol: str | None = None
    kind: str
    start_line: int
    end_line: int
    similarity: float


class AskRequest(BaseModel):
    repository_path: str = Field(min_length=1, max_length=4096)
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=ASK_DEFAULT_TOP_K, ge=1, le=ASK_MAX_TOP_K)


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


def _llm_http_error(error: LLMError) -> HTTPException:
    """Map local-LLM failures to status codes without leaking internals."""
    if isinstance(error, OllamaTimeoutError):
        return HTTPException(status_code=504, detail=str(error))
    if isinstance(error, OllamaResponseError):
        return HTTPException(status_code=502, detail=str(error))
    return HTTPException(status_code=503, detail=str(error))


@app.post("/repository/ask", tags=["rag"], response_model=AskResponse)
def ask_repository_endpoint(request: AskRequest) -> dict:
    """Answer a question about an indexed repository using retrieved code and a local LLM."""
    try:
        return ask_repository(request.repository_path, request.question, top_k=request.top_k)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except LLMError as error:
        raise _llm_http_error(error) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/llm/status", tags=["rag"])
def llm_status_endpoint() -> dict:
    """Check that Ollama is running locally and the configured model is downloaded."""
    try:
        return check_ollama()
    except LLMError as error:
        raise _llm_http_error(error) from error
