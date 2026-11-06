"""Local sentence-transformer embeddings and persistent Chroma indexing."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .chunker import chunk_repository

DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_BATCH_SIZE = 8  # conservative for machines with limited RAM
DEFAULT_PERSIST_DIRECTORY = Path(__file__).resolve().parents[1] / "data" / "chroma_db"


def _load_embedding_model(model_name: str = DEFAULT_EMBEDDING_MODEL) -> Any:
    """Load the embedding model only when indexing is requested."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as error:
        raise RuntimeError(
            "sentence-transformers is not installed. Run 'python -m pip install -r backend/requirements.txt'."
        ) from error
    try:
        return SentenceTransformer(model_name, device="cpu")
    except Exception as error:
        raise RuntimeError(
            f"Could not load embedding model '{model_name}'. Check internet access for the first download, "
            "then retry. The model is cached for later runs."
        ) from error


def _get_collection(repository_path: str, persist_directory: Path, model_name: str):
    try:
        import chromadb
    except ImportError as error:
        raise RuntimeError(
            "ChromaDB is not installed. Run 'python -m pip install -r backend/requirements.txt'."
        ) from error

    persist_directory.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(persist_directory))
    repo_hash = hashlib.sha256(str(Path(repository_path).resolve()).encode("utf-8")).hexdigest()[:16]
    collection = client.get_or_create_collection(
        name=f"repo_{repo_hash}",
        metadata={"hnsw:space": "cosine", "embedding_model": model_name},
    )
    return client, collection


def index_chunks(chunks: list[dict], collection: Any, model: Any,
                 batch_size: int = DEFAULT_BATCH_SIZE) -> dict:
    """Embed and upsert chunks in small batches; remove stale IDs after upsert."""
    if batch_size < 1 or batch_size > 32:
        raise ValueError("batch_size must be between 1 and 32.")
    if not chunks:
        return {"indexed_count": 0, "removed_stale_count": 0, "embedding_dimensions": 0}

    ids = [str(chunk["chunk_id"]) for chunk in chunks]
    documents = [str(chunk["content"]) for chunk in chunks]
    metadatas = []
    for chunk in chunks:
        metadata = {
            "file_path": str(chunk["file_path"]),
            "language": str(chunk["language"]),
            "kind": str(chunk["kind"]),
            "start_line": int(chunk["start_line"]),
            "end_line": int(chunk["end_line"]),
            "parse_has_error": bool(chunk.get("parse_has_error", False)),
        }
        if chunk.get("symbol"):
            metadata["symbol"] = str(chunk["symbol"])
        metadatas.append(metadata)

    vectors = []
    for start in range(0, len(documents), batch_size):
        encoded = model.encode(
            documents[start:start + batch_size],
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        vectors.extend(encoded.tolist() if hasattr(encoded, "tolist") else encoded)

    # Upsert first so a failed embedding pass never destroys the previous index.
    collection.upsert(ids=ids, documents=documents, metadatas=metadatas, embeddings=vectors)
    existing = collection.get(include=[]).get("ids", [])
    stale_ids = [item for item in existing if item not in set(ids)]
    if stale_ids:
        collection.delete(ids=stale_ids)

    dimensions = len(vectors[0]) if vectors else 0
    return {
        "indexed_count": len(ids),
        "removed_stale_count": len(stale_ids),
        "embedding_dimensions": dimensions,
    }


def index_repository(repository_path: str, max_chars: int = 6000,
                     batch_size: int = DEFAULT_BATCH_SIZE) -> dict:
    """Chunk, embed and persist one local repository in its own Chroma collection."""
    chunk_result = chunk_repository(repository_path, max_chars=max_chars)
    model_name = DEFAULT_EMBEDDING_MODEL
    model = _load_embedding_model(model_name)
    _, collection = _get_collection(repository_path, DEFAULT_PERSIST_DIRECTORY, model_name)
    stats = index_chunks(chunk_result["chunks"], collection, model, batch_size=batch_size)
    return {
        "repository_name": chunk_result["repository_name"],
        "file_count_scanned": chunk_result["file_count_scanned"],
        "chunk_count": chunk_result["chunk_count"],
        "indexed_count": stats["indexed_count"],
        "removed_stale_count": stats["removed_stale_count"],
        "embedding_model": model_name,
        "embedding_dimensions": stats["embedding_dimensions"],
        "storage": "local ChromaDB",
        "truncated": chunk_result["truncated"],
        "skipped_files": chunk_result["skipped_files"],
    }
