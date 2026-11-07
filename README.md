# Codebase RAG Assistant

A free, local-first assistant for exploring repositories, searching code by meaning, and answering questions with source-file evidence. The project is being built incrementally.

## Current status

- **C1:** FastAPI and React + Vite foundation.
- **C2:** Safe, lightweight repository structure inspection.
- **C3:** Tree-sitter AST-aware source-code chunking with file and line metadata.
- **C4:** local sentence-transformers embeddings and persistent Chroma indexing.
- **C5:** semantic code search over indexed chunks, returning source paths, line ranges and similarity scores.
- **C6:** Ollama-powered RAG: `POST /repository/ask` retrieves code and answers with a local Qwen 2.5 model.
- **C7:** answers carry `[path:start-end]` citations that are checked against the code actually retrieved.
- **C8:** local MCP server (stdio) with five repository tools for MCP-compatible clients.
- **C9:** consistent API (health, status, error codes), working web workflow (inspect, index, search, ask, citations) and integration tests.
- Not implemented yet: final design, security hardening and Windows scripts (C10).

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
7. Source citations and evidence validation (implemented)
8. MCP server and repository tools (implemented)
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


### Source citations and evidence checks (C7)

`POST /repository/ask` now asks the model to cite its sources like `[src/auth.py:15-32]` (the path and line numbers come from the numbered code it was shown). After the model answers, `backend/app/evidence_validator.py` checks every citation with plain deterministic rules:

1. Was that file among the chunks retrieved for this question?
2. Is the line range valid (starts at 1 or later, end not before start)?
3. Is the range inside lines the model was actually shown (adjacent chunks of one file are merged)?

It also reports which retrieved sources were cited, which sentences have no citation, and which `identifiers` written in backticks never appear in the retrieved code.

**New response fields** (all C6 fields are kept):

| Field | Meaning |
|---|---|
| `citations` | every citation found: `text`, `file_path`, `start_line`, `end_line`, `valid`, `reason`, `source_id` |
| `unsupported_citations` | the invalid ones (`file_not_retrieved`, `invalid_line_range`, `lines_outside_retrieved_range`) |
| `validation_passed` | true only if there is at least one citation and all are valid |
| `evidence_status` | see below |
| `evidence_coverage` | sources cited vs retrieved, cited vs uncited statements, examples of uncited statements |
| `unsupported_identifiers` | backticked names not found in the retrieved code |
| `evidence_summary` | one-sentence explanation |
| `retrieved_chunks` | every chunk shown to the model, with line ranges and `cited` flag |

Optional request field `include_source_text` (default `false`) adds the code text (secrets masked) to each item in `retrieved_chunks`.

**`evidence_status` values:** `verified` (all citations valid and every statement cited), `partially_verified` (citations valid, but some statements are uncited or some names are not in the code), `invalid_citations` (at least one citation does not match retrieved code: do not trust it), `no_citations`, and `insufficient_evidence` (nothing relevant retrieved, so the model is not called, or the model says it cannot tell). C6 used `retrieved` / `insufficient_context`; those are replaced by this list. `success` still means "an answer was generated from retrieved code".

**What this does not prove:** a valid citation means the file and lines were really retrieved. It does not prove the sentence next to it is true, and the uncited-statement and identifier checks are heuristics. Small local models sometimes cite loosely or skip citations; the status tells you when that happened. Invalid citations are never hidden or silently corrected.

**Tests:** `python -m unittest discover -s tests -v`. LLM output is mocked.


### MCP server and repository tools (C8)

MCP (Model Context Protocol) lets an AI app such as Claude Desktop call tools on your computer. C8 exposes the assistant as one local MCP server over **stdio**: the client starts the server as a child process and talks to it through standard input/output. No network port is opened, so nothing is reachable from outside your PC. The server reuses the existing services (inspection, chunking, indexing, search, RAG); it does not duplicate them.

**Install and check (PowerShell, from the repository root):**

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt   # adds the 'mcp' package
.\.venv\Scripts\python.exe run_mcp_server.py
```

If it works, the command just waits silently for a client (press Ctrl+C to stop). Do not type into it. Optional visual test with Node.js installed: `npx @modelcontextprotocol/inspector .\.venv\Scripts\python.exe run_mcp_server.py`.

**Connect a client.** Most desktop clients take a JSON entry like this (use your real absolute paths; in Claude Desktop the file is `%APPDATA%\Claude\claude_desktop_config.json`; restart the app afterwards):

```json
{
  "mcpServers": {
    "codebase-rag-assistant": {
      "command": "C:\\path\\to\\codebase-rag-assistant\\backend\\.venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\codebase-rag-assistant\\backend\\run_mcp_server.py"],
      "env": {
        "OLLAMA_MODEL": "qwen2.5:3b",
        "RAG_ALLOWED_ROOTS": "C:\\Users\\YourUser\\Desktop"
      }
    }
  }
}
```

**Tools**

| Tool | Inputs | What it does |
|---|---|---|
| `inspect_repository` | `repository_path` | lists supported source files (paths only), counts by file type |
| `index_repository` | `repository_path`, `max_chars` (500-12000, default 6000), `batch_size` (1-32, default 8) | chunks, embeds and stores the repo in local ChromaDB |
| `search_code` | `repository_path`, `query`, `top_k` (1-20, default 5) | semantic search; returns code, symbol, line range, `file:start-end` citation, similarity |
| `ask_codebase` | `repository_path`, `question`, `top_k` (1-10, default 5) | local Qwen answer with checked citations and `evidence_status` |
| `get_repository_summary` | `repository_path` | facts only: counts by type, top-level folders, notable files by name, index statistics |

Typical order: `inspect_repository`, `index_repository` (again after code changes), then `search_code` / `ask_codebase`. `repository_path` must be an absolute path. Tools return errors with short, safe messages (no stack traces or file contents from outside the repository).

**Security and the trust boundary**

- The *client you configure* is trusted to call these five tools. The server is not meant to be exposed to other computers or the internet; do not wrap it in a network proxy.
- No tool runs shell commands or accepts commands as arguments; repository code is never executed; repository text (comments, README) is never treated as instructions.
- Paths are validated before any work: absolute only; links/junctions as the root, filesystem roots, your home folder (or a folder containing it), operating-system folders and credential/app-data folders (`.ssh`, `.aws`, `.gnupg`, `.kube`, `.azure`, `.docker`, `AppData`) are refused. The existing C2 rules (skip secrets files, `.env*`, keys, dependency/build folders, symlinks) still apply.
- Optional extra lock: set `RAG_ALLOWED_ROOTS` (folders separated by `;` on Windows) and only repositories inside those folders are accepted.
- Likely secrets in returned code are masked (best effort). Chroma's anonymous telemetry is switched off for the server process.
- The same path rules are **not** applied to the FastAPI endpoints (they are for your own browser/Swagger use on localhost). Keep that API bound to 127.0.0.1.

**Practical limits (4 GB RAM machines):** the first `index_repository` run downloads the embedding model and large repositories can exceed a client's tool timeout (often 60 seconds); index through `POST /repository/index` in Swagger instead if that happens, then use the MCP tools. `ask_codebase` can take up to `OLLAMA_TIMEOUT` seconds (default 120). Logs go to the terminal's stderr, because stdout carries the protocol.

**Tests:** `python -m unittest discover -s tests -v`. Tool logic is tested with mocks (no Ollama or model download). The server-registration tests are skipped automatically if the `mcp` package is not installed.


### API integration and the web workflow (C9)

**Endpoints (all `POST` with JSON unless noted)**

| Endpoint | Purpose |
|---|---|
| `GET /health` | backend status, Ollama reachability and model, embedding and ChromaDB status (never loads models) |
| `/repository/inspect` | safe file listing for a folder |
| `/repository/chunk` | chunk preview (developer tool) |
| `/repository/index` | chunk, embed and store |
| `/repository/status` | is the repository indexed, and how many chunks/files/languages (new in C9) |
| `/repository/search` | semantic search |
| `/repository/ask` | RAG answer with citations and evidence status |
| `GET /llm/status` | Ollama and model check |

Every error has a readable `detail` string plus an `X-Error-Code` header: `invalid_request`, `not_indexed`, `ollama_unavailable`, `model_not_found`, `llm_timeout`, `llm_bad_response`, `llm_config_invalid`, `service_unavailable`. Status codes: 400 bad input or not indexed, 422 invalid body, 502 bad model reply, 503 service unavailable, 504 timeout. Inspect, index, search and status now have documented response models; their JSON is unchanged.

**Web interface.** The frontend lives in `frontend/`. Copy `frontend/.env.example` to `frontend/.env.local` if your backend is not at `http://127.0.0.1:8000`. (`VITE_*` values are visible in the browser, so never put secrets there.)

```powershell
cd frontend
npm install
npm run dev        # http://127.0.0.1:5173
npm run build      # production build into frontend/dist
npm test           # frontend tests (Node's built-in test runner, no extra packages)
```

With the backend running, open the page and follow the sections top to bottom: type a folder path, **Inspect**, **Index**, then **Search** or **Ask**. Citations in answers are clickable and show the retrieved code; a failed check is shown in red, never green.

**Fix in C9:** the frontend `build` script was `vite` (it started the dev server); it is now `vite build`. Dependency versions are no longer `latest`.

**Tests:** backend `python -m unittest discover -s tests -v` (add `python -m pip install -r backend/requirements-dev.txt` to also run the HTTP-level tests); frontend `npm test`.
