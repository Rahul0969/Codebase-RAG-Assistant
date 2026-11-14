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
12. C12 — Code change impact analysis

## Current commit
C12 — Code change impact analysis delivered; existing C1–C11 refinements included. Git commit history and real-machine verification remain pending where noted below.

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

## C12 refinement pass (2026-11-10)

- `impact_service.py` reworked in place (same endpoint, same earlier response fields): confirmed vs. inferred edges, deduplicated unresolved references with reasons, side-effect/comment-aware JS parsing, Java matching by declared package (Maven/Gradle layouts), Python source-root inference (labelled inferred), real cycle members (iterative Tarjan), skipped-file reporting, time/file/byte limits via `RAG_IMPACT_*`, dot-folder and Windows path handling.
- Behaviour change: `related_tests` now lists only import-confirmed tests; name-only matches moved to `likely_related_tests`.
- `security.py`: redaction now covers JSON keys, unquoted YAML/env/properties/batch values, URL credentials, bearer tokens and more token formats (line counts preserved; ordinary code left untouched).
- `repository.py`: secret folders and `client_secret*`/`service-account*` JSON files are excluded from scanning and indexing.
- `embedding_service.py`: cached embedding model and Chroma client, one indexing job at a time, streamed upserts, batched stale deletes, complete index statistics.
- `main.py`: each changed-file path in `/repository/impact` is length-validated.
- Frontend: Change Impact page separates confirmed from possible results and shows cycles, skipped files, unresolved references and unmapped aliases.
- New tests: 27 impact edge-case tests and 12 refinement tests (see `docs/TEST_RESULTS_C12.md`).

## Remaining verification

- On Windows, run `setup.bat`, then `start.bat`; open Reports and generate each of the three formats.
- Confirm the real Ollama summary works when the model is available and fallback works when it is not.
- Run `npm install`, `npm test`, and `npm run build` in `frontend`.
- Install the MCP dependency and run the four MCP SDK tests (they are skipped in this environment).
- Verify the downloaded report files open correctly in a browser/editor and do not include excluded secret files.
- Verify the hosted Vercel page can connect to the local backend in supported browsers, if deployment is desired.


## Existing-commit refinements included with C12 (2026-11-09)

- C5 security refinement: semantic search results now pass through the shared best-effort secret redactor before source snippets are returned to browser/API clients. This also protects the RAG retrieval path; secret masking remains best-effort, not a guarantee.
- C10/C12 security refinement: the new impact endpoint uses the same `_safe_repo` path guard as the other repository endpoints. Changed file paths must be repository-relative, cannot traverse outside the repository, and must match an inspected file.
- C11 documentation and report feature descriptions reviewed and linked from the README.
- Updated architecture documentation to include the impact-analysis service.

## Commit 12 — Code Change Impact Analysis

- Added `backend/app/impact_service.py` for bounded static import graph analysis without executing repository code.
- Supports Python imports, JavaScript/TypeScript import/export-from/require/literal dynamic import patterns, and Java package imports that resolve to local files.
- Reports changed files, direct dependents, transitive dependents, all affected files, likely related tests, dependency edges, unresolved local references, possible cycles, truncation and analysis limitations.
- Validates changed file paths against safe repository inspection; caps at 20 changed files, 2,500 analyzed files, 512 KB per file, 8 MB total reads and 500 returned dependency edges. User-selected changed files are prioritized within the analysis cap.
- Added `POST /repository/impact` with request validation and the standard repository path guard.
- Added a Change Impact frontend page and navigation entry with input validation, progress/error states, impact counts, affected file lists, dependency edges and limitations.
- Added `docs/C12_CHANGE_IMPACT.md`, updated README and architecture diagram.
- Added unit, API route, security-guard and frontend API-client tests.

## C12 and refinement verification in authoring environment (2026-11-09)

- Python compileall: passed.
- Backend suite: 157 passed, 0 failed, 4 skipped (MCP SDK dependency unavailable in this environment).
- Frontend Node tests: 26 passed, 0 failed.
- Vite production build: not run because Vite dependencies are not installed in this environment.
- Real Tree-sitter model/indexing, Ollama inference, Windows scripts, browser rendering and Vercel deployment: not verified here.

## Remaining verification

- On Windows, run `setup.bat`, then `start.bat`; inspect a small repository and test inspect/index/search/ask.
- Open Change Impact, enter a real changed file path, and confirm the direct/transitive dependency results and related test suggestions against the repository.
- Generate Markdown, HTML and JSON reports and open each downloaded file.
- Install/run frontend dependencies: `npm install`, `npm test`, `npm run build` from `frontend`.
- Install the MCP SDK and run the four skipped MCP SDK tests; test MCP tools with a real MCP client.
- Verify actual embedding model inference, Chroma persistence and Ollama response behavior.
- Verify browser-to-localhost permissions and optional Vercel deployment.
- Create Git commits C6–C12 in order if the existing Git history does not already contain them; do not represent a combined ZIP as seven historical commits.

## Commit 13 — UI redesign (2026-11-10)

- Redesigned the React application around the supplied dark analytics dashboard reference: midnight navy surfaces, blue ambient lighting, cyan/violet accents, compact grouped sidebar, workspace breadcrumb/search bar, and refined cards.
- Rebuilt the dashboard with truthful workspace metrics, repository/index status, language distribution, quick actions, recent activity derived from current workspace state, and the first-run checklist.
- Kept existing page components, navigation identifiers, API client, and backend endpoints intact. No UI library or new runtime dependency was added.
- Added responsive layouts and documented the redesign in `docs/C13_DESIGN_REFINEMENT.md`.
- Updated the integration-test FakeCollection fixture to accept Chroma offset pagination used by the existing index-statistics implementation.
- Validation: frontend Node tests 26 passed; Python compileall passed. Backend suite result and browser/build verification are recorded with the Commit 13 delivery. Vite production build is not available until frontend dependencies are installed on the target machine.

## Commit 14-A — Reports documentation reader refinement (2026-11-14)

- Refined the Reports page to match the supplied documentation-screen reference while retaining Commit 13's dark navy/blue visual system.
- Replaced the plain textarea preview with a safe Markdown document reader, section navigation, code-block presentation, report toolbar, generation controls, and responsive recent-report history.
- Preserved existing report APIs, all three download formats, optional local Ollama summary behavior, and deterministic fallback.
- No new runtime dependency; backend and core RAG services are unchanged.
- Frontend Node tests: 26 passed, 0 failed.
- Vite build/browser rendering and real local Ollama/report generation remain target-machine verification tasks.
- C14-B remains planned for AUTO/MANUAL intelligent local model routing; local-only/free inference requirement remains in force.

## Commit 15 — Intelligent Local Model Routing (completion package)

Commit 15 delivers the originally planned Commit 14 intelligent model-routing scope, carried forward under the next commit number. It also retains the Commit 14-A Reports UI refinement from the previous package.

- Added a local Ollama model registry endpoint (`GET /llm/models`) exposing installed model names and basic metadata.
- Added persistent local preferences (`backend/data/model_preferences.json`, ignored runtime data) with `AUTO` and `MANUAL` modes and atomic writes.
- Added `PUT /llm/preferences`; MANUAL mode validates that the chosen model is installed before saving.
- Added AUTO routing that classifies the request as low/medium/high complexity, estimates available physical memory without a new dependency, and selects from installed models using a conservative memory budget.
- MANUAL mode pins the selected installed model; if it is removed later, the request returns a clear actionable error.
- All discovery and inference use the loopback-only Ollama client. No cloud model provider or paid API was added.
- Added Settings UI for mode selection, local model discovery, refresh, manual model selection and preference saving.
- Repository Q&A responses now expose the selected routing mode and a human-readable routing reason alongside the model name.
- Integrated routing into shared `generate_chat`, so both repository Q&A and optional AI report summaries use the same policy.
- Retained serialized generation to avoid concurrent model loads on low-memory machines.
- Added unit tests for preferences, manual validation and AUTO routing.

### Verification status
- Python compileall: passed.
- Backend pytest suite: 196 passed, 4 skipped, 26 subtests passed.
- Frontend Node test suite: 27 passed.
- Vite production build: not run because frontend/node_modules was not present in the build environment.
- Real Ollama model discovery, RAM-based selection and inference must still be verified on the target Windows computer.


## C16 (redesign implemented)
- Done: top-nav shell, notifications, confirm dialog, Search filters, Ask conversation sidebar/copy/feedback, Impact graph + risk card, new theme. See docs/C16_TOP_NAV_REDESIGN.md.
- Open: run npm install, vite build, pytest and visual/responsive checks locally (not run in the build sandbox).
