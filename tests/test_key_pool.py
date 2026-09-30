# tests/test_key_pool.py
"""Tests for voice_typing.speech.key_pool — sequential active-standby pool."""

import logging

from voice_typing.speech.key_pool import KeyPool


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_normalize_keys_strips_dedupes_drops_blanks():
    assert KeyPool.normalize_keys(["  test-key-1 ", "", "  ", "test-key-1", "test-key-2"]) == [
        "test-key-1",
        "test-key-2",
    ]


def test_normalize_keys_ignores_non_strings():
    assert KeyPool.normalize_keys(["test-key-1", None, 123, "test-key-2"]) == [
        "test-key-1",
        "test-key-2",
    ]


def test_mask_never_reveals_full_key(caplog):
    key = "test-key-1234567890"
    masked = KeyPool.mask(key)
    assert key not in masked
    assert masked.endswith("7890")
    assert KeyPool.mask("") == "(empty)"
    assert KeyPool.mask(None) == "(empty)"
    assert KeyPool.mask("ab") == "****"
    with caplog.at_level(logging.INFO):
        pool = KeyPool(["test-key-1234567890"])
        pool.mark_failure()
        pool.advance()
    for record in caplog.records:
        assert key not in record.getMessage()


def test_empty_pool_is_exhausted():
    pool = KeyPool([])
    assert pool.size == 0
    assert pool.current_key == ""
    assert pool.is_exhausted is True
    assert pool.available_keys == []
    assert pool.advance() == ""


def test_current_key_and_index():
    pool = KeyPool(["test-key-1", "test-key-2"])
    assert pool.size == 2
    assert pool.current_index == 0
    assert pool.current_key == "test-key-1"
    assert pool.is_exhausted is False
    assert pool.available_keys == ["test-key-1", "test-key-2"]


def test_advance_cycles_sequentially():
    pool = KeyPool(["test-key-1", "test-key-2", "test-key-3"])
    assert pool.advance() == "test-key-2"
    assert pool.current_index == 1
    assert pool.advance() == "test-key-3"
    assert pool.advance() == "test-key-1"


def test_mark_failure_cools_down_and_advance_skips():
    clock = FakeClock()
    pool = KeyPool(["test-key-1", "test-key-2"], cooldown_seconds=60.0, time_func=clock)
    pool.mark_failure()  # fails test-key-1
    assert pool.available_keys == ["test-key-2"]
    assert pool.is_exhausted is False
    assert pool.advance() == "test-key-2"
    pool.mark_failure()  # fails test-key-2
    assert pool.is_exhausted is True
    assert pool.available_keys == []
    # All on cooldown: advance stays put.
    assert pool.advance() == "test-key-2"
    # After cooldown expires both are available again.
    clock.advance(61.0)
    assert pool.is_exhausted is False
    assert pool.available_keys == ["test-key-1", "test-key-2"]


def test_mark_success_clears_cooldown():
    clock = FakeClock()
    pool = KeyPool(["test-key-1", "test-key-2"], time_func=clock)
    pool.mark_failure("test-key-1")
    assert pool.is_exhausted is False
    pool.mark_failure("test-key-2")
    assert pool.is_exhausted is True
    pool.mark_success("test-key-1")
    assert pool.is_exhausted is False
    assert pool.available_keys == ["test-key-1"]


def test_set_keys_resets_pool():
    clock = FakeClock()
    pool = KeyPool(["test-key-1"], time_func=clock)
    pool.mark_failure()
    assert pool.is_exhausted is True
    pool.set_keys(["test-key-A", "test-key-B"])
    assert pool.size == 2
    assert pool.current_index == 0
    assert pool.current_key == "test-key-A"
    assert pool.is_exhausted is False


def test_add_and_remove_key():
    pool = KeyPool(["test-key-1"])
    assert pool.add_key("test-key-2") is True
    assert pool.size == 2
    assert pool.add_key("test-key-2") is False  # duplicate
    assert pool.add_key("   ") is False  # blank
    assert pool.remove_key("test-key-1") is True
    assert pool.keys == ["test-key-2"]
    assert pool.remove_key("missing") is False


def test_keys_property_returns_copy():
    pool = KeyPool(["test-key-1"])
    keys = pool.keys
    keys.append("mutated")
    assert pool.keys == ["test-key-1"]
