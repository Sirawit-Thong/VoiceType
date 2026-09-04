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


def test_worker_loads_legacy_str_list(tmp_path):
    import json

    from voice_typing.config.settings import SettingsManager
    cfg = tmp_path / "settings.json"
    settings = SettingsManager(cfg)
    settings.load()
    hist = tmp_path / "history.json"
    hist.write_text(json.dumps(["a", "b"]), encoding="utf-8")
    from voice_typing.app import WorkerThread
    w = WorkerThread.__new__(WorkerThread)
    w._settings = settings
    w._history_path = hist
    loaded = WorkerThread._load_history(w)
    assert [e["text"] for e in loaded] == ["a", "b"]
    assert all(e["pinned"] is False for e in loaded)


def test_worker_clear_history_keeps_pinned(tmp_path):
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    cfg = tmp_path / "settings.json"
    settings = SettingsManager(cfg)
    settings.load()
    w = WorkerThread.__new__(WorkerThread)
    w._settings = settings
    w._history_path = tmp_path / "history.json"
    import voice_typing.app as appmod
    w._signals = appmod.WorkerSignals()
    w._history = [
        {"text": "keep", "pinned": True, "created_at": NOW},
        {"text": "drop", "pinned": False, "created_at": NOW},
    ]
    w.clear_history(keep_pinned=True)
    assert [e["text"] for e in w._history] == ["keep"]


import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_history_dialog_filter_clear_pinned(qapp):
    from voice_typing.ui.history_dialog import HistoryDialog
    history = [
        _mk("alpha"), _mk("beta", pinned=True), _mk("gamma"), _mk("alpha"),
    ]
    d = HistoryDialog(history)
    d._search.setText("alpha")
    visible = [d._list.itemText(i) for i in range(d._list.count())]
    assert visible.count("alpha") == 1  # pinned row stays; unpinned dedup'ed
    assert "beta" not in visible  # "beta" does not match "alpha" filter
    d._search.clear()  # show all to pin alpha
    d._list.setCurrentText("alpha")
    d._on_pin()
    updated = [e for e in d.history if e["text"] == "alpha"]
    assert any(e.get("pinned") for e in updated), "alpha should be pinned"
    d2 = HistoryDialog(d.history)
    d2._on_clear()
    texts = [e["text"] for e in d2.history]
    assert "beta" in texts  # beta was pinned
    assert "alpha" in texts  # alpha was just pinned
