# voice_typing/ai/text_normalize.py
"""Normalization applied to outgoing transcripts.

Fixes two known model-output problems:
1. Gemini Live often writes Thai with a space between every word
   (e.g. "เออ แล้ว ครับ") — Thai script has no inter-word spaces.
2. Occasionally a non-Thai/non-English script (Korean, Japanese, ...)
   leaks into the transcript even though only Thai/English are offered.
"""
from __future__ import annotations

import re
import unicodedata

_THAI_MIN = 0x0E00
_THAI_MAX = 0x0E7F


def _is_thai(ch: str) -> bool:
    """True when ch is in the Thai block U+0E00-U+0E7F (letters + marks)."""
    return _THAI_MIN <= ord(ch) <= _THAI_MAX


def normalize_thai_spacing(text: str, language: str = "auto") -> str:
    """Remove spaces that sit between two Thai script characters.

    - language "thai" or "auto": remove a space when BOTH neighbors are Thai
      script chars (Unicode block U+0E00-U+0E7F, including combining marks
      above/below such as tone marks and vowels).
    - language "english": return text unchanged (no Thai joining needed).
    - Also collapse runs of 2+ spaces into one. Do NOT touch spaces that are
      adjacent to Latin letters, digits, or punctuation.
    - Must be idempotent: normalize(normalize(x)) == normalize(x).
    """
    if not text:
        return text
    if language == "english":
        return text
    # Collapse runs of 2+ spaces FIRST, then join: running the join before the
    # collapse would leave one space behind in "Thai<sp><sp>Thai" and break
    # idempotency.
    text = re.sub(r" {2,}", " ", text)
    out: list[str] = []
    for i, ch in enumerate(text):
        if (
            ch == " "
            and i > 0
            and i + 1 < len(text)
            and _is_thai(text[i - 1])
            and _is_thai(text[i + 1])
        ):
            continue  # drop the space: both neighbors are Thai
        out.append(ch)
    return "".join(out)


def has_foreign_script(text: str) -> bool:
    """True if text contains any letter that is neither Thai (U+0E00-U+0E7F)
    nor Latin (ASCII letters + Latin-1/extended letters) nor a digit.

    Unicode name based classification: an alphabetic char is allowed when its
    unicodedata name contains "LATIN" or "THAI"; any other alphabetic char
    (HANGUL, CJK, CYRILLIC, GREEK, ARABIC, ...) is foreign. Non-alphabetic
    chars (digits, punctuation, spaces, emoji, combining marks, ZWJ, ...) are
    never foreign by themselves.
    """
    if not text:
        return False
    for ch in text:
        if not ch.isalpha():
            continue
        name = unicodedata.name(ch, "")
        if "LATIN" in name or "THAI" in name:
            continue
        return True
    return False


def normalize_transcript(text: str, language: str = "auto") -> str:
    """Pipeline applied to every outgoing transcript:
    1. strip control characters except \n and \t (map other C0/C1 to "")
    2. collapse runs of spaces/tabs (keep \n as-is if present)
    3. normalize_thai_spacing(text, language)
    4. .strip() the ends
    Idempotent. Must never raise on any str input (empty, only spaces, emoji).
    """
    if not text:
        return text
    # 1. Remove C0/C1 control characters (and DEL), keeping only \n and \t.
    text = "".join(
        ch
        for ch in text
        if ch in "\n\t" or not (ord(ch) < 0x20 or 0x7F <= ord(ch) <= 0x9F)
    )
    # 2. Collapse runs of 2+ spaces/tabs into one space; \n is kept as-is.
    text = re.sub(r"[ \t]{2,}", " ", text)
    # 3. Join Thai words the model separated with spaces.
    text = normalize_thai_spacing(text, language)
    # 4. Trim the ends.
    return text.strip()
