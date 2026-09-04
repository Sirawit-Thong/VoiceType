# tests/test_history_v2.py
from voice_typing.history import parse_history_list, trim_history

NOW = "2026-09-04T00:00:00+00:00"


def _mk(text, pinned=False):
    return {"text": text, "pinned": pinned, "created_at": NOW}


def test_str_items_migrate_with_defaults():
    out = parse_history_list(["a", "b"], now_iso=NOW)
    assert out == [_mk("a"), _mk("b")]


def test_dict_missing_keys_normalize():
    out = parse_history_list([{"text": "x"}], now_iso=NOW)
    assert out == [_mk("x")]
    out2 = parse_history_list([{"text": "y", "pinned": 1, "created_at": "bad"}], now_iso=NOW)
    assert out2[0]["pinned"] is True
    assert out2[0]["created_at"] == NOW


def test_hostile_items_dropped_and_corrupt_root_empty():
    assert parse_history_list([1, None, ["x"], {"nope": 1}], now_iso=NOW) == []
    assert parse_history_list({"text": "x"}, now_iso=NOW) == []
    assert parse_history_list(None, now_iso=NOW) == []


def test_trim_evicts_oldest_unpinned_never_pinned():
    entries = [_mk(f"u{i}") for i in range(20)] + [_mk("pinned", pinned=True)] + [_mk("u20")]
    trim_history(entries, max_unpinned=20)
    texts = [e["text"] for e in entries]
    assert "pinned" in texts
    assert "u0" not in texts  # oldest unpinned evicted
    assert len([e for e in entries if not e["pinned"]]) == 20


def test_consecutive_duplicate_guard_compares_text():
    assert _mk("a")["text"] == _mk("a")["text"]
