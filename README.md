# Codebase RAG Assistant

A free, local-first assistant that understands a code repository. Point it at a project folder, then search the code by meaning or ask questions in plain language. Answers come from a language model running on your own computer and show the exact files and lines they are based on. Your code is never sent to a hosted AI service.

```
Browser -> React page (local, or hosted on Vercel) -> FastAPI on your PC (127.0.0.1:8000)
   -> Tree-sitter chunks -> sentence-transformers embeddings -> ChromaDB (all on your PC)
   -> Ollama + Qwen 2.5 (on your PC) -> answer + citations + evidence check
```

An MCP server (stdio) exposes the same capabilities to MCP-compatible tools.

## What you need

- Windows 10/11, Python 3.10+, Node.js 20.19+, [Ollama](https://ollama.com/download).
- About 3 GB of disk for packages and the embedding model, plus 1-2 GB for the language model.
- RAM: 4 GB works only with the small model. Read the resource notes in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md#4-resources-on-a-4-gb-computer-honest-guidance). Answers are generated on the CPU and can be slow.

## Quick start (Windows)

1. Double-click **`setup.bat`**. It checks Python and Node, asks before the large Python download, installs the packages, creates `backend\.env`, and reports whether Ollama and the model are present. It never downloads a model by itself.
2. Install Ollama, then download the model (once):
   ```powershell
   ollama pull qwen2.5:3b
   # 4 GB RAM computer? use the smaller one and set OLLAMA_MODEL=qwen2.5:1.5b in backend\.env
   # ollama pull qwen2.5:1.5b
   ```
3. Double-click **`start.bat`**. It opens a backend window and a web-page window, then your browser at http://127.0.0.1:5173. Close the windows to stop.

## Using the app

1. **Repository:** type the full folder path (for example `C:\Users\You\Desktop\my-project`) and click **Inspect repository**. A web page cannot browse your disk, so a typed path is the supported way.
2. Click **Index repository**. The first run downloads a small embedding model. There is no progress bar because the backend does not report progress; the page shows elapsed time.
3. **Code Search:** describe what you want; results show file, symbol, language, line range, a similarity score and the code.
4. **Ask Codebase:** ask a question. Each answer shows an evidence status, clickable citations that reveal the cited code, the model used and how many chunks were retrieved.

**Evidence status** (never green unless the check passed): *Citations verified*, *Partly verified*, *Citation check failed*, *No citations*, *Insufficient evidence*. A verified status means the cited lines were really retrieved, not that every sentence is correct. Read the cited code.

## Configuration

Backend: copy `backend\.env.example` to `backend\.env` (setup does this). Frontend: `frontend\.env.example` has `VITE_API_BASE_URL`. All variables are listed in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md#7-environment-variables). `.env` files are ignored by Git.

## Hosted frontend (Vercel) and your browser

You may host only the web page; the backend always stays on your computer. Steps and the exact browser behavior (Chrome/Edge permission prompt, Firefox, Safari's block, the HTTPS option) are in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md#5-deploying-the-web-page-to-vercel-optional). CORS alone does not make a hosted page work everywhere; the most reliable way is the local page that `start.bat` serves. No Vercel deployment has been done for you.

## Security in one paragraph

The backend listens on 127.0.0.1 only, rejects requests whose `Host` is not local (DNS rebinding) or whose `Origin` is not a trusted site, validates every folder (no system, home, credential or link roots), skips secret files, masks likely secrets, treats repository text as untrusted data in the prompt, never executes code or commands, and keeps the MCP server on stdio. Details and limits: [docs/SECURITY.md](docs/SECURITY.md).

## API

| Endpoint | Purpose |
|---|---|
| `GET /health` | status, Ollama reachability/model, embedding and ChromaDB status (loads nothing heavy) |
| `POST /repository/inspect` | list supported source files |
| `POST /repository/chunk` | chunk preview (developer tool) |
| `POST /repository/index` | chunk, embed, store (`max_chars`, `batch_size` optional) |
| `POST /repository/status` | is it indexed, chunk/file/language counts |
| `POST /repository/search` | semantic search (`query`, `top_k` 1-20) |
| `POST /repository/ask` | RAG answer (`question`, `top_k` 1-10, optional `include_source_text`) |
| `GET /llm/status` | Ollama and model check |

Interactive docs: http://127.0.0.1:8000/docs. Errors carry a readable `detail` and an `X-Error-Code` header (`invalid_request`, `repository_path_invalid`, `not_indexed`, `ollama_unavailable`, `model_not_found`, `llm_timeout`, `llm_bad_response`, `llm_config_invalid`, `service_unavailable`, `host_not_allowed`, `origin_not_allowed`). Status codes: 400 bad input/not indexed, 403 untrusted origin, 422 invalid body, 502 bad model reply, 503 service unavailable, 504 timeout.

`/repository/ask` returns `answer`, `model`, `evidence_status`, `validation_passed`, `citations` (text, lines, `valid`, `reason`), `unsupported_citations`, `unsupported_identifiers`, `evidence_coverage`, `evidence_summary`, `retrieved_chunks` and `sources`. Citations look like `[src/auth.py:15-32]` and are checked deterministically against the retrieved line ranges.

## MCP server

Start: `cd backend` then `.\.venv\Scripts\python.exe run_mcp_server.py` (it waits silently for a client). Client configuration example (absolute paths):

```json
{
  "mcpServers": {
    "codebase-rag-assistant": {
      "command": "C:\\path\\to\\codebase-rag-assistant\\backend\\.venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\codebase-rag-assistant\\backend\\run_mcp_server.py"],
      "env": { "OLLAMA_MODEL": "qwen2.5:3b", "RAG_ALLOWED_ROOTS": "C:\\Users\\YourUser\\Desktop" }
    }
  }
}
```

Tools: `inspect_repository`, `index_repository`, `search_code`, `ask_codebase`, `get_repository_summary` (all take an absolute `repository_path`). Indexing large repositories can exceed a client's tool timeout; index from the web page first if that happens. The server uses the same path guard and secret masking as the API.

## Tests

```powershell
# backend (from the repository root); optional HTTP-level tests need: python -m pip install -r backend\requirements-dev.txt
python -m unittest discover -s tests -v
# frontend
cd frontend; npm test; npm run build
```

Backend tests use mocks for Ollama, the embedding model and ChromaDB; no model download is needed. Frontend tests use Node's built-in runner (API client, error messages, evidence display, state helpers); there are no browser or component-rendering tests, so check the UI by hand. To test the real stack, run `start.bat`, index a small project and ask a question.

## Troubleshooting

| Problem | What to do |
|---|---|
| "Backend disconnected" | Run `start.bat`; check the backend window for errors; check the address in Settings. Hosted page: allow the browser's local-network prompt, add your site to `RAG_TRUSTED_ORIGINS`, or use Safari-safe options in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md#6-hosted-frontend-and-your-browser-important). |
| 403 "website is not allowed" / 400 "host not allowed" | The page's origin is not in `RAG_TRUSTED_ORIGINS`, or you reached the backend through a non-local name. Use `http://127.0.0.1:8000`. |
| "This folder cannot be used" | Choose a normal project folder, not your home folder, a drive root, a Windows folder, or a link. Check `RAG_ALLOWED_ROOTS`. |
| "Not indexed yet" | Index the repository. Re-index after code changes (and once after upgrading from versions before C6: line numbers were corrected). |
| "Ollama is not running" / "model not installed" | Start Ollama; run `ollama pull <model>` for the model shown in Settings. |
| Answers time out or the PC freezes | Use `qwen2.5:1.5b`, close other programs, raise `OLLAMA_TIMEOUT`. |
| Indexing fails with a package error | Run `setup.bat` again and accept the package install. |
| `npm run build` or `npm install` fails | Check `node --version` is 20.19 or newer. |
| Answer says "Citation check failed" | The model cited code it was not given. Do not trust that answer; rephrase or try a larger `top_k`. |

## Project layout

```
backend/app/        FastAPI app, repository scanning, chunker, embeddings, Chroma search,
                    llm_service, rag_service, evidence_validator, security*, mcp_*
backend/run_api.py  starts the API on loopback;  backend/run_mcp_server.py  starts the MCP server
frontend/src/       services/api.js (central client), hooks/, components/, utils/
tests/              backend tests;  frontend/tests/  frontend tests
docs/               SECURITY.md, DEPLOYMENT.md
setup.bat, start.bat, start-backend.bat, start-frontend.bat
```

## Status

All ten roadmap commits (C1-C10) are implemented. See `PROJECT_STATE.md` for what has been verified and what still needs checking on your machine. Known limits: no real indexing progress, no browser-level UI tests, answer quality depends on the small local model, and secret masking is best-effort.
