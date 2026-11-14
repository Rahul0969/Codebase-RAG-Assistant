# Commit 17 — UI refresh and model-routing status fixes

## Design changes
- Reworked the application shell into a restrained light workspace with a dark navy sidebar.
- Simplified surfaces, borders, controls, typography, status colors and dashboard cards.
- Added responsive sidebar-to-mobile navigation behavior.
- Kept existing feature components and backend contracts intact.

## Bug fixes
- Added the missing `modelPreferences` request timeout (10 seconds), preventing an undefined timeout / `NaN seconds` message when saving routing preferences.
- Workspace state now loads local Ollama model preferences alongside backend health.
- Dashboard and navigation status now use the saved MANUAL model selection rather than the static `OLLAMA_MODEL` health default.
- AUTO mode is identified as AUTO; after a successful repository question, the actual model used is shown alongside AUTO.
- Saving routing preferences refreshes shared model-routing state so the dashboard updates immediately.

## Verification
- Python bytecode compilation: passed.
- Backend tests: 196 passed, 4 skipped, 26 subtests passed (`PYTHONPATH=. pytest -q`).
- Frontend tests: 33 passed (`npm test`).
- Production Vite build: not run; frontend dependencies are not installed in this environment.
- Live Ollama inference and browser visual/responsive testing: not run in this environment.
