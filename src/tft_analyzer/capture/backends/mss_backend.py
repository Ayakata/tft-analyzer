from __future__ import annotations

from tft_analyzer.capture.screen_capture import MSSScreenCapture
from tft_analyzer.capture.types import BackendFrame, WindowInfo
from tft_analyzer.capture.window_locator import WindowsWindowLocator


class MSSWindowCaptureBackend:
    """Desktop-region fallback; does not survive window occlusion."""

    name = "mss"

    def __init__(self) -> None:
        self._window: WindowInfo | None = None
        self._capture: MSSScreenCapture | None = None
        self._locator: WindowsWindowLocator | None = None
        self._sequence = 0
        self._closed = False
        self._error: Exception | None = None

    def start(self, window: WindowInfo) -> None:
        self._window = window
        self._locator = WindowsWindowLocator()
        self._capture = MSSScreenCapture()

    def latest_frame(self) -> BackendFrame | None:
        if self._closed or self._capture is None or self._window is None:
            return None

        try:
            assert self._locator is not None
            current = self._locator.get_by_handle(self._window.handle)
            if current is None:
                self._closed = True
                return None
            if current.is_minimized:
                return None

            frame = self._capture.capture_window(current)
            packet = BackendFrame(sequence=self._sequence, frame=frame)
            self._sequence += 1
            return packet
        except Exception as exc:
            self._error = exc
            self._closed = True
            return None

    def is_closed(self) -> bool:
        return self._closed

    def error(self) -> Exception | None:
        return self._error

    def close(self) -> None:
        self._closed = True
        if self._capture is not None:
            self._capture.close()
            self._capture = None
