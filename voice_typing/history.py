# voice_typing/history.py
"""Pure history-v2 helpers: no Qt, no disk. All I/O lives in app.py."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

MAX_HISTORY = 20


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def normalize_history_entry(item: Any, now_iso: str | None = None) -> dict | None:
    """Coerce one raw history.json item to {"text","pinned","created_at"} or None to drop."""
    now = now_iso or _now_iso()
    if isinstance(item, str):
        if not item:
            return None
        return {"text": item, "pinned": False, "created_at": now}
    if isinstance(item, dict):
        text = item.get("text")
        if not isinstance(text, str) or not text:
            return None
        pinned = item.get("pinned", False)
        created = item.get("created_at")
        if not isinstance(created, str) or not created:
            created = now
        else:
            try:
                datetime.fromisoformat(created)
            except ValueError:
                created = now
        return {"text": text, "pinned": bool(pinned), "created_at": created}
    return None


def parse_history_list(loaded: Any, now_iso: str | None = None) -> list[dict]:
    """Normalize a whole history.json root; corrupt root -> []. Never raises."""
    if not isinstance(loaded, list):
        return []
    out: list[dict] = []
    for item in loaded:
        entry = normalize_history_entry(item, now_iso)
        if entry is not None:
            out.append(entry)
    return out


def trim_history(entries: list[dict], max_unpinned: int = MAX_HISTORY) -> list[dict]:
    """Evict oldest unpinned first; pinned entries are never evicted. Mutates + returns list."""
    unpinned_idx = [i for i, e in enumerate(entries) if not e.get("pinned")]
    overflow = len(unpinned_idx) - max_unpinned
    if overflow <= 0:
        return entries
    drop = set(unpinned_idx[:overflow])
    kept = [e for i, e in enumerate(entries) if i not in drop]
    del entries[:]
    entries.extend(kept)
    return entries
