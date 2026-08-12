from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from tft_analyzer import __version__
from tft_analyzer.capture.backends.factory import create_capture_backend
from tft_analyzer.core.models import MatchManifest, PipelineVersions
from tft_analyzer.storage import EvidenceStore

from .clock import elapsed_seconds
from .scene_change import SceneChangeDetector
from .types import WindowInfo
from .window_locator import WindowsWindowLocator


@dataclass(frozen=True, slots=True)
class RecorderSettings:
    backend: str = "wgc"
    fallback_backend: str | None = "mss"
    target_fps: float = 4.0
    first_frame_timeout_seconds: float = 4.0
    capture_gap_after_seconds: float = 2.0
    cursor_capture: bool | None = None
    draw_border: bool | None = None
    keyframe_interval_seconds: float = 10.0
    min_scene_save_interval_seconds: float = 0.75
    save_periodic_keyframes: bool = True
    save_on_scene_change: bool = True


class MatchSession:
    def __init__(
        self,
        *,
        data_root: Path,
        window: WindowInfo,
        scene_detector: SceneChangeDetector,
        settings: RecorderSettings,
    ) -> None:
        self.window = window
        self.scene_detector = scene_detector
        self.settings = settings

        now = datetime.now(timezone.utc)
        self.match_id = f"{now.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:10]}"
        self.match_dir = Path(data_root) / self.match_id
        self.match_dir.mkdir(parents=True, exist_ok=False)

        self.manifest_path = self.match_dir / "manifest.json"
        self.store = EvidenceStore(self.match_dir, self.match_id)
        self.manifest = MatchManifest(
            match_id=self.match_id,
            started_at=now,
            client_resolution=(window.width, window.height),
            versions=PipelineVersions(capture=__version__),
            notes=f"window={window.title!r}; process={window.process_name!r}",
        )
        self._write_manifest(self.manifest)

    def _write_manifest(self, manifest: MatchManifest) -> None:
        tmp = self.manifest_path.with_suffix(".json.tmp")
        tmp.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(self.manifest_path)

    def _make_backend(self, name: str):
        return create_capture_backend(
            name,
            target_fps=self.settings.target_fps,
            first_frame_timeout_seconds=self.settings.first_frame_timeout_seconds,
            cursor_capture=self.settings.cursor_capture,
            draw_border=self.settings.draw_border,
        )

    def _start_backend(self):
        primary_name = self.settings.backend
        backend = self._make_backend(primary_name)

        try:
            backend.start(self.window)
            return backend
        except Exception as primary_exc:
            try:
                backend.close()
            except Exception:
                pass

            fallback_name = self.settings.fallback_backend
            if not fallback_name or fallback_name.lower() == primary_name.lower():
                raise

            print(f"[WARN] Capture backend {primary_name!r} failed: {primary_exc}")
            print(f"[WARN] Falling back to {fallback_name!r}.")
            fallback = self._make_backend(fallback_name)
            fallback.start(self.window)
            return fallback

    def run(self) -> None:
        locator = WindowsWindowLocator()

        # The WGC backend may receive and cache its first frame while start()
        # is still waiting to return. Therefore the session clock must start
        # before the backend is started, otherwise that first frame can have
        # a negative elapsed timestamp.
        session_start = time.monotonic()
        backend = self._start_backend()

        frame_period = 1.0 / max(self.settings.target_fps, 0.1)
        next_poll_at = time.monotonic()
        last_backend_sequence = -1
        last_new_frame_at = session_start
        last_saved_at = float("-inf")
        last_keyframe_at = float("-inf")
        gap_open = False

        self.store.append_status(
            elapsed_s=0.0,
            status="capture_started",
            details={"backend": backend.name},
        )

        self.manifest = self.manifest.model_copy(
            update={
                "notes": (
                    f"window={self.window.title!r}; "
                    f"process={self.window.process_name!r}; "
                    f"capture_backend={backend.name!r}"
                )
            }
        )
        self._write_manifest(self.manifest)

        try:
            while True:
                now = time.monotonic()
                if now < next_poll_at:
                    time.sleep(min(next_poll_at - now, 0.05))
                    continue
                next_poll_at = now + frame_period

                current_window = locator.get_by_handle(self.window.handle)
                if current_window is None:
                    print("\n[INFO] Target window disappeared; closing session.")
                    self.store.append_status(
                        elapsed_s=now - session_start,
                        status="window_closed",
                    )
                    break

                if backend.is_closed():
                    err = backend.error()
                    if err is not None:
                        raise RuntimeError(
                            f"Capture backend {backend.name!r} stopped: {err}"
                        ) from err
                    print("\n[INFO] Capture backend reported closed target.")
                    self.store.append_status(
                        elapsed_s=now - session_start,
                        status="capture_closed",
                        details={"backend": backend.name},
                    )
                    break

                packet = backend.latest_frame()
                if packet is None or packet.sequence == last_backend_sequence:
                    no_frame_for = now - last_new_frame_at
                    if (
                        not gap_open
                        and no_frame_for >= self.settings.capture_gap_after_seconds
                    ):
                        gap_open = True
                        reason = (
                            "window_minimized"
                            if current_window.is_minimized
                            else "no_new_frames"
                        )
                        self.store.append_status(
                            elapsed_s=now - session_start,
                            status="capture_gap_start",
                            details={"reason": reason, "backend": backend.name},
                        )
                        print(
                            f"\n[WARN] Capture gap started: {reason} "
                            f"({no_frame_for:.1f}s without a new frame)"
                        )
                    continue

                last_backend_sequence = packet.sequence
                last_new_frame_at = now

                if gap_open:
                    gap_open = False
                    self.store.append_status(
                        elapsed_s=now - session_start,
                        status="capture_gap_end",
                        details={"backend": backend.name},
                    )
                    print("\n[INFO] Capture resumed.")

                frame = packet.frame
                # Both timestamps use time.monotonic(). The max() is only a
                # defensive guard against sub-resolution/platform anomalies.
                elapsed = elapsed_seconds(frame.timestamp_s, session_start)
                changed, score = self.scene_detector.changed(frame.png_bytes)

                reason: str | None = None
                if self.store.count == 0:
                    reason = "session_start"
                elif (
                    self.settings.save_periodic_keyframes
                    and elapsed - last_keyframe_at >= self.settings.keyframe_interval_seconds
                ):
                    reason = "periodic_keyframe"
                elif (
                    self.settings.save_on_scene_change
                    and changed
                    and elapsed - last_saved_at >= self.settings.min_scene_save_interval_seconds
                ):
                    reason = "scene_change"

                if reason is not None:
                    stored = self.store.append_frame(
                        frame,
                        elapsed_s=elapsed,
                        reason=reason,
                        scene_change_score=score,
                    )
                    last_saved_at = elapsed
                    if reason in {"session_start", "periodic_keyframe"}:
                        last_keyframe_at = elapsed

                    print(
                        f"\rbackend={backend.name:<4} "
                        f"frames={stored.sequence + 1:<6} "
                        f"elapsed={elapsed:8.1f}s "
                        f"change={score:0.4f} "
                        f"reason={reason:<17}",
                        end="",
                        flush=True,
                    )

        except KeyboardInterrupt:
            print("\n[INFO] Recorder stopped by user.")
            self.store.append_status(
                elapsed_s=time.monotonic() - session_start,
                status="stopped_by_user",
            )
        finally:
            backend.close()
            self.store.append_status(
                elapsed_s=time.monotonic() - session_start,
                status="capture_stopped",
                details={"backend": backend.name},
            )
            self.manifest = self.manifest.model_copy(
                update={"ended_at": datetime.now(timezone.utc)}
            )
            self._write_manifest(self.manifest)
