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
11. C11 — AI-powered repository report generation

## Current commit
C11 — AI-powered repository report generation delivered (builds on C10). Git commit history and real-machine verification remain pending where noted below.

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
- C6: llm_service.py (stdlib HTTP client for local Ollama; loopback-only base URL; typed errors; one generation at a time).
- C6: rag_service.py (search -> line-numbered, redacted, size-limited context -> Ollama; insufficient-context path skips the LLM).
- C6: security.py (best-effort secret redaction that preserves line counts).
- C6: POST /repository/ask and GET /llm/status; AskResponse models; status codes 400/422/502/503/504.
- C6 fix: chunker line ranges were wrong when a chunk started with blank lines; trimmed lines now move start/end together. Existing indexes need one re-index.
- C6 fix: sensitive-name skip now also matches names with extensions (secrets.py, credentials.json) and .npmrc/.pypirc/.netrc.
- C7: evidence_validator.py: deterministic citation extraction ([path:start-end]) and validation against the line ranges shown to the model; coverage, uncited-statement and unsupported-identifier heuristics.
- C7: system prompt now requires citations; /repository/ask adds citations, unsupported_citations, validation_passed, evidence_status (verified | partially_verified | invalid_citations | no_citations | insufficient_evidence), evidence_coverage, evidence_summary, retrieved_chunks; optional include_source_text.
- C7: C6 status values retrieved/insufficient_context replaced by the list above; all other C6 fields kept.
- C8: mcp_tools.py (five tool functions, input validation, safe errors, result caps) and mcp_server.py (FastMCP, stdio) with backend/run_mcp_server.py launcher; tools: inspect_repository, index_repository, search_code, ask_codebase, get_repository_summary.
- C8: security.validate_repository_path (absolute, no link root, no filesystem/home/OS/credential folders, optional RAG_ALLOWED_ROOTS); used only by MCP tools, not by FastAPI endpoints.
- C8: embedding_service.get_index_info (index statistics without loading the embedding model); requirements.txt adds mcp>=1.2,<2.0.
- C9: main.py rewritten for consistency: GET /health (Ollama, model, embedding, Chroma status without loading models), POST /repository/status, response models for inspect/index/search, X-Error-Code header and `_translate` error mapping; routes unchanged.
- C9: frontend: services/api.js (timeouts, error kinds, response shape checks, loopback hint), services/errors.js, utils/evidence.js, utils/repo.js, hooks/useWorkspace.js, components (Repository, Search, Ask, EvidenceBadge, CodeBlock, Feedback), basic App/CSS; .env.example; vite.config.js.
- C9 fixes: frontend `build` script was `vite` (dev server) -> `vite build`; dependencies pinned to ranges; stale-index and error-code handling.
- C9 tests: tests/test_api_integration.py (workflow with fake model/Chroma, error codes, evidence propagation, optional TestClient HTTP tests; requirements-dev.txt adds httpx); frontend node:test suites (api, helpers).
- C10 security: config.py (backend/.env loader for OLLAMA_*/RAG_* only, trusted origins, allowed hosts), security_middleware.py (pure ASGI: Host check vs DNS rebinding, Origin allow-list 403, private-network preflight header, nosniff/no-store), CORS with exact origins and no credentials, path guard on every API endpoint, run_api.py (loopback-only launcher with optional TLS), Chroma telemetry off.
- C10 frontend: sidebar/header layout, dashboard with real checklist, repository/search/ask pages, settings (read-only), BackendHelp, responsive dark-navy CSS, vercel.json (build, dist, headers, CSP limited to loopback connections).
- C10 tooling/docs: setup.bat, start.bat, start-backend.bat, start-frontend.bat, backend/.env.example, README rewrite, docs/SECURITY.md, docs/DEPLOYMENT.md (browser-to-localhost findings: Chrome/Edge local-network prompt, Firefox, Safari block).

## Technology decisions
- React + Vite frontend; keep minimal until backend is complete.
- FastAPI backend.
- sentence-transformers embeddings.
- Ollama local LLM (Qwen 2.5 planned for C6).
- Chroma vector database.
- Tree-sitter AST-aware chunking.
- MCP server exposing repository tools (stdio transport, local only).
- Keras optional reranker only.
- Ollama default model qwen2.5:3b (override with OLLAMA_MODEL; qwen2.5:1.5b for very low RAM). No new dependency in C6.
- Free and local-first; no paid APIs.
- CPU inference and small batches to be mindful of 4 GB RAM.
- One commit at a time.

## Pending
- On the real machine: run setup.bat, npm run build, npm test, all Python tests (with requirements-dev.txt), then start.bat and try the full workflow with a real model.
- Test the hosted-page connection in Chrome/Edge/Firefox/Safari after a real Vercel deployment; confirm browser prompts and RAG_TRUSTED_ORIGINS behavior.
- Commit C6-C10 in order in Git; commit package-lock.json after npm install.
- Run `npm install`, `npm run build`, `npm test` and the TestClient tests locally (not run in the authoring sandbox: no network).
- Install `mcp` (pip install -r backend/requirements.txt), run tests, and try the server with MCP Inspector or a client; confirm tool schemas and call_tool behavior match the installed SDK version.
- Decide in C9/C10 whether FastAPI endpoints should share the MCP path guard.
- Verify with real qwen2.5:3b how often it follows the citation format; tune the prompt if needed.
- Install Ollama, run `ollama pull qwen2.5:3b`, and verify GET /llm/status then POST /repository/ask on a small indexed repo.
- Re-run POST /repository/index on existing indexes (line-number fix).
- Install updated dependencies on Windows.
- First run downloads the embedding model; verify actual model encoding.
- Test POST /repository/index against a small sample repository.
- Confirm C2/C3 Git commits and create the C4 Git commit.
- Verify C4 indexing and C5 semantic search locally against a small sample repository.
- Confirm C2/C3/C4 Git commits exist in order, then create the C5 Git commit.

## Last model + what it did
Claude: delivered C10. Backend: 138 tests pass in a sandbox with stand-in stubs for fastapi/pydantic/mcp (7 skipped: HTTP-level and MCP-SDK tests). Frontend: 23 node tests pass; the app bundles with esbuild (react not installed, so no render and no real vite build). The .bat scripts, real FastAPI middleware stacking, Ollama, browsers and Vercel were not run or deployed.


## Commit 10 correction and verification update (2026-11-07)

- Corrected `tests/test_api_integration.py`: invalid repository paths now expect the API's specific `repository_path_invalid` error code in the HTTP response header.
- Backend test suite rerun after correction: 134 passed, 0 failed, 4 skipped (MCP SDK package unavailable in the verification environment).
- Python compile check: passed.
- Frontend Node test suite: 23 passed, 0 failed.
- Vite production build, real Ollama inference, Windows launcher execution, and Vercel deployment remain unverified and must be checked on the target machine.


## Commit 11 — Repository Intelligence Report Generator

- Added `backend/app/report_service.py` for bounded, local repository report generation.
- Added Markdown (`.md`), HTML (`.html`) and JSON (`.json`) output formats.
- Reports include repository statistics, file-type/language counts, dependency manifest observations, directory structure, entry-point candidates, important files, conservative security pattern matches, recommendations, evidence references and limitations.
- Factual statistics and file references come from repository inspection and Tree-sitter chunking; chunking failures are disclosed rather than fabricated.
- Optional executive-summary generation uses the configured local Ollama model. If Ollama is unavailable, deterministic summary generation remains available.
- Added report storage under `backend/data/reports`; this folder is ignored by Git. Report IDs are opaque UUIDs and download paths are validated.
- Added FastAPI endpoints: `POST /api/reports/generate`, `GET /api/reports`, `GET /api/reports/{report_id}`, and `GET /api/reports/{report_id}/download`.
- Added Reports navigation and page to the React frontend, including format selection, optional AI summary, preview, download and report history.
- Added backend report service/API tests and frontend API-client tests.
- Added `docs/C11_REPORTS.md`, `docs/ARCHITECTURE.md` and `docs/SAMPLE_REPORT.md`.

## C11 verification in authoring environment (2026-11-09)

- Python compilation: passed.
- Backend suite: 145 passed, 0 failed, 4 skipped (MCP SDK package is not installed in this environment).
- Frontend Node tests: 25 passed, 0 failed.
- Vite production build: not run successfully because Vite is not installed in the environment (`vite: not found`).
- Real Ollama executive-summary generation: not tested; deterministic fallback was tested.
- Windows setup/start scripts, real browser UI and Vercel deployment: not tested.

## Remaining verification

- On Windows, run `setup.bat`, then `start.bat`; open Reports and generate each of the three formats.
- Confirm the real Ollama summary works when the model is available and fallback works when it is not.
- Run `npm install`, `npm test`, and `npm run build` in `frontend`.
- Install the MCP dependency and run the four MCP SDK tests (they are skipped in this environment).
- Verify the downloaded report files open correctly in a browser/editor and do not include excluded secret files.
- Verify the hosted Vercel page can connect to the local backend in supported browsers, if deployment is desired.
