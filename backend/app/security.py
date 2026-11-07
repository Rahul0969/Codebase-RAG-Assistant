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
]

# name = "value"  /  name: 'value'  where the name looks secret.
_ASSIGNMENT = re.compile(
    r"""(?ix)
    (?P<prefix>\b[\w.-]*(?:api[_-]?key|secret|token|passw(?:or)?d|pwd|private[_-]?key|access[_-]?key)[\w.-]*
        \s*[:=]\s*)
    (?P<quote>['"])
    (?P<value>[^'"\r\n]{6,})
    (?P=quote)
    """
)


def _redact_private_key(match: re.Match) -> str:
    # Keep the same number of lines so cited line ranges still line up.
    return "[REDACTED PRIVATE KEY]" + "\n" * match.group(0).count("\n")


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
    return text
