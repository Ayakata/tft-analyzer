from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

from tft_analyzer import __version__
from tft_analyzer.capture.scene_change import SceneChangeDetector
from tft_analyzer.capture.session import MatchSession, RecorderSettings
from tft_analyzer.capture.window_locator import WindowsWindowLocator
from tft_analyzer.replay import build_replay_html
from tft_analyzer.perception.layout import ROIRegistry, build_roi_debug

from .config import load_yaml


def _optional_bool(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1", "on"}:
            return True
        if normalized in {"false", "no", "0", "off"}:
            return False
    raise ValueError(f"Expected boolean or null, got {value!r}")


def cmd_windows(args):
    locator = WindowsWindowLocator()
    windows = locator.find(
        title_regex=args.title_regex,
        process_regex=args.process_regex,
    )

    if not windows:
        print("No matching visible windows found.")
        return 1

    print(
        f"{'HWND':>10}  {'PID':>7}  {'SIZE':>12}  {'MIN':>3}  "
        f"{'PROCESS':<28} TITLE"
    )
    for w in windows:
        print(
            f"{w.handle:>10}  {(w.process_id or 0):>7}  "
            f"{w.width}x{w.height:<6}  "
            f"{('Y' if w.is_minimized else 'N'):>3}  "
            f"{(w.process_name or '-'):28.28} {w.title}"
        )
    return 0


def select_window(locator, handle, title_regex, process_regex):
    if handle is not None:
        window = locator.get_by_handle(handle)
        if window is None:
            raise RuntimeError(f"Window with HWND={handle} not found.")
        return window

    matches = locator.find(
        title_regex=title_regex,
        process_regex=process_regex,
    )
    if not matches:
        raise RuntimeError(
            "No matching window found. Run `tft-analyzer windows` first."
        )
    if len(matches) > 1:
        lines = [
            f"HWND={w.handle} PID={w.process_id} {w.width}x{w.height} "
            f"{w.process_name!r} {w.title!r}"
            for w in matches[:10]
        ]
        raise RuntimeError(
            "More than one window matched. Pass --handle explicitly:\n  "
            + "\n  ".join(lines)
        )
    return matches[0]


def cmd_record(args):
    cfg = load_yaml(Path(args.config))
    window_cfg = cfg.get("window", {})
    cap_cfg = cfg.get("capture", {})

    locator = WindowsWindowLocator()
    window = select_window(
        locator,
        args.handle,
        args.title_regex or window_cfg.get("title_regex"),
        args.process_regex or window_cfg.get("process_regex"),
    )

    print(
        f"[INFO] Window: HWND={window.handle} {window.width}x{window.height} "
        f"{window.process_name!r} {window.title!r}"
    )

    detector = SceneChangeDetector(
        width=int(cap_cfg.get("scene_signature_width", 160)),
        height=int(cap_cfg.get("scene_signature_height", 90)),
        threshold=float(cap_cfg.get("scene_change_threshold", 0.045)),
    )

    backend = args.backend or str(cap_cfg.get("backend", "wgc"))
    fallback = cap_cfg.get("fallback_backend", "mss")
    if args.no_fallback:
        fallback = None

    settings = RecorderSettings(
        backend=backend,
        fallback_backend=fallback,
        target_fps=float(args.fps or cap_cfg.get("target_fps", 4)),
        first_frame_timeout_seconds=float(
            cap_cfg.get("first_frame_timeout_seconds", 4.0)
        ),
        capture_gap_after_seconds=float(
            cap_cfg.get("capture_gap_after_seconds", 2.0)
        ),
        cursor_capture=_optional_bool(cap_cfg.get("cursor_capture")),
        draw_border=_optional_bool(cap_cfg.get("draw_border")),
        keyframe_interval_seconds=float(
            cap_cfg.get("keyframe_interval_seconds", 10)
        ),
        min_scene_save_interval_seconds=float(
            cap_cfg.get("min_scene_save_interval_seconds", 0.75)
        ),
        save_periodic_keyframes=bool(
            cap_cfg.get("save_periodic_keyframes", True)
        ),
        save_on_scene_change=bool(
            cap_cfg.get("save_on_scene_change", True)
        ),
    )

    session = MatchSession(
        data_root=Path(args.output),
        window=window,
        scene_detector=detector,
        settings=settings,
    )

    print(f"[INFO] Requested backend: {settings.backend}")
    print(f"[INFO] Match ID: {session.match_id}")
    print(f"[INFO] Output:   {session.match_dir}")
    print("[INFO] Press Ctrl+C to stop.")

    session.run()
    replay = build_replay_html(session.match_dir)
    print(f"[OK] Replay: {replay}")
    return 0


def cmd_replay(args):
    replay = build_replay_html(Path(args.match_dir))
    print(replay)
    if args.open:
        webbrowser.open(replay.resolve().as_uri())
    return 0



def cmd_roi_debug(args):
    image_path = Path(args.image)
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    profile_path = Path(args.profile)
    registry = ROIRegistry.from_yaml(profile_path)

    if args.output:
        output_dir = Path(args.output)
    else:
        output_dir = Path("data/roi_debug") / (
            f"{image_path.stem}_{registry.profile.profile_id}"
        )

    result = build_roi_debug(
        image_path,
        registry,
        output_dir,
        selected_names=args.roi or None,
    )

    print(f"[INFO] Image:   {image_path}")
    print(f"[INFO] Profile: {registry.profile.profile_id}")
    print(f"[OK] ROIs:     {result['roi_count']}")
    print(f"[OK] Overlay:  {result['overlay']}")
    print(f"[OK] Crops:    {result['crops_dir']}")
    print(f"[OK] Manifest: {result['manifest']}")

    if args.open:
        webbrowser.open(Path(result["overlay"]).resolve().as_uri())

    return 0

def build_parser():
    parser = argparse.ArgumentParser(prog="tft-analyzer")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("windows", help="List visible Windows windows.")
    p.add_argument("--title-regex")
    p.add_argument("--process-regex")
    p.set_defaults(func=cmd_windows)

    p = sub.add_parser("record", help="Record immutable game evidence.")
    p.add_argument("--config", default="configs/default.yaml")
    p.add_argument("--output", default="data/matches")
    p.add_argument("--handle", type=int)
    p.add_argument("--title-regex")
    p.add_argument("--process-regex")
    p.add_argument("--fps", type=float)
    p.add_argument(
        "--backend",
        choices=("wgc", "mss"),
        help="Override configured capture backend.",
    )
    p.add_argument(
        "--no-fallback",
        action="store_true",
        help="Do not fall back to MSS if the primary backend cannot start.",
    )
    p.set_defaults(func=cmd_record)

    p = sub.add_parser("replay", help="Build HTML replay for a match.")
    p.add_argument("match_dir")
    p.add_argument("--open", action="store_true")
    p.set_defaults(func=cmd_replay)

    p = sub.add_parser(
        "roi-debug",
        help="Resolve a layout profile, save ROI crops and draw an overlay.",
    )
    p.add_argument("image", help="Captured TFT frame PNG/JPEG.")
    p.add_argument(
        "--profile",
        default="configs/layouts/tft_16_9_default.yaml",
        help="Layout YAML profile.",
    )
    p.add_argument("--output", help="Output directory.")
    p.add_argument(
        "--roi",
        action="append",
        help="Only render/crop this ROI. May be repeated.",
    )
    p.add_argument("--open", action="store_true", help="Open overlay after creation.")
    p.set_defaults(func=cmd_roi_debug)

    return parser


def main():
    args = build_parser().parse_args()
    try:
        code = int(args.func(args))
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        code = 2
    raise SystemExit(code)


if __name__ == "__main__":
    main()
