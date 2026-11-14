# Commit 15 — Intelligent Local Model Routing

This commit carries the originally planned Commit 14 model-routing work under the next commit number. The package also retains the Reports-page UI refinement from the prior C14-A package.

## Modes

### AUTO

For every generation, the backend queries the local Ollama model registry, classifies the latest user request into low/medium/high complexity, and chooses an installed model using a best-effort available-memory estimate. It prefers a smaller model for simple questions and the largest model within a conservative estimated budget for complex requests. If model metadata is missing or the memory budget excludes every model, it falls back to the smallest installed model.

### MANUAL

The user selects one installed model in Settings. The backend validates the choice when saving and again before generation. If that model is later removed from Ollama, generation returns an actionable error instead of silently switching models.

## API

- `GET /llm/models` — installed local model names and available metadata, plus saved preferences.
- `PUT /llm/preferences` — save `{ "mode": "AUTO" }` or `{ "mode": "MANUAL", "model": "model:tag" }`.
- `GET /llm/status` — existing Ollama health check remains available.
- Repository Q&A responses now include routing mode and a human-readable routing reason alongside the selected model.

Preferences are written atomically to `backend/data/model_preferences.json`; `backend/data/` is ignored by Git. All requests use the existing loopback-only Ollama client. No hosted model provider or new runtime dependency was introduced.

## Resource and safety behavior

- Request generation remains serialized by the existing lock to avoid parallel model loads.
- AUTO uses available physical memory when the operating system exposes it; when unavailable, a conservative default budget is used.
- Model-size-to-memory mapping is heuristic, not a guarantee of inference fit. The user should verify AUTO on the target machine; MANUAL remains available.
- Model discovery and inference are local. Repository content is not sent to a cloud LLM.

## Verification

- Python compileall: passed.
- Backend pytest suite: 196 passed, 4 skipped, 26 subtests passed.
- Frontend Node test suite: 27 passed.
- Vite production build: not run because `frontend/node_modules` was not present in the build environment.
- Real Ollama inference and Windows memory selection: not run in this environment; verify on the target PC.
