"""Local configuration: optional backend/.env file, trusted origins and allowed hosts.

Nothing here returns or logs the *values* of environment variables.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

# Chroma sends anonymous usage statistics unless told otherwise; this app is local-first.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
_ALLOWED_KEY = re.compile(r"^(OLLAMA|RAG)_[A-Z0-9_]+$")

DEFAULT_DEV_ORIGINS = (
    "http://localhost:5173", "http://127.0.0.1:5173",   # Vite dev server
    "http://localhost:4173", "http://127.0.0.1:4173",   # Vite preview
)
DEFAULT_ALLOWED_HOSTS = ("localhost", "127.0.0.1", "[::1]")
LOOPBACK_NAMES = {"localhost", "127.0.0.1", "::1", "[::1]"}


def load_env_file(path: Path | None = None) -> list[str]:
    """Load KEY=VALUE lines from backend/.env into os.environ (existing variables win).

    Only OLLAMA_* and RAG_* names are accepted. Returns the names that were set.
    """
    path = path or ENV_FILE
    loaded: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return loaded
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].strip()
        if not _ALLOWED_KEY.match(key) or key in os.environ:
            continue
        os.environ[key] = value
        loaded.append(key)
    return loaded


def normalize_origin(value: str) -> str | None:
    """Return 'scheme://host[:port]' in lower case, or None if it is not a plain origin."""
    candidate = (value or "").strip().rstrip("/").lower()
    if not candidate or candidate in {"*", "null"}:
        return None
    parts = urlsplit(candidate)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return None
    if parts.path or parts.query or parts.fragment or parts.username or parts.password or "*" in candidate:
        return None
    try:
        port = parts.port
    except ValueError:
        return None
    host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
    return f"{parts.scheme}://{host}" + (f":{port}" if port else "")


def trusted_origins() -> list[str]:
    """Development origins plus RAG_TRUSTED_ORIGINS (comma separated, exact origins only)."""
    origins = list(DEFAULT_DEV_ORIGINS)
    for item in (os.environ.get("RAG_TRUSTED_ORIGINS") or "").split(","):
        if not item.strip():
            continue
        origin = normalize_origin(item)
        if origin is None:
            logger.warning("Ignoring an invalid entry in RAG_TRUSTED_ORIGINS (use exact origins like https://my-app.vercel.app).")
        elif origin not in origins:
            origins.append(origin)
    return origins


def allowed_hosts() -> list[str]:
    """Host names the backend answers to (loopback names plus RAG_ALLOWED_HOSTS)."""
    hosts = list(DEFAULT_ALLOWED_HOSTS)
    for item in (os.environ.get("RAG_ALLOWED_HOSTS") or "").split(","):
        name = item.strip().lower()
        if name and "*" not in name and "/" not in name and name not in hosts:
            hosts.append(name)
    return hosts


def is_loopback_host(host: str) -> bool:
    return host.strip().lower() in LOOPBACK_NAMES
