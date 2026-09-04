"""Redact credentials from diagnostics, logs, and UI messages.

Keys stay in local settings only. Anything shown to the user or written
to logs passes through redact_text first.
"""
from __future__ import annotations

import re
from typing import Mapping

REDACTED = "***REDACTED***"

_QUERY_KEY_RE = re.compile(r"([?&](?:key|api_key|api-key|token|access_token)=)[^&\s\"']+", re.IGNORECASE)
_BEARER_RE = re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.~+/=]+", re.IGNORECASE)
_TOKEN_ASSIGN_RE = re.compile(r"((?:api[_-]?key|token|secret)\s*[=:]\s*)(['\"]?)[A-Za-z0-9_\-]{8,}\2", re.IGNORECASE)
_GOOGLE_KEY_RE = re.compile(r"\bAIza[A-Za-z0-9_\-]{10,}")
_SK_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9]{8,}")
_DEEPGRAM_KEY_RE = re.compile(r"\bdg_[A-Za-z0-9_\-]{8,}")


def redact_text(message: str) -> str:
    if not message:
        return message
    out = _QUERY_KEY_RE.sub(r"\1" + REDACTED, message)
    out = _BEARER_RE.sub(r"\1" + REDACTED, out)
    out = _TOKEN_ASSIGN_RE.sub(lambda m: m.group(1) + (m.group(2) or "") + REDACTED, out)
    out = _GOOGLE_KEY_RE.sub(REDACTED, out)
    out = _SK_KEY_RE.sub("sk-" + REDACTED, out)
    out = _DEEPGRAM_KEY_RE.sub(REDACTED, out)
    return out


def redact_url(url: str) -> str:
    return redact_text(url)


def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    redacted: dict[str, str] = {}
    for name, value in headers.items():
        if name.lower() in ("authorization", "x-api-key", "api-key"):
            redacted[name] = REDACTED
        else:
            redacted[name] = redact_text(value)
    return redacted


def safe_error(exc: BaseException, prefix: str = "") -> str:
    text = redact_text(f"{type(exc).__name__}: {exc}")
    return f"{prefix}{text[:300]}" if prefix else text[:300]
