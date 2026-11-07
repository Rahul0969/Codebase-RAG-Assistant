r"""Starts the API on this computer only.

Usage (PowerShell):  .\.venv\Scripts\python.exe run_api.py

Settings (environment or backend\.env): RAG_HOST (default 127.0.0.1), RAG_PORT (default 8000),
RAG_RELOAD=1 (auto-restart while developing), RAG_SSL_CERTFILE / RAG_SSL_KEYFILE (optional HTTPS).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import is_loopback_host, load_env_file  # noqa: E402

load_env_file()


def main() -> int:
    host = (os.environ.get("RAG_HOST") or "127.0.0.1").strip()
    if not is_loopback_host(host) and os.environ.get("RAG_UNSAFE_ALLOW_NON_LOOPBACK") != "1":
        print(
            "Refusing to start: RAG_HOST is not a loopback address. This backend reads files on your computer "
            "and must not be reachable from other computers. Use 127.0.0.1 (the default).",
            file=sys.stderr,
        )
        return 2
    try:
        port = int(os.environ.get("RAG_PORT") or "8000")
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        print("RAG_PORT must be a number between 1 and 65535.", file=sys.stderr)
        return 2

    certfile = os.environ.get("RAG_SSL_CERTFILE") or None
    keyfile = os.environ.get("RAG_SSL_KEYFILE") or None
    if bool(certfile) != bool(keyfile):
        print("Set both RAG_SSL_CERTFILE and RAG_SSL_KEYFILE, or neither.", file=sys.stderr)
        return 2

    import uvicorn

    scheme = "https" if certfile else "http"
    print(f"Codebase RAG Assistant API: {scheme}://{host}:{port}  (local only; press Ctrl+C to stop)")
    uvicorn.run(
        "app.main:app", host=host, port=port, reload=os.environ.get("RAG_RELOAD") == "1",
        ssl_certfile=certfile, ssl_keyfile=keyfile, server_header=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
