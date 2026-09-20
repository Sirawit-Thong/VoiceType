# voice_typing/errors.py
"""Error classification for Gemini API and network failures.

The goal is to let the reconnect logic decide:
  - RETRY   → transient; back off and try again
  - FATAL   → permanent; stop retrying and tell the user to fix something
"""
from __future__ import annotations

import logging
import re
from enum import Enum

log = logging.getLogger(__name__)


class ErrorCategory(Enum):
    RETRY = "retry"      # transient – network glitch, timeout, 5xx
    FATAL = "fatal"      # permanent – bad API key, quota, model not found


# Patterns that look like an HTTP status code in context
_HTTP_CODE_RE = re.compile(r"(?:HTTP|status\s*(?:code)?|code)[:\s]*(\d{3})", re.IGNORECASE)
_ANY_3DIGIT_RE = re.compile(r"\b(\d{3})\b")


def classify_ws_error(exc: Exception) -> tuple[ErrorCategory, str]:
    """Classify an exception from the WebSocket / HTTP layer.

    Returns (category, human-readable reason).
    """
    name = type(exc).__name__
    msg = str(exc).lower()

    # --- websockets InvalidStatusCode (server rejected the upgrade) ---
    if "invalidstatuscode" in name or "status code" in msg:
        code = _extract_status_code(msg)
        if code is not None:
            return classify_http_status(code, "WebSocket upgrade")

    # --- HTTP error surfaced through urllib / aiohttp ---
    if "httperror" in name or "http" in msg:
        code = _extract_status_code(msg)
        if code is not None:
            return classify_http_status(code, "HTTP")

    # --- Authentication / permission (generic) ---
    if any(kw in msg for kw in ("401", "403", "unauthorized", "forbidden", "api key")):
        return ErrorCategory.FATAL, "API key is invalid or lacks permission"

    # --- Quota / rate limit ---
    if any(kw in msg for kw in ("429", "quota", "rate limit", "resource_exhausted")):
        return ErrorCategory.FATAL, "API quota / rate limit exceeded"

    # --- Model not found (with explicit parentheses for clarity) ---
    if "404" in msg or "not found" in msg or ("model" in msg and "not" in msg):
        return ErrorCategory.FATAL, "Requested model not found – check model name"

    # --- DNS / connection refused / timeout → transient ---
    if any(kw in msg for kw in (
        "connect", "name resolution", "dns", "timeout", "timed out",
        "connectionreset", "connectionrefused", "eof",
        "broken pipe", "connection aborted",
    )):
        return ErrorCategory.RETRY, f"Network error: {type(exc).__name__}"

    # --- SSL errors can be transient (cert issues) or permanent ---
    if "ssl" in msg or "certificate" in msg:
        return ErrorCategory.RETRY, f"SSL/TLS error: {type(exc).__name__}"

    # Default: retry (safe default – we don't want to kill the app on unknown errors)
    return ErrorCategory.RETRY, f"Unexpected error: {name}: {str(exc)[:200]}"


def classify_http_status(code: int, context: str = "HTTP") -> tuple[ErrorCategory, str]:
    """Classify a raw HTTP status code."""
    if code == 200:
        return ErrorCategory.RETRY, "OK"  # shouldn't happen
    if code in (401, 403):
        return ErrorCategory.FATAL, f"{context} {code}: API key is invalid or lacks permission"
    if code == 404:
        return ErrorCategory.FATAL, f"{context} {code}: Model or endpoint not found"
    if code == 429:
        return ErrorCategory.FATAL, f"{context} {code}: Quota / rate limit exceeded"
    if code == 400:
        return ErrorCategory.FATAL, f"{context} {code}: Bad request – check settings"
    if code >= 500:
        return ErrorCategory.RETRY, f"{context} {code}: Server error (transient)"
    return ErrorCategory.RETRY, f"{context} {code}: Unexpected status code"


def _extract_status_code(msg: str) -> int | None:
    """Try to pull an HTTP status code number out of an error message.

    First tries a targeted pattern like 'HTTP 403' or 'status code: 429'.
    Falls back to any isolated 3-digit number if the targeted pattern fails.
    """
    m = _HTTP_CODE_RE.search(msg)
    if m:
        code = int(m.group(1))
        if 100 <= code <= 599:
            return code
    # Fallback: any 3-digit word-boundary number
    m = _ANY_3DIGIT_RE.search(msg)
    if m:
        code = int(m.group(1))
        if 100 <= code <= 599:
            return code
    return None
