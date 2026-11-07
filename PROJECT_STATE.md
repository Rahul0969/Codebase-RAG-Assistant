# PROJECT_STATE.md

## Roadmap
1. C1 — Project foundation
2. C2 — Safe repository inspection
3. C3 — Tree-sitter AST-aware code chunking
4. C4 — Sentence-transformers embeddings and Chroma indexing
5. C5 — Semantic code search
6. C6 — Ollama-powered RAG
7. C7 — Source citations and evidence validation
8. C8 — MCP server and repository tools
9. C9 — API integration and end-to-end testing
10. C10 — Security, documentation, deployment and final frontend design

## Current commit
C5 — Semantic search implementation delivered; local verification and Git commit pending. C4 real model/index verification is still pending unless completed locally.

## Completed
- C1: project foundation.
- C2: safe repository inspection and API endpoint.
- C3: Tree-sitter AST-aware code chunking and POST /repository/chunk.
- C4: lazy-loaded sentence-transformers embedding service.
- C4: default model `sentence-transformers/all-MiniLM-L6-v2`, CPU inference and batch size 8.
- C4: persistent local ChromaDB collections, one per repository.
- C4: chunk metadata stored with vectors; deterministic IDs upserted; stale IDs removed.
- C4: POST /repository/index endpoint.
- C4: added mocked unit tests for batching, metadata, stale cleanup and API errors.
- C5: added semantic search using the same sentence-transformers model and repository-specific Chroma collection.
- C5: added POST /repository/search with query validation and top_k limit (1–20).
- C5: results include code content, relative path, symbol, language, 1-based line range, cosine distance and normalized similarity.
- C5: added mocked tests for result mapping, empty indexes, validation and API errors.

## Technology decisions
- React + Vite frontend; keep minimal until backend is complete.
- FastAPI backend.
- sentence-transformers embeddings.
- Ollama local LLM (Qwen 2.5 planned for C6).
- Chroma vector database.
- Tree-sitter AST-aware chunking.
- MCP server exposing repository tools.
- Keras optional reranker only.
- Free and local-first; no paid APIs.
- CPU inference and small batches to be mindful of 4 GB RAM.
- One commit at a time.

## Pending
- Install updated dependencies on Windows.
- First run downloads the embedding model; verify actual model encoding.
- Test POST /repository/index against a small sample repository.
- Confirm C2/C3 Git commits and create the C4 Git commit.
- Verify C4 indexing and C5 semantic search locally against a small sample repository.
- Confirm C2/C3/C4 Git commits exist in order, then create the C5 Git commit.

## Last model + what it did
GPT-6: added semantic search over C4 Chroma indexes, FastAPI POST /repository/search, metadata-rich match results, validation, tests and documentation. Tests use fake model/Chroma objects; real model inference and local Chroma query must be verified on the user’s machine.
