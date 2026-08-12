from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WindowInfo:
    handle: int
    title: str
    process_id: int | None
    process_name: str | None
    left: int
    top: int
    width: int
    height: int
    is_minimized: bool = False

    @property
    def region(self) -> dict[str, int]:
        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True, slots=True)
class CapturedFrame:
    timestamp_s: float
    wall_time_iso: str
    width: int
    height: int
    png_bytes: bytes


@dataclass(frozen=True, slots=True)
class BackendFrame:
    sequence: int
    frame: CapturedFrame
