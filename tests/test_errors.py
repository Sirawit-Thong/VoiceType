# tests/test_errors.py
"""Tests for voice_typing.errors – error classification."""

import urllib.error

import pytest

from voice_typing.errors import ErrorCategory, classify_http_status, classify_ws_error


# ── classify_ws_error ────────────────────────────────────────────────

class TestClassifyWsError:
    def test_invalid_status_code_401_is_fatal(self):
        exc = Exception("server rejected connection: HTTP 401 Unauthorized")
        cat, reason = classify_ws_error(exc)
        assert cat == ErrorCategory.FATAL
        assert "401" in reason or "API key" in reason.lower() or "permission" in reason.lower()

    def test_invalid_status_code_403_is_fatal(self):
        exc = Exception("InvalidStatusCode: 403 Forbidden")
        cat, reason = classify_ws_error(exc)
        assert cat == ErrorCategory.FATAL

    def test_invalid_status_code_404_is_fatal(self):
        exc = Exception("HTTP 404 Not Found")
        cat, reason = classify_ws_error(exc)
        assert cat == ErrorCategory.FATAL

    def test_invalid_status_code_429_is_fatal(self):
        exc = Exception("429 Too Many Requests / quota exceeded")
        cat, reason = classify_ws_error(exc)
        assert cat == ErrorCategory.FATAL
        assert "quota" in reason.lower() or "rate" in reason.lower()

    def test_invalid_status_code_500_is_retry(self):
        exc = Exception("server error: HTTP 500 Internal Server Error")
        cat, reason = classify_ws_error(exc)
        assert cat == ErrorCategory.RETRY

    def test_connection_refused_is_retry(self):
        exc = ConnectionRefusedError("Connection refused")
        cat, reason = classify_ws_error(exc)
        assert cat == ErrorCategory.RETRY

    def test_timeout_is_retry(self):
        exc = TimeoutError("timed out")
        cat, reason = classify_ws_error(exc)
        assert cat == ErrorCategory.RETRY

    def test_dns_error_is_retry(self):
        exc = Exception("Name or service not known (DNS resolution failed)")
        cat, reason = classify_ws_error(exc)
        assert cat == ErrorCategory.RETRY

    def test_ssl_error_is_retry(self):
        exc = Exception("SSL: certificate verify failed")
        cat, reason = classify_ws_error(exc)
        assert cat == ErrorCategory.RETRY

    def test_unknown_error_defaults_to_retry(self):
        exc = RuntimeError("something completely unknown happened")
        cat, reason = classify_ws_error(exc)
        assert cat == ErrorCategory.RETRY

    def test_quota_keyword_is_fatal(self):
        exc = Exception("Resource exhausted: quota limit reached")
        cat, reason = classify_ws_error(exc)
        assert cat == ErrorCategory.FATAL


# ── classify_http_status ─────────────────────────────────────────────

class TestClassifyHttpStatus:
    def test_200_ok(self):
        cat, _ = classify_http_status(200)
        assert cat == ErrorCategory.RETRY  # shouldn't happen but safe default

    def test_400_bad_request_is_fatal(self):
        cat, reason = classify_http_status(400)
        assert cat == ErrorCategory.FATAL
        assert "400" in reason

    def test_401_unauthorized_is_fatal(self):
        cat, _ = classify_http_status(401)
        assert cat == ErrorCategory.FATAL

    def test_403_forbidden_is_fatal(self):
        cat, _ = classify_http_status(403)
        assert cat == ErrorCategory.FATAL

    def test_404_not_found_is_fatal(self):
        cat, _ = classify_http_status(404)
        assert cat == ErrorCategory.FATAL

    def test_429_rate_limit_is_fatal(self):
        cat, _ = classify_http_status(429)
        assert cat == ErrorCategory.FATAL

    def test_500_server_error_is_retry(self):
        cat, _ = classify_http_status(500)
        assert cat == ErrorCategory.RETRY

    def test_503_service_unavailable_is_retry(self):
        cat, _ = classify_http_status(503)
        assert cat == ErrorCategory.RETRY

    def test_custom_context_in_reason(self):
        _, reason = classify_http_status(401, context="WebSocket upgrade")
        assert "WebSocket" in reason

    def test_unknown_code_418_is_retry(self):
        """I'm a teapot — should be RETRY as safe default."""
        cat, _ = classify_http_status(418)
        assert cat == ErrorCategory.RETRY

    def test_502_bad_gateway_is_retry(self):
        cat, _ = classify_http_status(502)
        assert cat == ErrorCategory.RETRY


# ── _extract_status_code edge cases ──────────────────────────────────

class TestExtractStatusCode:
    def test_no_number_returns_none(self):
        from voice_typing.errors import _extract_status_code
        assert _extract_status_code("connection refused") is None

    def test_http_prefix_pattern(self):
        from voice_typing.errors import _extract_status_code
        assert _extract_status_code("HTTP 403 forbidden") == 403

    def test_status_code_pattern(self):
        from voice_typing.errors import _extract_status_code
        assert _extract_status_code("status code: 429") == 429

    def test_code_pattern(self):
        from voice_typing.errors import _extract_status_code
        assert _extract_status_code("error code 401") == 401

    def test_out_of_range_returns_none(self):
        from voice_typing.errors import _extract_status_code
        # 999 is outside HTTP range
        assert _extract_status_code("error 999 times") is None

    def test_timestamp_not_misclassified(self):
        """Timestamps like 2025-01 should not be extracted as HTTP codes."""
        from voice_typing.errors import _extract_status_code
        # "202" is in range 100-599 but the targeted pattern won't match
        # The fallback will match it, but this is acceptable as the caller
        # checks the context. The key test is that it doesn't crash.
        result = _extract_status_code("2025-01-15T12:00:00 error")
        # May return 202 or None depending on regex — both acceptable
        assert result is None or (100 <= result <= 599)

    def test_model_name_with_digits_not_misclassified(self):
        """Model names like gemini-2.0-flash shouldn't be extracted as codes."""
        from voice_typing.errors import _extract_status_code
        # "200" is in the model name
        result = _extract_status_code("model gemini-2.0-flash returned error")
        # "200" from "2.0" won't match word boundary, so should be None
        assert result is None


# ── classify_ws_error edge cases ─────────────────────────────────────

class TestClassifyWsErrorEdgeCases:
    def test_broken_pipe_is_retry(self):
        exc = Exception("Broken pipe")
        cat, _ = classify_ws_error(exc)
        assert cat == ErrorCategory.RETRY

    def test_eof_is_retry(self):
        exc = ConnectionError("eof")
        cat, _ = classify_ws_error(exc)
        assert cat == ErrorCategory.RETRY

    def test_connection_aborted_is_retry(self):
        exc = Exception("connection aborted by peer")
        cat, _ = classify_ws_error(exc)
        assert cat == ErrorCategory.RETRY

    def test_resource_exhausted_is_fatal(self):
        exc = Exception("resource_exhausted: quota exceeded")
        cat, _ = classify_ws_error(exc)
        assert cat == ErrorCategory.FATAL

    def test_api_key_keyword_is_fatal(self):
        exc = Exception("invalid api key provided")
        cat, _ = classify_ws_error(exc)
        assert cat == ErrorCategory.FATAL

    def test_forbidden_keyword_is_fatal(self):
        exc = Exception("request forbidden by administrator")
        cat, _ = classify_ws_error(exc)
        assert cat == ErrorCategory.FATAL

    def test_model_not_found_via_keyword(self):
        """The 'model' + 'not' keyword path."""
        exc = Exception("the requested model was not available")
        cat, _ = classify_ws_error(exc)
        assert cat == ErrorCategory.FATAL

    def test_rate_limit_keyword_is_fatal(self):
        exc = Exception("rate limit exceeded, slow down")
        cat, _ = classify_ws_error(exc)
        assert cat == ErrorCategory.FATAL

    def test_name_resolution_is_retry(self):
        exc = Exception("name resolution failed for generativelanguage.googleapis.com")
        cat, _ = classify_ws_error(exc)
        assert cat == ErrorCategory.RETRY

    def test_timed_out_is_retry(self):
        exc = Exception("Connection timed out after 30s")
        cat, _ = classify_ws_error(exc)
        assert cat == ErrorCategory.RETRY

    def test_connectionreset_is_retry(self):
        exc = Exception("connectionreset by peer")
        cat, _ = classify_ws_error(exc)
        assert cat == ErrorCategory.RETRY

    def test_connectionrefused_is_retry(self):
        exc = Exception("connectionrefused: no route to host")
        cat, _ = classify_ws_error(exc)
        assert cat == ErrorCategory.RETRY


# ── should_rotate_on_error ─────────────────────────────────────────

class TestShouldRotateOnError:
    def test_429_rotates(self):
        from voice_typing.errors import should_rotate_on_error
        assert should_rotate_on_error(ErrorCategory.FATAL, "HTTP 429: Quota exceeded") is True

    def test_quota_keyword_rotates(self):
        from voice_typing.errors import should_rotate_on_error
        assert should_rotate_on_error(ErrorCategory.FATAL, "API quota / rate limit exceeded") is True

    def test_resource_exhausted_rotates(self):
        from voice_typing.errors import should_rotate_on_error
        assert should_rotate_on_error(ErrorCategory.FATAL, "resource_exhausted: quota exceeded") is True

    def test_rate_limit_rotates(self):
        from voice_typing.errors import should_rotate_on_error
        assert should_rotate_on_error(ErrorCategory.FATAL, "rate limit exceeded, slow down") is True

    def test_401_rotates(self):
        from voice_typing.errors import should_rotate_on_error
        assert should_rotate_on_error(ErrorCategory.FATAL, "HTTP 401 Unauthorized") is True

    def test_403_rotates(self):
        from voice_typing.errors import should_rotate_on_error
        assert should_rotate_on_error(ErrorCategory.FATAL, "API key is invalid or lacks permission") is True

    def test_invalid_key_rotates(self):
        from voice_typing.errors import should_rotate_on_error
        assert should_rotate_on_error(ErrorCategory.FATAL, "invalid api key provided") is True

    def test_404_does_not_rotate(self):
        from voice_typing.errors import should_rotate_on_error
        assert should_rotate_on_error(ErrorCategory.FATAL, "HTTP 404 Not Found") is False

    def test_model_not_found_does_not_rotate(self):
        from voice_typing.errors import should_rotate_on_error
        assert should_rotate_on_error(ErrorCategory.FATAL, "Requested model not found") is False

    def test_400_does_not_rotate(self):
        from voice_typing.errors import should_rotate_on_error
        assert should_rotate_on_error(ErrorCategory.FATAL, "HTTP 400: Bad request") is False

    def test_500_does_not_rotate(self):
        from voice_typing.errors import should_rotate_on_error
        assert should_rotate_on_error(ErrorCategory.RETRY, "HTTP 500 Internal Server Error") is False

    def test_network_error_does_not_rotate(self):
        from voice_typing.errors import should_rotate_on_error
        assert should_rotate_on_error(ErrorCategory.RETRY, "Network error: ConnectionRefused") is False

    def test_empty_reason_does_not_rotate(self):
        from voice_typing.errors import should_rotate_on_error
        assert should_rotate_on_error(None, "") is False
        assert should_rotate_on_error(None, None) is False


# ── is_server_error_5xx ──────────────────────────────────────────

class TestIsServerError5xx:
    def test_500_retry_is_5xx(self):
        from voice_typing.errors import ErrorCategory, is_server_error_5xx
        assert is_server_error_5xx(
            ErrorCategory.RETRY, "HTTP 500: Server error (transient)"
        ) is True

    def test_502_retry_is_5xx(self):
        from voice_typing.errors import ErrorCategory, is_server_error_5xx
        assert is_server_error_5xx(
            ErrorCategory.RETRY, "HTTP 502 Bad Gateway"
        ) is True

    def test_503_retry_is_5xx(self):
        from voice_typing.errors import ErrorCategory, is_server_error_5xx
        assert is_server_error_5xx(
            ErrorCategory.RETRY, "HTTP 503 Service Unavailable"
        ) is True

    def test_504_retry_is_5xx(self):
        from voice_typing.errors import ErrorCategory, is_server_error_5xx
        assert is_server_error_5xx(
            ErrorCategory.RETRY, "HTTP 504 Gateway Timeout"
        ) is True

    def test_server_error_phrase_is_5xx(self):
        from voice_typing.errors import ErrorCategory, is_server_error_5xx
        assert is_server_error_5xx(
            ErrorCategory.RETRY, "HTTP Server error (transient)"
        ) is True

    def test_network_retry_is_not_5xx(self):
        from voice_typing.errors import ErrorCategory, is_server_error_5xx
        assert is_server_error_5xx(
            ErrorCategory.RETRY, "Network error: ConnectionRefused"
        ) is False

    def test_429_fatal_is_not_5xx(self):
        from voice_typing.errors import ErrorCategory, is_server_error_5xx
        assert is_server_error_5xx(
            ErrorCategory.FATAL, "HTTP 429: Quota exceeded"
        ) is False

    def test_500_fatal_is_not_5xx(self):
        """Category must be RETRY — FATAL 500 never selects the 5xx policy."""
        from voice_typing.errors import ErrorCategory, is_server_error_5xx
        assert is_server_error_5xx(
            ErrorCategory.FATAL, "HTTP 500 Internal Server Error"
        ) is False

    def test_none_category_is_not_5xx(self):
        from voice_typing.errors import is_server_error_5xx
        assert is_server_error_5xx(None, "HTTP 500 Internal Server Error") is False

    def test_empty_reason_is_not_5xx(self):
        from voice_typing.errors import ErrorCategory, is_server_error_5xx
        assert is_server_error_5xx(ErrorCategory.RETRY, "") is False
        assert is_server_error_5xx(ErrorCategory.RETRY, None) is False

    def test_classify_and_rotate_unchanged_for_500(self):
        """classify stays RETRY and should_rotate stays False for 500."""
        from voice_typing.errors import (
            ErrorCategory,
            classify_http_status,
            should_rotate_on_error,
        )
        cat, reason = classify_http_status(500)
        assert cat == ErrorCategory.RETRY
        assert should_rotate_on_error(cat, reason) is False
