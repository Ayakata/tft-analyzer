from __future__ import annotations

from typing import Protocol

from tft_analyzer.capture.types import BackendFrame, WindowInfo


class CaptureBackend(Protocol):
    name: str

    def start(self, window: WindowInfo) -> None:
        ...

    def latest_frame(self) -> BackendFrame | None:
        ...

    def is_closed(self) -> bool:
        ...

    def error(self) -> Exception | None:
        ...

    def close(self) -> None:
        ...
