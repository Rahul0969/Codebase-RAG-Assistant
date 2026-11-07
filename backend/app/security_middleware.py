"""Pure ASGI middleware that protects a backend running on the user's own computer.

CORS only tells the *browser* what a page may read; it does not stop a request from
being sent. This middleware refuses the requests themselves:

* Host header check: blocks DNS-rebinding (a hostile site pointing its own name at 127.0.0.1).
* Origin check: a browser request from any website that is not explicitly trusted gets 403.
  Requests without an Origin header (curl, Swagger on the same origin, other programs on this
  PC) are allowed: the backend trusts the local user, see docs/SECURITY.md.
* Private-network preflight: answers Chrome's "Access-Control-Request-Private-Network".
* Adds no-store / nosniff headers.
"""
from __future__ import annotations

import json
from typing import Awaitable, Callable, Iterable

from .config import normalize_origin

Scope = dict
Receive = Callable[[], Awaitable[dict]]
Send = Callable[[dict], Awaitable[None]]


def _host_without_port(host_header: str) -> str:
    host = host_header.strip().lower()
    if host.startswith("["):
        end = host.find("]")
        return host[: end + 1] if end != -1 else host
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


class LocalAccessMiddleware:
    def __init__(self, app, allowed_hosts: Iterable[str], trusted_origins: Iterable[str]) -> None:
        self.app = app
        self.allowed_hosts = {h.lower() for h in allowed_hosts}
        self.trusted_origins = {o for o in (normalize_origin(x) for x in trusted_origins) if o}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        host_header = headers.get("host", "")
        if _host_without_port(host_header) not in self.allowed_hosts:
            await self._reject(scope, send, 400, "This host name is not allowed.", "host_not_allowed")
            return

        origin = headers.get("origin")
        origin_ok = True
        if origin is not None:
            normalized = normalize_origin(origin)
            same_origin = normalized is not None and normalized.split("://", 1)[-1] == host_header.strip().lower()
            origin_ok = normalized in self.trusted_origins or same_origin
            if not origin_ok:
                await self._reject(scope, send, 403,
                                   "This website is not allowed to use the local backend.", "origin_not_allowed")
                return

        private_network = (
            scope["type"] == "http" and scope.get("method") == "OPTIONS"
            and headers.get("access-control-request-private-network", "").lower() == "true"
            and origin is not None and origin_ok
        )

        async def guarded_send(message: dict) -> None:
            if message["type"] == "http.response.start":
                extra = [(b"x-content-type-options", b"nosniff"), (b"cache-control", b"no-store")]
                if private_network:
                    extra.append((b"access-control-allow-private-network", b"true"))
                names = {name.lower() for name, _ in message.get("headers", [])}
                message = {**message, "headers": list(message.get("headers", []))
                           + [pair for pair in extra if pair[0] not in names]}
            await send(message)

        await self.app(scope, receive, guarded_send)

    @staticmethod
    async def _reject(scope: Scope, send: Send, status: int, detail: str, code: str) -> None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        body = json.dumps({"detail": detail}).encode("utf-8")
        await send({"type": "http.response.start", "status": status, "headers": [
            (b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
            (b"x-error-code", code.encode()), (b"cache-control", b"no-store"),
        ]})
        await send({"type": "http.response.body", "body": body})
