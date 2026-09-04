# tests/test_redaction.py
from voice_typing.providers.redaction import (
    redact_headers,
    redact_text,
    redact_url,
    safe_error,
)

GOOGLE_KEY = "AIzaFakeTestKey0123456789abcdef"
OPENAI_KEY = "sk-fake-test-key-0123456789abcdefghij"
DEEPGRAM_KEY = "dg_fake_test_key_0123456789abcdef"


def test_redact_text_removes_google_key():
    assert GOOGLE_KEY not in redact_text(f"API error 403: key {GOOGLE_KEY} invalid")


def test_redact_text_removes_bearer_key():
    out = redact_text(f"Authorization: Bearer {OPENAI_KEY}")
    assert OPENAI_KEY not in out
    assert "Bearer" in out


def test_redact_text_removes_query_key():
    out = redact_text(f"https://example.com/v1beta/models?key={GOOGLE_KEY}&pageSize=1000")
    assert GOOGLE_KEY not in out
    assert "pageSize=1000" in out


def test_redact_text_removes_assigned_tokens():
    assert OPENAI_KEY not in redact_text(f"api_key={OPENAI_KEY}")
    assert DEEPGRAM_KEY not in redact_text("token: dg_fake_test_key_0123456789abcdef")


def test_redact_url_keeps_structure():
    out = redact_url(f"wss://example.com/ws?key={GOOGLE_KEY}")
    assert GOOGLE_KEY not in out
    assert out.startswith("wss://example.com/ws?")


def test_redact_headers_masks_auth_values():
    headers = {"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "audio/wav"}
    out = redact_headers(headers)
    assert OPENAI_KEY not in out["Authorization"]
    assert out["Content-Type"] == "audio/wav"


def test_safe_error_truncates_and_redacts():
    try:
        raise RuntimeError(f"API error 401 with key {GOOGLE_KEY} " + "x" * 500)
    except RuntimeError as exc:
        out = safe_error(exc, prefix="Gemini connect failed: ")
    assert GOOGLE_KEY not in out
    assert out.startswith("Gemini connect failed: ")
    assert len(out) <= len("Gemini connect failed: ") + 300


def test_posture_token_carries_no_key_material():
    from voice_typing.config import credential_store as _cs

    token = _cs.posture_token()
    assert token in ("credential_store=vault", "credential_store=fallback(plaintext)")
    for secret in (GOOGLE_KEY, OPENAI_KEY, DEEPGRAM_KEY):
        assert secret not in token
    assert redact_text(token) == token
