# Codebase RAG Assistant

A free, local-first assistant for exploring repositories, searching code by meaning, and answering questions with source-file evidence. The project is being built incrementally.

## Current status

- **C1:** FastAPI and React + Vite foundation.
- **C2:** Safe, lightweight repository structure inspection.
- **C3:** Tree-sitter AST-aware source-code chunking with file and line metadata.
- **C4:** local sentence-transformers embeddings and persistent Chroma indexing.
- **C5:** semantic code search over indexed chunks, returning source paths, line ranges and similarity scores.
- **C6:** Ollama-powered RAG: `POST /repository/ask` retrieves code and answers with a local Qwen 2.5 model.
- Not implemented yet: citation validation and MCP.

## Prerequisites

- Python 3.10 or newer
- Node.js 20.19+ or 22.12+ (for current Vite releases)
- Git

Check versions in PowerShell:

```powershell
python --version
node --version
npm --version
git --version
```

## Run the backend

From the repository root, in terminal 1:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload
```

If PowerShell blocks activation, use the venv executables directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Useful endpoints:

- http://127.0.0.1:8000/ — welcome response
- http://127.0.0.1:8000/health — health check
- http://127.0.0.1:8000/docs — interactive API documentation
- `POST /repository/inspect` — inspect a local repository
- `POST /repository/chunk` — preview AST-aware code chunks
- `POST /repository/index` — create/update a local vector index
- `POST /repository/search` — retrieve semantically relevant code chunks

### Inspect a repository

Use Swagger UI at http://127.0.0.1:8000/docs. Open `POST /repository/inspect`, select **Try it out**, and provide an absolute path to a repository folder:

```json
{
  "repository_path": "C:\\Users\\YourUser\\Desktop\\sample-project"
}
```

The endpoint returns supported relative file paths and extensions. It does not read or execute source files. It skips common dependency/build/cache directories, symbolic links, environment files, and common private-key files. The scan is limited to 5,000 files and 20 directory levels.

**Local-use safety note:** this development API accepts an absolute path from the request and inspects it using the permissions of the account running the backend. Keep the server on your own machine; do not expose it to an untrusted network. This is not an authorization boundary for a multi-user deployment.


### Create AST-aware code chunks (C3)

The chunker uses Tree-sitter grammars for supported programming languages (Python, JavaScript/JSX, TypeScript/TSX, Java, C/C++, C#, Go, Rust, Ruby, and PHP). It prefers function, method, class, and other definition nodes; files without recognized definitions fall back to line-based module chunks. Every chunk includes a relative file path, language, syntax-node kind, optional symbol name, and 1-based start/end lines. Oversized syntax nodes are split at line boundaries.

After installing the updated backend requirements, open http://127.0.0.1:8000/docs and try `POST /repository/chunk`:

```json
{
  "repository_path": "C:\\Users\\YourUser\\Desktop\\sample-project",
  "max_chars": 6000
}
```

`max_chars` must be between 500 and 12,000. Files larger than 1 MB are skipped. The endpoint returns source snippets as chunk content, so keep the local API private and only select repositories whose code may be processed locally.

## Run the frontend

In terminal 2, from the repository root:

```powershell
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite, usually http://localhost:5173. Click **Check backend** while the API is running.

## Run backend tests

From the repository root:

```powershell
python -m unittest discover -s tests -v
```

The tests use Python's built-in `unittest` and do not require an additional test package.

## Roadmap

1. Project foundation
2. Safe repository inspection
3. Tree-sitter AST-aware code chunking (implemented)
4. Sentence-transformers embeddings and Chroma indexing
5. Semantic code search
6. Ollama-powered RAG (implemented)
7. Source citations and evidence validation
8. MCP server and repository tools
9. API integration and end-to-end testing
10. Security, documentation, and final frontend design


### Build a local vector index (C4)

C4 embeds C3 code chunks with `sentence-transformers/all-MiniLM-L6-v2` and stores vectors in a persistent local ChromaDB database under `backend/data/chroma_db/`. The model runs on CPU and encodes in small batches (default 8) to reduce memory use. The first indexing run downloads the embedding model from Hugging Face; later runs reuse its local cache. No paid API key is used.

Install the updated backend requirements (PyTorch and model dependencies can take time and disk space):

```powershell
cd backend
python -m pip install -r requirements.txt
cd ..
```

Then open http://127.0.0.1:8000/docs and use `POST /repository/index`:

```json
{
  "repository_path": "C:\\Users\\YourUser\\Desktop\\sample-project",
  "max_chars": 6000,
  "batch_size": 8
}
```

The endpoint chunks source files, creates normalized embeddings, and upserts them into a repository-specific Chroma collection. Re-indexing updates changed chunks and removes stale chunk IDs. The local vector database is excluded from Git. Keep the API bound to localhost and do not index repositories containing secrets.


### Search code by meaning (C5)

After successfully indexing a repository with `POST /repository/index`, use `POST /repository/search` in Swagger UI. Enter a natural-language question or describe the code you are looking for:

```json
{
  "repository_path": "C:\\Users\\YourUser\\Desktop\\sample-project",
  "query": "Where is user authentication checked?",
  "top_k": 5
}
```

The search text is embedded with the same local sentence-transformers model used during indexing. Chroma returns the closest code chunks. Each match includes its relative file path, symbol (when available), language, chunk type, 1-based line range, code content, cosine distance and a normalized similarity value. Similarity is a retrieval score, not a probability or a guarantee that a result is correct. `top_k` is limited to 1–20 and the number of returned matches cannot exceed the number of indexed chunks.

The repository must be indexed first. Re-index after changing source files so search results stay current. Search is local and does not call a paid API.


### Ask questions about your code (C6)

C6 connects C5 search to a local LLM through [Ollama](https://ollama.com). Flow: your question -> semantic search -> the best chunks (secrets masked, line-numbered, size-limited) -> Qwen 2.5 on your computer -> answer plus the sources that were shown to the model. Nothing is sent to a hosted AI service, and the backend refuses any Ollama address that is not on your own computer.

**One-time setup (PowerShell):**

```powershell
# 1. Install Ollama from https://ollama.com, then download the model (about 2 GB):
ollama pull qwen2.5:3b
# On a 4 GB machine, if it is too slow or runs out of memory, use the smaller model:
#   ollama pull qwen2.5:1.5b
#   $env:OLLAMA_MODEL = "qwen2.5:1.5b"

# 2. Start the backend (no new Python packages are needed for C6):
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

**Use it:** index first (`POST /repository/index`), then open http://127.0.0.1:8000/docs and call `POST /repository/ask`:

```json
{
  "repository_path": "C:\\Users\\YourUser\\Desktop\\sample-project",
  "question": "Where is user authentication implemented?",
  "top_k": 5
}
```

Check your setup any time with `GET /llm/status` (is Ollama running, is the model downloaded?).

**Response fields:** `answer`, `model`, `evidence_status` (`retrieved` or `insufficient_context`), `success`, `retrieved_count`, `used_chunk_count`, `sources` (file, symbol, line range, similarity), `context_chars`, `context_truncated`. If nothing relevant is retrieved, the model is **not** called and you get an insufficient-context status.

**Status codes:** 400 bad input or repository not indexed; 422 invalid request body; 502 malformed Ollama reply; 503 Ollama not running, model not downloaded, or ChromaDB/embedding unavailable; 504 timeout.

**Settings (environment variables, all optional):**

| Variable | Default | Meaning |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | must be localhost / 127.0.0.1 |
| `OLLAMA_MODEL` | `qwen2.5:3b` | any model you have pulled |
| `OLLAMA_TIMEOUT` | `120` | seconds; first request after loading is slowest |
| `OLLAMA_NUM_CTX` | `4096` | context window (tokens) |
| `OLLAMA_NUM_PREDICT` | `512` | max answer length (tokens) |
| `OLLAMA_KEEP_ALIVE` | `2m` | how long Ollama keeps the model in RAM |
| `RAG_MAX_CONTEXT_CHARS` | `6000` | total code sent to the model |
| `RAG_MAX_CHUNK_CHARS` | `2500` | per-chunk limit |
| `RAG_MIN_SIMILARITY` | `0.15` | chunks scoring lower are ignored |

Set one in PowerShell like this: `$env:OLLAMA_MODEL = "qwen2.5:1.5b"` (applies to that terminal window).

**Safety design:** the system prompt tells the model to treat retrieved code as untrusted data and ignore instructions hidden in it; repository text cannot close the prompt's delimiter tags; likely secrets (private keys, API keys, tokens, `password = "..."`) are masked before the model sees them (best effort, not a guarantee); nothing from the repository is ever executed; only one generation runs at a time. A small model can still be wrong, so C7 adds citation checking.

**Fixes made while building C6**

- Chunk line numbers were off when a split chunk began with blank lines (the range started too early). Ranges now always match the stored text. **Re-run `POST /repository/index` once** so existing indexes get corrected line numbers; stale chunks are removed automatically.
- Files named like `secrets.py` or `credentials.json` are now skipped (before, only exact names without an extension were).
- Stale-chunk cleanup no longer rebuilds a set on every loop iteration.

**Run the tests:** `python -m unittest discover -s tests -v`. All Ollama tests use mocks; no model download is needed. An optional real check is `GET /llm/status` followed by one `POST /repository/ask` on a small indexed project.
