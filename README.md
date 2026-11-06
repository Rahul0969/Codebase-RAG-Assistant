# Codebase RAG Assistant

A free, local-first assistant for exploring repositories, searching code by meaning, and answering questions with source-file evidence. The project is being built incrementally.

## Current status

- **C1:** FastAPI and React + Vite foundation.
- **C2:** Safe, lightweight repository structure inspection.
- **C3:** Tree-sitter AST-aware source-code chunking with file and line metadata.
- **C4:** local sentence-transformers embeddings and persistent Chroma indexing.
- Not implemented yet: semantic search, Ollama RAG, citation validation, and MCP.

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
6. Ollama-powered RAG
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
