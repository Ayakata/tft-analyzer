from __future__ import annotations

import os
import re

from .types import WindowInfo


class WindowLocatorError(RuntimeError):
    pass


class WindowsWindowLocator:
    """Enumerate visible top-level Windows windows using client-area bounds."""

    def __init__(self) -> None:
        if os.name != "nt":
            raise WindowLocatorError("WindowsWindowLocator can only run on Windows.")

        try:
            import psutil  # noqa: F401
            import win32gui  # noqa: F401
            import win32process  # noqa: F401
        except ImportError as exc:
            raise WindowLocatorError(
                "Missing Windows dependencies. Run `pip install -e .`."
            ) from exc

    def _window_info(self, hwnd: int) -> WindowInfo | None:
        import psutil
        import win32gui
        import win32process

        if not win32gui.IsWindow(hwnd):
            return None

        title = win32gui.GetWindowText(hwnd).strip()
        if not title:
            return None

        try:
            left, top = win32gui.ClientToScreen(hwnd, (0, 0))
            rect = win32gui.GetClientRect(hwnd)
            width = int(rect[2] - rect[0])
            height = int(rect[3] - rect[1])
        except Exception:
            return None

        if width <= 0 or height <= 0:
            return None

        pid: int | None = None
        process_name: str | None = None
        try:
            _tid, pid = win32process.GetWindowThreadProcessId(hwnd)
            process_name = psutil.Process(pid).name()
        except Exception:
            pass

        return WindowInfo(
            handle=int(hwnd),
            title=title,
            process_id=pid,
            process_name=process_name,
            left=int(left),
            top=int(top),
            width=width,
            height=height,
            is_minimized=bool(win32gui.IsIconic(hwnd)),
        )

    def list_windows(self) -> list[WindowInfo]:
        import win32gui

        result: list[WindowInfo] = []

        def callback(hwnd: int, _extra: object) -> None:
            if not win32gui.IsWindowVisible(hwnd):
                return
            info = self._window_info(hwnd)
            if info is not None:
                result.append(info)

        win32gui.EnumWindows(callback, None)
        return sorted(result, key=lambda w: (w.title.lower(), w.handle))

    def find(
        self,
        *,
        title_regex: str | None = None,
        process_regex: str | None = None,
    ) -> list[WindowInfo]:
        title_re = re.compile(title_regex, re.IGNORECASE) if title_regex else None
        process_re = re.compile(process_regex, re.IGNORECASE) if process_regex else None

        found: list[WindowInfo] = []
        for window in self.list_windows():
            if title_re and not title_re.search(window.title):
                continue
            if process_re and not process_re.search(window.process_name or ""):
                continue
            found.append(window)
        return found

    def get_by_handle(self, handle: int) -> WindowInfo | None:
        return self._window_info(handle)
