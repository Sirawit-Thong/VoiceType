# voice_typing/speech/engine.py
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable


class TranscriptBuffer:
    def __init__(self) -> None:
        self._current = ""

    @property
    def current(self) -> str:
        return self._current

    def add_partial(self, text: str) -> None:
        self._current = text

    def finalize(self) -> str:
        result = self._current
        self._current = ""
        return result

    def reset(self) -> None:
        self._current = ""


class STTEngine(ABC):
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def send_audio(self, audio_bytes: bytes) -> None: ...

    @abstractmethod
    async def receive_transcript(
        self, on_partial: Callable[[str], None], on_final: Callable[[str], None]
    ) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...
