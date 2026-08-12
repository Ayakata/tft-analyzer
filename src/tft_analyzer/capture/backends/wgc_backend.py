from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from io import BytesIO

import numpy as np
from PIL import Image

from tft_analyzer.capture.types import BackendFrame, CapturedFrame, WindowInfo


class WGCWindowCaptureBackend:
    """Windows Graphics Capture backend targeting an exact HWND.

    Compatibility rule: optional Graphics Capture capability toggles are left at
    ``None`` unless explicitly requested. Older Windows 10 builds may reject
    attempts to toggle features such as the capture border. Frame-rate limiting
    is therefore done in our callback rather than through the optional native
    ``minimum_update_interval`` setting.
    """

    name = "wgc"

    def __init__(
        self,
        *,
        target_fps: float = 4.0,
        first_frame_timeout_seconds: float = 4.0,
        cursor_capture: bool | None = None,
        draw_border: bool | None = None,
    ) -> None:
        self.target_fps = max(float(target_fps), 0.1)
        self.first_frame_timeout_seconds = max(
            float(first_frame_timeout_seconds), 0.1
        )
        self.cursor_capture = cursor_capture
        self.draw_border = draw_border

        self._lock = threading.Lock()
        self._latest: BackendFrame | None = None
        self._sequence = 0
        self._capture = None
        self._control = None
        self._closed = threading.Event()
        self._error: Exception | None = None

        self._min_callback_interval_s = 1.0 / self.target_fps
        self._last_accepted_frame_at = float("-inf")

    def start(self, window: WindowInfo) -> None:
        try:
            from windows_capture import Frame, InternalCaptureControl, WindowsCapture
        except ImportError as exc:
            raise RuntimeError(
                "WGC backend requires `windows-capture==2.0.1`. "
                "Run `python -m pip install -e \".[dev]\"`."
            ) from exc

        # IMPORTANT: secondary_window, minimum_update_interval and dirty_region
        # stay None. Passing False/integers asks Windows to toggle optional WGC
        # capabilities which are not available on every Windows 10 build.
        capture = WindowsCapture(
            cursor_capture=self.cursor_capture,
            draw_border=self.draw_border,
            secondary_window=None,
            minimum_update_interval=None,
            dirty_region=None,
            monitor_index=None,
            window_name=None,
            window_hwnd=window.handle,
        )

        @capture.event
        def on_frame_arrived(
            frame: Frame,
            capture_control: InternalCaptureControl,
        ) -> None:
            try:
                now = time.monotonic()

                # WGC may deliver frames at the game's refresh rate. We only need
                # a few frames per second for the recorder/perception pipeline.
                if now - self._last_accepted_frame_at < self._min_callback_interval_s:
                    return
                self._last_accepted_frame_at = now

                # Copy while the native mapped frame is still valid.
                bgr = frame.convert_to_bgr().frame_buffer
                rgb = np.ascontiguousarray(bgr[:, :, ::-1])

                image = Image.fromarray(rgb)
                buf = BytesIO()
                image.save(buf, format="PNG", optimize=False)

                captured = CapturedFrame(
                    timestamp_s=now,
                    wall_time_iso=datetime.now(timezone.utc).isoformat(),
                    width=int(frame.width),
                    height=int(frame.height),
                    png_bytes=buf.getvalue(),
                )

                with self._lock:
                    self._latest = BackendFrame(
                        sequence=self._sequence,
                        frame=captured,
                    )
                    self._sequence += 1
            except Exception as exc:
                self._error = exc
                self._closed.set()
                capture_control.stop()

        @capture.event
        def on_closed() -> None:
            self._closed.set()

        self._capture = capture

        try:
            self._control = capture.start_free_threaded()
        except Exception:
            self._capture = None
            raise

        # Fail early so MatchSession can switch to the configured fallback.
        deadline = time.monotonic() + self.first_frame_timeout_seconds
        while time.monotonic() < deadline:
            err = self.error()
            if err is not None:
                self.close()
                raise RuntimeError(f"WGC capture failed: {err}") from err

            if self.latest_frame() is not None:
                return

            if self.is_closed():
                self.close()
                raise RuntimeError(
                    "WGC capture closed before the first frame arrived."
                )

            time.sleep(0.02)

        self.close()
        raise TimeoutError(
            "WGC did not produce a frame within "
            f"{self.first_frame_timeout_seconds:.1f}s."
        )

    def latest_frame(self) -> BackendFrame | None:
        with self._lock:
            return self._latest

    def is_closed(self) -> bool:
        if self._closed.is_set():
            return True

        control = self._control
        if control is not None:
            try:
                if control.is_finished():
                    return True
            except Exception as exc:
                self._error = exc
                return True

        return False

    def error(self) -> Exception | None:
        return self._error

    def close(self) -> None:
        self._closed.set()
        control = self._control
        self._control = None

        if control is not None:
            try:
                control.stop()
            except Exception:
                pass
            try:
                control.wait()
            except Exception:
                pass

        self._capture = None
