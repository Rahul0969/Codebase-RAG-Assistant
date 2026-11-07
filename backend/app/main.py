from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .repository import inspect_repository
from .chunker import chunk_repository, DEFAULT_MAX_CHARS, MIN_MAX_CHARS, MAX_MAX_CHARS
from .embedding_service import index_repository, search_repository, DEFAULT_BATCH_SIZE

app = FastAPI(
    title="Codebase RAG Assistant API",
    description="Local-first API for understanding and searching code repositories.",
    version="0.4.0",
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
