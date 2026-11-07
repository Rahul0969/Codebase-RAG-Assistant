# Installation, deployment and the browser-to-localhost connection

## 1. Architecture and why the backend stays local

```
Browser  ->  React page (local, or hosted on Vercel)  ->  FastAPI on YOUR PC (127.0.0.1:8000)
                                                           ->  ChromaDB + embedding model (on your PC)
                                                           ->  Ollama + Qwen 2.5 (on your PC)
```

The backend must read folders on your disk and run models on your hardware. Putting it on Render or any cloud host would mean uploading your source code to a server (the opposite of this project's goal), would need a paid GPU/CPU tier for the models, and would make the API a public target. So **only the web page can be hosted; the backend is never deployed to a cloud service by default and must never be exposed to the internet.** A hosted page cannot browse your files or reach Ollama by itself: you always run the local backend.

## 2. Local installation (Windows)

Requirements: Windows 10/11, Python 3.10+, Node.js 20.19+, about 3 GB of free disk for packages and the embedding model plus 1-2 GB for the language model, and 4 GB RAM or more (see section 4).

1. Install Python (tick "Add python.exe to PATH") and Node.js LTS.
2. Double-click `setup.bat`. It checks your tools, asks before the large Python download, installs the frontend packages, creates `backend\.env`, and tells you whether Ollama and the model are present.
3. Install Ollama and download the model (section 3).
4. Double-click `start.bat`. It opens a backend window and a web-page window and then your browser at `http://127.0.0.1:5173`. To stop, close the windows (or press Ctrl+C in them).

Without the scripts (PowerShell): `cd backend; .\.venv\Scripts\python.exe run_api.py` and, in another window, `cd frontend; npm run dev`.

## 3. Ollama and the model

1. Install Ollama from https://ollama.com/download.
2. Make sure it is running (the Ollama app in the tray, or `ollama serve` in a terminal).
3. Download the exact model configured in `backend\.env` (default `qwen2.5:3b`, about 1.9 GB):
   `ollama pull qwen2.5:3b`
4. Verify: `ollama list` shows the model. Test inference: `ollama run qwen2.5:3b "Say hello"` (type `/bye` to leave).
5. In the app, **Settings** shows the model and whether it is installed. `GET http://127.0.0.1:8000/llm/status` reports the same.

## 4. Resources on a 4 GB computer (honest guidance)

- `qwen2.5:3b` needs roughly 2-3 GB of RAM while answering; with Windows and a browser running, a 4 GB machine may swap heavily or fail. **Prefer `qwen2.5:1.5b`** (about 1 GB download, lower RAM): `ollama pull qwen2.5:1.5b` and set `OLLAMA_MODEL=qwen2.5:1.5b` in `backend\.env`.
- Answers are generated on the CPU and can take from tens of seconds to several minutes. If requests time out, raise `OLLAMA_TIMEOUT`.
- The first index or search downloads the embedding model (about 90 MB) and loads PyTorch, which uses a few hundred MB of RAM. Embedding runs in small batches (default 8).
- `OLLAMA_KEEP_ALIVE=2m` frees the model's memory soon after use. Only one answer is generated at a time.
- Close other heavy programs while indexing or asking. None of this can guarantee smooth performance on weak hardware.

## 5. Deploying the web page to Vercel (optional)

You can skip this and use the local page that `start.bat` serves. Hosting is only a convenience. **No Vercel deployment has been performed for this project; follow these steps yourself.**

1. Push the repository to GitHub (make sure no `.env` file is committed).
2. In Vercel: **Add New > Project**, import the repository.
3. Set **Root Directory** to `frontend`. Framework preset: Vite. Build command `npm run build`, output directory `dist` (both are also in `frontend/vercel.json`).
4. Add the environment variable `VITE_API_BASE_URL` = `http://127.0.0.1:8000` (the address of the backend on the *visitor's* computer). It is compiled into the page and visible to everyone, so it must never contain a secret. It is fixed per build; changing it means a redeploy.
5. Deploy. Copy the production URL, for example `https://my-app.vercel.app`.
6. On each computer that runs the backend, set in `backend\.env`: `RAG_TRUSTED_ORIGINS=https://my-app.vercel.app` and restart the backend. Preview deployments have different URLs; add one only if you need it. Never add `*`.

`frontend/vercel.json` also sets security headers and a content-security-policy that only lets the page connect to itself and to loopback addresses. If you serve the backend on another address, edit `connect-src` there.

## 6. Hosted frontend and your browser (important)

A page served over **HTTPS** that calls **`http://127.0.0.1`** is a "secure site talking to a plain-HTTP local address". What actually happens depends on the browser. CORS settings alone do not solve any of this.

| Browser | Behavior (as documented when this was written) |
|---|---|
| Chrome, Edge | Plain-HTTP requests to `127.0.0.1`/`localhost` are exempt from mixed-content blocking. Since Chrome 142 / Edge 143 (late 2025) the first request from a public site shows a **"Local network access" permission prompt**; the user must choose Allow, and a denial is remembered per site (re-enable it in the site settings). The page declares its target with `targetAddressSpace: "loopback"` (done in `frontend/src/services/api.js`). |
| Firefox | Mixed-content blocking does not apply to loopback addresses (`127.0.0.1` and `localhost`). Firefox has also been rolling out its own local-network permission prompt (reported for version 147, early 2026); check your version if connections are blocked. |
| Safari | Does not exempt loopback from mixed-content blocking, so a hosted HTTPS page **cannot** reach `http://127.0.0.1`. Use the local page (`http://127.0.0.1:5173`, from `start.bat`) or the HTTPS option below. |

Other things that can block it: browser privacy/shield settings, extensions, and company-managed browser policies.

**Most reliable setup:** open the page that `start.bat` serves (`http://127.0.0.1:5173`). The page and the API are both on your computer, so none of the restrictions above apply.

**Hosted page with HTTPS backend (Safari, or to avoid HTTP entirely):** give the backend a certificate your browser trusts for `127.0.0.1`, for example with the free tool mkcert (`mkcert -install`, then `mkcert 127.0.0.1 localhost`). Put the two generated files' paths in `backend\.env` as `RAG_SSL_CERTFILE` and `RAG_SSL_KEYFILE`, set the build variable `VITE_API_BASE_URL=https://127.0.0.1:8000`, and redeploy. Trade-offs: every user must install a local certificate authority, and the hosted build is tied to one address. The backend still binds to loopback only.

The backend never accepts requests from untrusted websites regardless of browser: see `SECURITY.md`.

## 7. Environment variables

Backend (`backend\.env`, see `backend\.env.example`): `OLLAMA_MODEL`, `OLLAMA_BASE_URL` (must be local), `OLLAMA_TIMEOUT`, `OLLAMA_NUM_CTX`, `OLLAMA_NUM_PREDICT`, `OLLAMA_KEEP_ALIVE`, `RAG_MAX_CONTEXT_CHARS`, `RAG_MAX_CHUNK_CHARS`, `RAG_MIN_SIMILARITY`, `RAG_HOST`, `RAG_PORT`, `RAG_TRUSTED_ORIGINS`, `RAG_ALLOWED_HOSTS`, `RAG_ALLOWED_ROOTS`, `RAG_SSL_CERTFILE`, `RAG_SSL_KEYFILE`, `RAG_RELOAD`. Values already set in the shell win over the file.

Frontend (`frontend\.env.local` or the Vercel dashboard): `VITE_API_BASE_URL` only. Never put secrets in `VITE_*` variables.

## 8. Troubleshooting

See the troubleshooting section of the main `README.md`.
