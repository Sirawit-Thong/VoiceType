"""Tests for voice_typing.ai.text_normalize.

Contract under test:
  * normalize_thai_spacing(text: str, language: str = "auto") -> str
  * has_foreign_script(text: str) -> bool
  * normalize_transcript(text: str, language: str = "auto") -> str

Plus a read-only regression guard for LANGUAGE_INSTRUCTIONS in
voice_typing.speech.gemini_live.

All tests are synchronous (asyncio_mode="auto" is configured, but nothing
here needs an event loop).

Import strategy: voice_typing.ai.text_normalize is imported lazily INSIDE each
test so that the LANGUAGE_INSTRUCTIONS guard below still runs and reports
independently while the production module is being written. A missing module
surfaces as a RED per-test ERROR (ModuleNotFoundError) — never as a skip.
"""

import pytest

from voice_typing.speech.gemini_live import LANGUAGE_INSTRUCTIONS

# ---------------------------------------------------------------------------
# normalize_thai_spacing
# ---------------------------------------------------------------------------


def test_auto_mode_removes_spaces_between_thai_words():
    from voice_typing.ai.text_normalize import normalize_thai_spacing

    # default language argument must behave like "auto"
    assert normalize_thai_spacing("เออ แล้ว ครับ") == "เออแล้วครับ"
    assert normalize_thai_spacing("เออ แล้ว ครับ", "auto") == "เออแล้วครับ"
    # no leading/trailing spaces introduced by the removal
    assert normalize_thai_spacing("เออ แล้ว ครับ").strip() == "เออแล้วครับ"


def test_thai_mode_removes_spaces_between_thai_words():
    from voice_typing.ai.text_normalize import normalize_thai_spacing

    # explicit "thai" behaves the same as "auto" for Thai text
    assert normalize_thai_spacing("เออ แล้ว ครับ", "thai") == "เออแล้วครับ"
    assert normalize_thai_spacing("สวัสดี ครับ", "thai") == "สวัสดีครับ"


def test_english_mode_leaves_thai_with_spaces_unchanged():
    from voice_typing.ai.text_normalize import normalize_thai_spacing

    text = "เออ แล้ว ครับ"
    assert normalize_thai_spacing(text, "english") == text
    assert normalize_thai_spacing("สวัสดี ครับ", "english") == "สวัสดี ครับ"


def test_english_mode_returns_text_unchanged_verbatim():
    from voice_typing.ai.text_normalize import normalize_thai_spacing

    # Contract: language "english" returns text unchanged — applied literally,
    # even to runs of spaces (english mode does not even collapse them).
    for text in ("hello  world", "เออ แล้ว  ครับ", "  padded  "):
        assert normalize_thai_spacing(text, "english") == text


def test_space_between_thai_char_and_comma_is_kept():
    from voice_typing.ai.text_normalize import normalize_thai_spacing

    # "," is not a Thai char, so "both neighbors Thai" fails on BOTH sides:
    # the space sits between "บ" and "," (keep) and between "," and "แ" (keep).
    text = "ครับ , และ"
    assert normalize_thai_spacing(text) == text
    assert normalize_thai_spacing(text, "thai") == text
    assert normalize_thai_spacing(text, "english") == text


def test_spaces_around_thai_script_punctuation_like_etc_are_removed():
    from voice_typing.ai.text_normalize import normalize_thai_spacing

    # "ฯ" (U+0E2F) and "ๆ" (U+0E46) live inside the Thai block U+0E00-U+0E7F,
    # so they count as Thai neighbors and the spaces around them are removed.
    assert normalize_thai_spacing("เรียบร้อย ฯ ครับ") == "เรียบร้อยฯครับ"
    assert normalize_thai_spacing("ชอบ ๆ เลย") == "ชอบๆเลย"
    assert normalize_thai_spacing("เรียบร้อย ฯ ครับ", "thai") == "เรียบร้อยฯครับ"
    # ...but english mode must not touch them
    assert normalize_thai_spacing("ชอบ ๆ เลย", "english") == "ชอบ ๆ เลย"


def test_space_between_thai_and_english_word_is_kept():
    from voice_typing.ai.text_normalize import normalize_thai_spacing

    # Latin neighbor on one side => not "both neighbors Thai" => keep.
    text = "ผมใช้ Python เครื่องนี้"
    assert normalize_thai_spacing(text) == text
    assert normalize_thai_spacing(text, "thai") == text


def test_spaces_at_digit_boundaries_are_kept():
    from voice_typing.ai.text_normalize import normalize_thai_spacing

    # digits are not Thai script => keep
    assert normalize_thai_spacing("ปี 2024") == "ปี 2024"
    assert normalize_thai_spacing("ปี 2024 ครับ") == "ปี 2024 ครับ"


def test_double_spaces_between_thai_words_collapse_to_nothing():
    from voice_typing.ai.text_normalize import normalize_thai_spacing

    # a space run whose outer neighbors are both Thai is removed entirely
    # (collapse + Thai-neighbor removal happen within a single call)
    assert normalize_thai_spacing("สวัสดี  ครับ") == "สวัสดีครับ"
    assert normalize_thai_spacing("สวัสดี   ครับ") == "สวัสดีครับ"
    assert normalize_thai_spacing("สวัสดี  ครับ", "thai") == "สวัสดีครับ"


def test_double_spaces_at_non_thai_boundaries_collapse_to_single_space():
    from voice_typing.ai.text_normalize import normalize_thai_spacing

    # runs of 2+ spaces collapse to ONE space when the neighbors are not
    # both Thai (they must not be deleted entirely)
    assert normalize_thai_spacing("hello  world") == "hello world"
    assert normalize_thai_spacing("hello   world  again") == "hello world again"
    assert normalize_thai_spacing("ใช้  Python") == "ใช้ Python"


def test_leading_and_trailing_single_spaces_are_preserved():
    from voice_typing.ai.text_normalize import normalize_thai_spacing

    # normalize_thai_spacing does not strip ends (that is normalize_transcript's
    # job); a boundary space lacks a neighbor on one side => "both Thai" fails
    # => kept.
    assert normalize_thai_spacing(" สวัสดี ครับ ") == " สวัสดีครับ "


@pytest.mark.parametrize(
    "language",
    ["auto", "thai", "english"],
    ids=["auto", "thai", "english"],
)
@pytest.mark.parametrize(
    "text",
    [
        "เออ แล้ว ครับ",            # Thai words separated by single spaces
        "สวัสดี  ครับ",              # double space between Thai words
        "ผมใช้ Python เครื่องนี้",  # Thai/English mix
        "ปี 2024 ครับ",              # digit boundaries
        "ครับ , และ",                # space adjacent to non-Thai punctuation
        "  hello   world  ",         # Latin with space runs and edge spaces
    ],
    ids=[
        "thai-spaced",
        "thai-double-space",
        "thai-english-mix",
        "digit-boundary",
        "punct-boundary",
        "latin-spaces",
    ],
)
def test_normalize_thai_spacing_is_idempotent(text, language):
    from voice_typing.ai.text_normalize import normalize_thai_spacing

    once = normalize_thai_spacing(text, language)
    twice = normalize_thai_spacing(once, language)
    assert twice == once


@pytest.mark.parametrize("text", ["", "   ", "\t \t"], ids=["empty", "spaces", "mixed-ws"])
def test_normalize_thai_spacing_handles_empty_and_whitespace_without_raising(text):
    from voice_typing.ai.text_normalize import normalize_thai_spacing

    result = normalize_thai_spacing(text)
    assert result.strip() == ""  # no content materialises; whitespace may collapse


# ---------------------------------------------------------------------------
# has_foreign_script
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "สวัสดีครับ",                       # pure Thai
        "Hello, world!",                    # pure English
        "ผมใช้ Python 3 เครื่องนี้!",       # Thai + English + digits + punctuation
        "café",                             # accented Latin
        "naïve",                            # accented Latin
        "!!??",                             # punctuation only
        "123",                              # digits only
        "🙂🎉 !!",                           # emoji + punctuation
        "",                                 # empty
        "   \t\n",                          # whitespace only
    ],
    ids=[
        "pure-thai",
        "pure-english",
        "mixed-th-en-digits-punct",
        "accented-latin-cafe",
        "accented-latin-naive",
        "punct-only",
        "digits-only",
        "emoji-and-punct",
        "empty",
        "whitespace",
    ],
)
def test_has_foreign_script_returns_false_for_thai_latin_and_non_letters(text):
    from voice_typing.ai.text_normalize import has_foreign_script

    assert has_foreign_script(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "안녕하세요",          # Korean Hangul
        "こんにちは",          # Japanese Hiragana
        "カタカナ",            # Japanese Katakana
        "你好",                # Chinese CJK
        "привет",             # Cyrillic
        "مرحبا",              # Arabic
        "αβγ",                # Greek
        "สวัสดี안녕하세요",     # Thai mixed with Korean
    ],
    ids=[
        "korean",
        "japanese-hiragana",
        "japanese-katakana",
        "chinese",
        "cyrillic",
        "arabic",
        "greek",
        "thai-mixed-korean",
    ],
)
def test_has_foreign_script_returns_true_for_non_thai_latin_scripts(text):
    from voice_typing.ai.text_normalize import has_foreign_script

    assert has_foreign_script(text) is True


# ---------------------------------------------------------------------------
# normalize_transcript
# ---------------------------------------------------------------------------


def test_normalize_transcript_applies_thai_spacing_in_one_call():
    from voice_typing.ai.text_normalize import normalize_transcript

    assert normalize_transcript("เออ แล้ว ครับ") == "เออแล้วครับ"
    assert normalize_transcript("เออ แล้ว ครับ", "thai") == "เออแล้วครับ"
    # english mode still passes text through the spacing stage unchanged
    assert normalize_transcript("เออ แล้ว ครับ", "english") == "เออ แล้ว ครับ"


@pytest.mark.parametrize(
    "control",
    ["\x00", "\x07", "\x1b", "\x85"],
    ids=["NUL", "BEL", "ESC", "C1-NEL"],
)
def test_normalize_transcript_strips_control_chars(control):
    from voice_typing.ai.text_normalize import normalize_transcript

    # C0 controls are removed outright; the C1 case (\x85) may legally be
    # handled either by explicit C1 stripping or by treating it as runable
    # whitespace — either way the expected result is identical here because
    # the surrounding text is Thai and goes through Thai spacing afterwards.
    assert normalize_transcript(f"สวัสดี{control}ครับ") == "สวัสดีครับ"


def test_normalize_transcript_keeps_newlines():
    from voice_typing.ai.text_normalize import normalize_transcript

    # \n and \t are explicitly NOT stripped as control chars
    assert normalize_transcript("สวัสดี\nครับ") == "สวัสดี\nครับ"
    assert normalize_transcript("line one\nline two") == "line one\nline two"


def test_normalize_transcript_collapses_tabs_and_spaces_and_strips_ends():
    from voice_typing.ai.text_normalize import normalize_transcript

    assert normalize_transcript(" \tสวัสดี  ครับ\t ") == "สวัสดีครับ"
    assert normalize_transcript("  hello \t world  ") == "hello world"
    assert normalize_transcript("\t\tเออ แล้ว ครับ\n") == "เออแล้วครับ"


@pytest.mark.parametrize(
    "text",
    [
        "เออ แล้ว ครับ",
        "สวัสดี\x00ครับ",
        " \tสวัสดี  ครับ\t ",
        "สวัสดี\nครับ",
        "  hello   world  ",
        "🙂 !!123",
    ],
    ids=[
        "thai-spaced",
        "control-nul",
        "tab-and-space-runs",
        "thai-newline",
        "latin-spaces",
        "emoji-and-punct",
    ],
)
def test_normalize_transcript_is_idempotent(text):
    from voice_typing.ai.text_normalize import normalize_transcript

    once = normalize_transcript(text)
    twice = normalize_transcript(once)
    assert twice == once


@pytest.mark.parametrize("text", ["", "   ", "\t\n ", "🙂👍🎉"], ids=["empty", "spaces", "ws-plus-newline", "emoji-only"])
def test_normalize_transcript_never_raises_on_degenerate_input(text):
    from voice_typing.ai.text_normalize import normalize_transcript

    if text == "🙂👍🎉":
        assert normalize_transcript(text) == "🙂👍🎉"
    elif text.strip() == "":
        assert normalize_transcript(text) == ""
    else:  # pragma: no cover - defensive
        normalize_transcript(text)


# ---------------------------------------------------------------------------
# Regression guard for the wiring in voice_typing.speech.gemini_live
# (read-only: this file never edits voice_typing/**)
# ---------------------------------------------------------------------------

# The guard passes only if a prompt mentions spacing/script handling.
SPACE_OR_SCRIPT_TOKENS = ("space", "thai script", "transliterate")

# The prompts as they existed BEFORE the spacing work — kept here so this file
# documents (and proves) that the guard would reject them.
LEGACY_LANGUAGE_INSTRUCTIONS = {
    "auto": "Support both Thai and English. Transcribe speech naturally in the spoken language without translation.",
    "thai": "Transcribe the user's speech strictly into Thai (ภาษาไทย). Do not output English or translate into English. Write pure Thai script.",
    "english": "Transcribe the user's speech strictly into English. Do not output Thai or translate into Thai. Write in English.",
}


def _mentions_spacing(text: str) -> bool:
    lower = text.lower()
    return any(token in lower for token in SPACE_OR_SCRIPT_TOKENS)


def test_language_instructions_mention_spaces_or_script_for_every_language():
    for key in ("auto", "thai", "english"):
        assert key in LANGUAGE_INSTRUCTIONS, f"missing LANGUAGE_INSTRUCTIONS[{key!r}]"
        prompt = LANGUAGE_INSTRUCTIONS[key]
        assert isinstance(prompt, str) and prompt.strip(), (
            f"LANGUAGE_INSTRUCTIONS[{key!r}] must be a non-empty string"
        )
        assert _mentions_spacing(prompt), (
            f"LANGUAGE_INSTRUCTIONS[{key!r}] must mention spaces or script handling "
            f"(one of {SPACE_OR_SCRIPT_TOKENS}); got: {prompt!r}"
        )


def test_language_instructions_guard_rejects_legacy_prompts():
    # Documents that the guard above has teeth: the legacy prompts fail it.
    # (Legacy "auto" and "english" say nothing about spaces/scripts at all;
    # legacy "thai" happens to contain "Thai script" but the all-keys
    # assertion still fails on the legacy dict as a whole.)
    assert not _mentions_spacing(LEGACY_LANGUAGE_INSTRUCTIONS["auto"])
    assert not _mentions_spacing(LEGACY_LANGUAGE_INSTRUCTIONS["english"])
    assert any(
        not _mentions_spacing(prompt)
        for prompt in LEGACY_LANGUAGE_INSTRUCTIONS.values()
    )
