from __future__ import annotations


def create_capture_backend(
    name: str,
    *,
    target_fps: float,
    first_frame_timeout_seconds: float,
    cursor_capture: bool | None,
    draw_border: bool | None,
):
    normalized = name.strip().lower()

    if normalized == "wgc":
        from tft_analyzer.capture.backends.wgc_backend import WGCWindowCaptureBackend

        return WGCWindowCaptureBackend(
            target_fps=target_fps,
            first_frame_timeout_seconds=first_frame_timeout_seconds,
            cursor_capture=cursor_capture,
            draw_border=draw_border,
        )

    if normalized == "mss":
        from tft_analyzer.capture.backends.mss_backend import MSSWindowCaptureBackend

        return MSSWindowCaptureBackend()

    raise ValueError(
        f"Unknown capture backend {name!r}. Supported: wgc, mss."
    )
