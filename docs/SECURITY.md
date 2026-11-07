# Security and the local trust boundary

Codebase RAG Assistant reads source code on your computer, so it is built to stay on your computer.

## What is trusted

- **You, and programs you run on this computer, are trusted.** The API has no login. Anyone who can already run programs as you can call it, just as they could read the same files directly.
- **Websites are not trusted.** A web page you visit must not be able to use your backend. That is what most of the protections below are for.
- **Repository contents are untrusted data.** Source code, comments and README files may contain text that tries to manipulate the AI. They are only ever treated as text to read.

## Controls

| Risk | Protection | Where |
|---|---|---|
| Backend reachable from other computers | Binds to `127.0.0.1` by default. The launcher refuses any non-loopback `RAG_HOST` unless you set an explicit override variable. | `backend/run_api.py` |
| A website calls your backend | Browser requests carrying an `Origin` that is not on the trusted list get **403**. Trusted = the local Vite pages plus exact origins you list in `RAG_TRUSTED_ORIGINS`. No wildcards, no `null`. | `security_middleware.py`, `config.py` |
| DNS rebinding (a hostile name pointing at 127.0.0.1) | The `Host` header must be `localhost`, `127.0.0.1` or `[::1]` (plus names in `RAG_ALLOWED_HOSTS`), otherwise **400**. | `security_middleware.py` |
| CORS mistakes | Exact-origin allow-list, `allow_credentials=False` (no cookies are used), only `GET`, `POST`, `OPTIONS`, only `Content-Type` and `Accept` headers. CORS is not the security boundary: the middleware rejects the request itself. | `main.py` |
| Chrome "private network" preflight | Answered with `Access-Control-Allow-Private-Network: true`, only for trusted origins. | `security_middleware.py` |
| Reading arbitrary folders | Every repository endpoint and MCP tool validates the path: absolute only, no links or junctions as the root, no filesystem roots, no home folder (or a folder containing it), no Windows/OS folders, no `.ssh`, `.aws`, `.gnupg`, `.kube`, `.azure`, `.docker`, `AppData`. Optional `RAG_ALLOWED_ROOTS` restricts to chosen folders. | `security.py` |
| Secrets inside a repository | Files named like keys or credentials, `.env*`, key/certificate files, dependency and build folders, and symbolic links are skipped when scanning. Likely secrets in returned code (private keys, tokens, `password = "..."`) are masked before they reach the model, search results or MCP output. | `repository.py`, `security.py` |
| Prompt injection | The system prompt tells the model that retrieved code is untrusted data and must never be obeyed. Repository text cannot close or fake the prompt delimiters. The model can only return text: nothing in the app executes model output, shell commands or repository code. | `rag_service.py` |
| Hallucinated sources | Citations are checked against the code that was really retrieved; failures are shown in red. | `evidence_validator.py` |
| Leaking details in errors | Error messages are fixed, human-readable strings. No stack traces, no file contents, no environment values. `/health` returns model names and status only. | `main.py` |
| Telemetry | Chroma's anonymous telemetry is switched off (API and MCP server). | `config.py`, `mcp_server.py` |
| MCP exposure | stdio only: the MCP client starts the server as a child process; no network port. Five fixed tools, no command execution. | `mcp_server.py` |
| Committing secrets | `.env`, certificates, keys, model files and generated databases are in `.gitignore`. `.env.example` files hold no real values. Only `OLLAMA_*` and `RAG_*` names are read from `backend\.env`. | `.gitignore`, `config.py` |

## Limits you should know about

- A malicious **program on your computer** can call the API. Keep the backend on loopback, and use `RAG_ALLOWED_ROOTS` if you want to limit which folders can ever be read.
- The Origin check relies on the browser sending the `Origin` header, which all current browsers do for cross-site requests. Non-browser clients can send anything; they are in the "trusted local user" group above.
- Secret masking is pattern-based and can miss unusual secrets. Do not index repositories whose source files contain real credentials.
- Prompt-injection defenses lower the risk but cannot remove it. A model can still be misled into a wrong or odd answer. Because the app never acts on model output, the worst case is a misleading text answer, which the citation check helps you notice.
- Symlink and junction detection is best-effort on Windows. The root folder and every scanned entry are checked.
- Traffic between the page and the backend is plain HTTP on the loopback interface by default (it never leaves the computer). Optional HTTPS is described in `DEPLOYMENT.md`.
- Dependencies (PyTorch, ChromaDB, etc.) come from PyPI and npm; keep them updated.

## Reporting a problem

Open an issue in your repository's tracker, or contact the project owner. Do not include real secrets or private source code in reports.
