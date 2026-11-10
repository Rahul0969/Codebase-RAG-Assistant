"""Small security helpers shared by the RAG pipeline and the MCP server.

Nothing in this module executes code or touches the network.
"""
from __future__ import annotations

import re

REDACTED = "[REDACTED]"

# Multi-line private key blocks. Newlines are preserved so line numbers stay valid.
_PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)",
    re.DOTALL,
)

# Well-known token shapes.
_TOKEN_PATTERNS = [
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                       # AWS access key id
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),             # GitHub tokens
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),           # Slack tokens
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),                  # generic "sk-" API keys
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),  # JWT
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b"),          # GitHub fine-grained token
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),                 # Google API key
    re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}\b"),  # Stripe secret/restricted keys
    re.compile(r"\bnpm_[A-Za-z0-9]{36}\b"),                   # npm token
    re.compile(r"\bSG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\b"),  # SendGrid
]

_SECRET_NAME = r"(?:api[_-]?key|secret|token|passw(?:or)?d|pwd|private[_-]?key|access[_-]?key)"

# name = "value"  /  name: 'value'  /  "name": "value" (JSON)  where the name looks secret.
_ASSIGNMENT = re.compile(
    r"""(?ix)
    (?P<prefix>\b[\w.-]*""" + _SECRET_NAME + r"""[\w.-]*
        (?:\\?['"])?\s*[:=]\s*)
    (?P<quote>\\?['"])
    (?P<value>[^'"\r\n]{6,})
    (?P=quote)
    """
)

# Unquoted values: YAML "key: value", .env / shell / .properties "KEY=value", batch "set KEY=value".
# Deliberately strict so ordinary code such as `token = get_token(x)` is left alone.
_UNQUOTED = re.compile(
    r"""(?imx)
    ^(?P<prefix>[ \t]*(?:-[ \t]+)?(?:export[ \t]+|set[ \t]+)?[\w.-]*""" + _SECRET_NAME + r"""[\w.-]*
        (?::[ \t]+|=))
    (?P<value>[^\s'"$%\#{}\[\]()<>,;`][^\s'"{}\[\]()<>,;`\#]{5,})
    [ \t]*(?:\#.*)?$
    """
)

# scheme://user:password@host
_URL_CREDENTIALS = re.compile(r"(?P<head>\b[a-z][a-z0-9+.-]*://[^\s:/@'\"]+:)(?P<pw>[^\s@/'\"]+)(?P<tail>@)", re.I)
_BEARER = re.compile(r"(?P<head>\bBearer\s+)(?P<tok>[A-Za-z0-9._~+/=-]{16,})", re.I)


def _redact_private_key(match: re.Match) -> str:
    # Keep the same number of lines so cited line ranges still line up.
    return "[REDACTED PRIVATE KEY]" + "\n" * match.group(0).count("\n")


def _redact_unquoted(match: re.Match) -> str:
    value = match.group("value")
    # Real secrets nearly always contain a digit or a separator; plain words
    # (type names such as SecretStr, identifiers) are left alone.
    if value == REDACTED or not re.search(r"[0-9_/+=-]", value):
        return match.group(0)
    return f"{match.group('prefix')}{REDACTED}"


def redact_secrets(text: str) -> str:
    """Mask likely credentials in source text before it leaves the backend.

    This is a best-effort safety net, not a guarantee. The line count of the
    text never changes.
    """
    if not text:
        return text
    text = _PRIVATE_KEY_BLOCK.sub(_redact_private_key, text)
    for pattern in _TOKEN_PATTERNS:
        text = pattern.sub(REDACTED, text)
    text = _ASSIGNMENT.sub(
        lambda m: f"{m.group('prefix')}{m.group('quote')}{REDACTED}{m.group('quote')}", text
    )
    text = _UNQUOTED.sub(_redact_unquoted, text)
    text = _URL_CREDENTIALS.sub(lambda m: f"{m.group('head')}{REDACTED}{m.group('tail')}", text)
    text = _BEARER.sub(lambda m: f"{m.group('head')}{REDACTED}", text)
    return text


# ---------------------------------------------------------------------------
# Repository path guard (used by the MCP server, whose caller is another program)
# ---------------------------------------------------------------------------
import os as _os
from pathlib import Path as _Path

_SENSITIVE_DIR_NAMES = {".ssh", ".aws", ".gnupg", ".kube", ".azure", ".docker", "appdata"}
_POSIX_SYSTEM_DIRS = ("/etc", "/usr", "/bin", "/sbin", "/lib", "/lib64", "/var", "/proc",
                      "/sys", "/dev", "/boot", "/root", "/run", "/snap")
_WINDOWS_SYSTEM_ENV = ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData")


class PathNotAllowedError(ValueError):
    """The repository path is invalid or points to a protected location."""


def _is_link(path: _Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(is_junction and is_junction())


def _inside(child: _Path, parent: _Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def validate_repository_path(repository_path: str) -> _Path:
    """Return the resolved repository directory or raise PathNotAllowedError.

    Rejects: relative paths, links as the root, missing paths, files, filesystem
    roots, the user's home folder (or any folder containing it), operating-system
    folders and credential folders such as .ssh or .aws. If RAG_ALLOWED_ROOTS is
    set (folders separated by ';' on Windows, ':' elsewhere) the repository must
    live inside one of them. Error messages never include the supplied path.
    """
    if not isinstance(repository_path, str) or not repository_path.strip():
        raise PathNotAllowedError("repository_path must not be empty.")
    if len(repository_path) > 4096 or "\x00" in repository_path:
        raise PathNotAllowedError("repository_path is not a valid path.")
    requested = _Path(repository_path.strip()).expanduser()
    if not requested.is_absolute():
        raise PathNotAllowedError("repository_path must be an absolute path.")
    if not requested.exists():
        raise PathNotAllowedError("repository_path does not exist.")
    if not requested.is_dir():
        raise PathNotAllowedError("repository_path must be a directory.")
    if _is_link(requested):
        raise PathNotAllowedError("A symbolic link or junction cannot be the repository root.")
    try:
        resolved = requested.resolve(strict=True)
    except OSError:
        raise PathNotAllowedError("repository_path could not be resolved.") from None

    if resolved.parent == resolved:
        raise PathNotAllowedError("A filesystem root cannot be used as a repository.")
    try:
        home = _Path.home().resolve()
    except (RuntimeError, OSError):
        home = None
    if home is not None and _inside(home, resolved):
        raise PathNotAllowedError("Your home folder (or a folder containing it) cannot be used as a repository.")

    protected = [_Path(p) for p in _POSIX_SYSTEM_DIRS]
    protected += [_Path(_os.environ[name]) for name in _WINDOWS_SYSTEM_ENV if _os.environ.get(name)]
    for folder in protected:
        try:
            folder = folder.resolve()
        except OSError:
            continue
        if _inside(resolved, folder):
            raise PathNotAllowedError("Operating-system folders cannot be used as a repository.")
    if any(part.lower() in _SENSITIVE_DIR_NAMES for part in resolved.parts):
        raise PathNotAllowedError("Credential and application-data folders cannot be used as a repository.")

    allowed = [p for p in (_os.environ.get("RAG_ALLOWED_ROOTS") or "").split(_os.pathsep) if p.strip()]
    if allowed:
        roots = []
        for item in allowed:
            try:
                roots.append(_Path(item).expanduser().resolve())
            except OSError:
                continue
        if not any(_inside(resolved, root) for root in roots):
            raise PathNotAllowedError("repository_path is outside the folders allowed by RAG_ALLOWED_ROOTS.")
    return resolved
