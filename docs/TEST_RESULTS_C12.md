# C1–C12 verification snapshot (refinement pass, 2026-11-10)

These are automated results from a sandbox **without network access**, so `fastapi`, `pydantic`, `chromadb`, `sentence-transformers`, `tree-sitter-language-pack`, `mcp`, `httpx` and Vite could not be installed. Nothing below is proof of operation on your Windows computer.

## Executed in this refinement pass

| Check | Result | Notes |
|---|---:|---|
| Python compilation | PASS | `python -m compileall -q backend tests` |
| Impact service tests (`tests/test_impact_service.py`) | 33 passed | 6 original + 27 new edge-case tests (Python/JS/Java resolution, inferred vs confirmed, cycles, dot-folders, Windows paths, malformed files, symlink, caps) |
| Refinement tests (`tests/test_c12_refinements.py`) | 12 passed | redaction, sensitive folders, model/client reuse, indexing slot, sliced writes, stale-delete batching, index statistics paging (all with fakes) |
| Other existing backend tests that load without FastAPI | passed | `test_c6_fixes` (redaction/chunk lines/sensitive names) and others |
| Whole backend suite via `unittest discover` | 87 passed, 4 skipped, **9 modules could not load** | the 9 modules import `fastapi`; they were **not run** here. The 4 skips are the MCP SDK tests |
| Frontend Node tests (`npm test`) | 26 passed | no new frontend tests were added |

## Not executed here (must be run on your machine)

- The 9 FastAPI-dependent test modules (API integration, API security, report API, route registration, embedding endpoint, semantic search endpoint, repository endpoint, RAG endpoint and others): run `python -m unittest discover -s tests -v` after `setup.bat`.
- Vite production build (`npm install`, `npm run build`) and the rewritten `ImpactPanel.jsx`: only a brace/tag balance check was done; it was never compiled or rendered.
- MCP SDK tests, real MCP client.
- Real embedding model, real ChromaDB persistence (including the new client reuse and sliced upserts), real Ollama generation, real Tree-sitter parsing.
- Windows `setup.bat` / `start.bat`, browser rendering, Vercel connection.
- Behaviour of the 4 GB RAM target under a real indexing run.

## Earlier snapshot (previous environment, 2026-11-09, not reproduced here)

157 backend tests passed and 4 were skipped; 26 frontend tests passed. That environment had FastAPI available; this one does not.

## Interpretation

- C12 is static file-level import analysis. Confirmed results come only from imports that resolve unambiguously; inferred results are reported separately and are guesses.
- Secret masking is best-effort and is not a guarantee that all credentials are detected.
- The MCP SDK tests are skipped, not passed.
