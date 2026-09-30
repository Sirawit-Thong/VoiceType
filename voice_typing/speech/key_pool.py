# voice_typing/speech/key_pool.py
"""Sequential active-standby pool of Gemini API keys.

Only one key is active at a time (never parallel WebSocket connections).
Failed keys are put on cooldown; callers rotate with :meth:`advance`.

Pure stdlib (+ :mod:`voice_typing.errors` types only) — no Qt, no network.
All logging uses :meth:`KeyPool.mask` so raw key material never hits logs.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterable

log = logging.getLogger(__name__)


class KeyPool:
    """Ordered pool of API keys with per-key cooldown."""

    def __init__(
        self,
        keys: Iterable[str] | None = None,
        cooldown_seconds: float = 60.0,
        time_func: Callable[[], float] | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._cooldown = max(0.0, float(cooldown_seconds))
        self._time: Callable[[], float] = time_func or time.monotonic
        self._keys: list[str] = self.normalize_keys(keys or [])
        self._index = 0
        # key -> monotonic timestamp when cooldown expires
        self._cooldown_until: dict[str, float] = {}

    # -- static helpers -------------------------------------------------
    @staticmethod
    def normalize_keys(keys: Iterable[str]) -> list[str]:
        """Strip, drop blanks/non-strings, dedupe preserving order."""
        seen: set[str] = set()
        out: list[str] = []
        for k in keys:
            if not isinstance(k, str):
                continue
            s = k.strip()
            if not s or s in seen:
                continue
            seen.add(s)
            out.append(s)
        return out

    @staticmethod
    def mask(key: str | None) -> str:
        """Return a log-safe masked representation (never the raw key)."""
        if not key or not isinstance(key, str):
            return "(empty)"
        s = key.strip()
        if len(s) <= 4:
            return "****"
        return f"****{s[-4:]}"

    # -- properties -----------------------------------------------------
    @property
    def keys(self) -> list[str]:
        with self._lock:
            return list(self._keys)

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._keys)

    @property
    def current_index(self) -> int:
        with self._lock:
            return self._index

    @property
    def current_key(self) -> str:
        with self._lock:
            if not self._keys:
                return ""
            return self._keys[self._index % len(self._keys)]

    @property
    def is_exhausted(self) -> bool:
        with self._lock:
            if not self._keys:
                return True
            now = self._time()
            for k in self._keys:
                if self._cooldown_until.get(k, 0.0) <= now:
                    return False
            return True

    @property
    def available_keys(self) -> list[str]:
        with self._lock:
            now = self._time()
            return [k for k in self._keys if self._cooldown_until.get(k, 0.0) <= now]

    # -- mutation -------------------------------------------------------
    def set_keys(self, keys: Iterable[str]) -> None:
        normalized = self.normalize_keys(keys)
        with self._lock:
            self._keys = normalized
            self._index = 0
            # Drop cooldown entries for keys no longer in the pool.
            self._cooldown_until = {
                k: v for k, v in self._cooldown_until.items() if k in set(normalized)
            }
        log.debug("KeyPool set: %d key(s)", len(normalized))

    def add_key(self, key: str) -> bool:
        if not isinstance(key, str):
            return False
        s = key.strip()
        if not s:
            return False
        with self._lock:
            if s in self._keys:
                return False
            self._keys.append(s)
        log.info("KeyPool: added key %s (n=%d)", self.mask(s), len(self._keys))
        return True

    def remove_key(self, key: str) -> bool:
        if not isinstance(key, str):
            return False
        s = key.strip()
        with self._lock:
            if s not in self._keys:
                return False
            pos = self._keys.index(s)
            self._keys.remove(s)
            self._cooldown_until.pop(s, None)
            if not self._keys:
                self._index = 0
            else:
                if pos < self._index:
                    self._index -= 1
                self._index %= len(self._keys)
        log.info("KeyPool: removed key %s (n=%d)", self.mask(s), len(self._keys))
        return True

    def advance(self) -> str:
        """Move to the next available (non-cooldown) key; return current key."""
        with self._lock:
            if not self._keys:
                return ""
            now = self._time()
            n = len(self._keys)
            for step in range(1, n + 1):
                candidate = (self._index + step) % n
                k = self._keys[candidate]
                if self._cooldown_until.get(k, 0.0) <= now:
                    self._index = candidate
                    log.info(
                        "KeyPool: active key %d/%d (%s)",
                        self._index + 1, n, self.mask(k),
                    )
                    return k
            # All keys on cooldown — stay put.
            cur = self._keys[self._index % n]
            log.warning(
                "KeyPool: all %d key(s) on cooldown; staying on key %d/%d (%s)",
                n, self._index + 1, n, self.mask(cur),
            )
            return cur

    def mark_success(self, key: str | None = None) -> None:
        target = (key.strip() if isinstance(key, str) and key.strip() else None)
        with self._lock:
            if target is None and self._keys:
                target = self._keys[self._index % len(self._keys)]
            if target is not None:
                self._cooldown_until.pop(target, None)
        if target is not None:
            log.debug("KeyPool: key %s marked healthy", self.mask(target))

    def mark_failure(self, key: str | None = None) -> None:
        target = (key.strip() if isinstance(key, str) and key.strip() else None)
        with self._lock:
            if target is None and self._keys:
                target = self._keys[self._index % len(self._keys)]
            if target is not None:
                self._cooldown_until[target] = self._time() + self._cooldown
        if target is not None:
            log.warning(
                "KeyPool: key %s on cooldown (%.0fs)",
                self.mask(target), self._cooldown,
            )
