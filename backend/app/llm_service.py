"""Local Ollama client (standard library only, loopback connections only).

Configuration (environment variables, all optional):
    OLLAMA_BASE_URL    default http://localhost:11434 (must be a loopback host)
    OLLAMA_MODEL       default qwen2.5:3b
    OLLAMA_TIMEOUT     seconds, default 120
    OLLAMA_NUM_CTX     context window in tokens, default 4096
    OLLAMA_NUM_PREDICT max generated tokens, default 512
    OLLAMA_KEEP_ALIVE  how long Ollama keeps the model in RAM, default 2m
"""
from __future__ import annotations

import ipaddress
import json
import os
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5:3b"
DEFAULT_TIMEOUT = 120.0
DEFAULT_NUM_CTX = 4096
DEFAULT_NUM_PREDICT = 512
DEFAULT_KEEP_ALIVE = "2m"
MAX_RESPONSE_BYTES = 2_000_000

# One generation at a time: a 4 GB machine cannot serve parallel LLM requests.
_GENERATION_LOCK = threading.Lock()


class LLMError(RuntimeError):
    """Base class. Messages are safe to show to API clients."""


class LLMConfigError(LLMError):
    """Invalid local configuration."""


class OllamaUnavailableError(LLMError):
    """Ollama is not installed, not running, or refused the connection."""


class OllamaModelNotFoundError(LLMError):
    """The configured model has not been downloaded."""


class OllamaTimeoutError(LLMError):
    """Ollama did not answer in time."""


class OllamaResponseError(LLMError):
    """Ollama answered with something unusable."""


@dataclass(frozen=True)
class LLMSettings:
    base_url: str
    model: str
    timeout: float
    num_ctx: int
    num_predict: int
    keep_alive: str


def _env_number(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError as error:
        raise LLMConfigError(f"{name} must be a number.") from error
    if value < minimum or value > maximum:
        raise LLMConfigError(f"{name} must be between {minimum:g} and {maximum:g}.")
    return value


def _validate_loopback(base_url: str) -> str:
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise LLMConfigError("OLLAMA_BASE_URL must look like http://localhost:11434.")
    host = parsed.hostname
    if host.lower() != "localhost":
        try:
            if not ipaddress.ip_address(host).is_loopback:
                raise ValueError
        except ValueError as error:
            raise LLMConfigError(
                "OLLAMA_BASE_URL must point to this computer (localhost or 127.0.0.1). "
                "Source code is never sent to remote servers."
            ) from error
    return base_url.rstrip("/")


def get_settings() -> LLMSettings:
    """Read configuration from the environment at call time."""
    model = (os.environ.get("OLLAMA_MODEL") or DEFAULT_MODEL).strip()
    if not model or len(model) > 200:
        raise LLMConfigError("OLLAMA_MODEL is invalid.")
    return LLMSettings(
        base_url=_validate_loopback((os.environ.get("OLLAMA_BASE_URL") or DEFAULT_BASE_URL).strip()),
        model=model,
        timeout=_env_number("OLLAMA_TIMEOUT", DEFAULT_TIMEOUT, 1, 3600),
        num_ctx=int(_env_number("OLLAMA_NUM_CTX", DEFAULT_NUM_CTX, 512, 32768)),
        num_predict=int(_env_number("OLLAMA_NUM_PREDICT", DEFAULT_NUM_PREDICT, 16, 4096)),
        keep_alive=(os.environ.get("OLLAMA_KEEP_ALIVE") or DEFAULT_KEEP_ALIVE).strip(),
    )


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: D401 - urllib hook
        return None


def _opener() -> urllib.request.OpenerDirector:
    # Empty ProxyHandler: never route localhost traffic through a system proxy.
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def _request(settings: LLMSettings, path: str, payload: dict | None, timeout: float) -> dict:
    url = settings.base_url + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url, data=data, method="POST" if data is not None else "GET",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with _opener().open(request, timeout=timeout) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as error:
        detail = ""
        try:
            detail = json.loads(error.read(10_000).decode("utf-8", "replace")).get("error", "")
        except (ValueError, AttributeError):
            pass
        if error.code == 404 or "not found" in str(detail).lower():
            raise OllamaModelNotFoundError(
                f"Model '{settings.model}' is not available in Ollama. "
                f"Download it with: ollama pull {settings.model}"
            ) from None
        raise OllamaResponseError(f"Ollama returned HTTP {error.code}.") from None
    except (socket.timeout, TimeoutError):
        raise OllamaTimeoutError(
            f"Ollama did not answer within {settings.timeout:g} seconds. "
            "Try a smaller model or raise OLLAMA_TIMEOUT."
        ) from None
    except urllib.error.URLError as error:
        if isinstance(error.reason, (socket.timeout, TimeoutError)):
            raise OllamaTimeoutError(
                f"Ollama did not answer within {settings.timeout:g} seconds. "
                "Try a smaller model or raise OLLAMA_TIMEOUT."
            ) from None
        raise OllamaUnavailableError(
            "Cannot reach Ollama on this computer. Install it from https://ollama.com, "
            "start it (run 'ollama serve' or open the Ollama app), then retry."
        ) from None
    except OSError:
        raise OllamaUnavailableError("Cannot reach Ollama on this computer.") from None

    if len(body) > MAX_RESPONSE_BYTES:
        raise OllamaResponseError("Ollama response was unexpectedly large.")
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise OllamaResponseError("Ollama returned a response that is not valid JSON.") from None
    if not isinstance(parsed, dict):
        raise OllamaResponseError("Ollama returned an unexpected response shape.")
    return parsed


def generate_chat(messages: list[dict[str, str]], settings: LLMSettings | None = None) -> dict[str, Any]:
    """Send chat messages to the local model and return {'text', 'model'}.

    Generation is serialized with a lock and uses low temperature so answers
    stay close to the supplied code.
    """
    if not messages:
        raise ValueError("messages must not be empty.")
    settings = settings or get_settings()
    payload = {
        "model": settings.model,
        "messages": messages,
        "stream": False,
        "keep_alive": settings.keep_alive,
        "options": {
            "temperature": 0.1,
            "num_ctx": settings.num_ctx,
            "num_predict": settings.num_predict,
        },
    }
    with _GENERATION_LOCK:
        result = _request(settings, "/api/chat", payload, settings.timeout)
    message = result.get("message")
    text = message.get("content") if isinstance(message, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise OllamaResponseError("Ollama returned an empty or malformed answer.")
    return {"text": text.strip(), "model": str(result.get("model") or settings.model)}


def check_ollama(settings: LLMSettings | None = None, timeout: float = 10.0) -> dict[str, Any]:
    """Report whether Ollama is reachable and the configured model is downloaded."""
    settings = settings or get_settings()
    result = _request(settings, "/api/tags", None, min(settings.timeout, timeout))
    models = result.get("models")
    if not isinstance(models, list):
        raise OllamaResponseError("Ollama returned an unexpected model list.")
    names = {str(item.get("name", "")) for item in models if isinstance(item, dict)}
    wanted = settings.model if ":" in settings.model else settings.model + ":latest"
    return {
        "ollama_reachable": True,
        "model": settings.model,
        "model_available": wanted in names or settings.model in names,
        "installed_models": sorted(names)[:50],
    }
