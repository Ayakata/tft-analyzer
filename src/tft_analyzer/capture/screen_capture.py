from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from time import monotonic

import mss
from PIL import Image

from .types import CapturedFrame, WindowInfo


class MSSScreenCapture:
    def __init__(self) -> None:
        self._mss = mss.mss()

    def close(self) -> None:
        self._mss.close()

    def capture_window(self, window: WindowInfo) -> CapturedFrame:
        shot = self._mss.grab(window.region)
        image = Image.frombytes("RGB", shot.size, shot.rgb)

        buf = BytesIO()
        image.save(buf, format="PNG", optimize=False)

        return CapturedFrame(
            timestamp_s=monotonic(),
            wall_time_iso=datetime.now(timezone.utc).isoformat(),
            width=image.width,
            height=image.height,
            png_bytes=buf.getvalue(),
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
