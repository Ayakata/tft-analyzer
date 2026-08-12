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
from tft_analyzer.tracking.hud import (
    HUDTrackerSettings,
    track_match_hud,
)
from tft_analyzer.tracking.hud.timeline import format_hud_timeline
from tft_analyzer.events.hud import (
    HUDEventDetectorSettings,
    detect_match_hud_events,
)
from tft_analyzer.events.hud.timeline import format_hud_event_timeline
from tft_analyzer.perception.layout import ROIRegistry, build_roi_debug
from tft_analyzer.perception.ocr import RapidOCREngine
from tft_analyzer.perception.hud.debug import build_hud_debug
from tft_analyzer.perception.hud.pipeline import process_match_hud
from tft_analyzer.perception.hud.recognizer import HUDRecognizer
from tft_analyzer.perception.hud.presence import HUDPresenceGate
from tft_analyzer.perception.hud.stage_localizer import StageLocalizer

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


def _build_hud_recognizer(args, cfg):
    perception_cfg = cfg.get("perception", {})
    hud_cfg = perception_cfg.get("hud", {})

    profile_path = Path(
        getattr(args, "profile", None)
        or "configs/layouts/tft_16_9_default.yaml"
    )
    registry = ROIRegistry.from_yaml(profile_path)

    engine_name = str(hud_cfg.get("engine", "rapidocr")).lower()
    if engine_name != "rapidocr":
        raise ValueError(
            f"Unsupported HUD OCR engine {engine_name!r}. "
            "Stage 2.1 currently supports: rapidocr."
        )

    presence_cfg = hud_cfg.get("presence", {})
    localizer_cfg = hud_cfg.get("stage_localizer", {})

    presence_gate = None
    if bool(presence_cfg.get("enabled", True)):
        presence_gate = HUDPresenceGate(
            min_dark_fraction=float(
                presence_cfg.get("min_dark_fraction", 0.20)
            ),
            min_edge_density=float(
                presence_cfg.get("min_edge_density", 0.015)
            ),
            min_bright_fraction=float(
                presence_cfg.get("min_bright_fraction", 0.002)
            ),
            stage_min_edge_density=float(
                presence_cfg.get("stage_min_edge_density", 0.010)
            ),
        )

    stage_localizer = StageLocalizer(
        candidate_width_px_at_1920=int(
            localizer_cfg.get("candidate_width_px_at_1920", 56)
        ),
        candidate_height_px_at_1080=int(
            localizer_cfg.get("candidate_height_px_at_1080", 28)
        ),
        x_offsets_px_at_1920=tuple(
            int(x) for x in localizer_cfg.get(
                "x_offsets_px_at_1920",
                [-20, -10, 0, 10, 20, 30],
            )
        ),
        y_offset_px_at_1080=int(
            localizer_cfg.get("y_offset_px_at_1080", 0)
        ),
    )

    return HUDRecognizer(
        registry=registry,
        ocr_engine=RapidOCREngine(),
        producer_version=str(
            hud_cfg.get("producer_version", "hud-rapidocr-0.4.3")
        ),
        min_observation_confidence=float(
            hud_cfg.get("min_observation_confidence", 0.45)
        ),
        primary_upscale=int(hud_cfg.get("primary_upscale", 4)),
        fallback_upscale=int(hud_cfg.get("fallback_upscale", 5)),
        horizontal_padding_ratio=float(
            hud_cfg.get("horizontal_padding_ratio", 0.16)
        ),
        binary_threshold=int(
            hud_cfg.get("binary_threshold", 150)
        ),
        presence_gate=presence_gate,
        stage_localizer=stage_localizer,
    )


def cmd_hud_debug(args):
    cfg = load_yaml(Path(args.config))
    recognizer = _build_hud_recognizer(args, cfg)

    image_path = Path(args.image)
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    if args.output:
        output_dir = Path(args.output)
    else:
        output_dir = Path("data/hud_debug") / (
            f"{image_path.stem}_{recognizer.registry.profile.profile_id}"
        )

    debug = build_hud_debug(
        image_path,
        output_dir,
        recognizer,
    )
    result = debug["result"]

    print(f"[INFO] Image:   {image_path}")
    print(f"[INFO] Profile: {recognizer.registry.profile.profile_id}")
    print(f"[INFO] Engine:  {recognizer.ocr_engine.name}")

    for field in ("stage", "gold", "level", "xp"):
        best = result.best_attempt(field)
        if best is None:
            print(f"{field:>7}: no attempt")
            continue

        parsed = (
            best.parsed.normalized_text
            if best.parsed is not None
            else "INVALID"
        )
        status = (
            "ACCEPT"
            if best.parsed is not None
            and best.confidence >= recognizer.min_observation_confidence
            else ("LOW" if best.parsed is not None else "INVALID")
        )
        candidate = (
            f" candidate={best.candidate_name}"
            if best.candidate_name
            else ""
        )
        presence_label = (
            "PRESENT" if best.presence_passed else "ABSENT"
        )
        print(
            f"{field:>7}: [{status:<7}] "
            f"raw={best.raw_text!r:<14} "
            f"parsed={parsed:<8} "
            f"ocr={best.ocr_score:.3f} "
            f"conf={best.confidence:.3f} "
            f"presence={presence_label}({best.presence_score:.3f}) "
            f"variant={best.variant}"
            f"{candidate}"
        )

    print(f"[OK] Result:       {debug['result_path']}")
    print(f"[OK] Crops:        {debug['crops_dir']}")
    print(f"[OK] Preprocessed: {debug['preprocessed_dir']}")
    return 0


def cmd_perceive_hud(args):
    cfg = load_yaml(Path(args.config))
    recognizer = _build_hud_recognizer(args, cfg)

    match_dir = Path(args.match_dir)
    if not match_dir.exists():
        raise FileNotFoundError(f"Match directory not found: {match_dir}")

    summary = process_match_hud(
        match_dir,
        recognizer,
        stride=args.stride,
        limit=args.limit,
    )

    print(f"[INFO] Match:     {match_dir}")
    print(f"[INFO] Producer:  {summary['producer_version']}")
    print(f"[OK] Frames:     {summary['processed_frames']}")
    print(f"[OK] Observations:{summary['observation_count']}")

    for field, metrics in summary["fields"].items():
        present = metrics["present"]
        print(
            f"  {field:<6} "
            f"present={present}/{metrics['frames']}  "
            f"parsed={metrics['parse_valid']}/{present} "
            f"({metrics['parse_rate_when_present'] * 100:5.1f}%)  "
            f"accepted={metrics['accepted']}/{present} "
            f"({metrics['accepted_rate_when_present'] * 100:5.1f}%)  "
            f"mean_acc_conf={metrics['mean_accepted_confidence']:.3f}"
        )

    print(f"[OK] JSONL:      {summary['observations_path']}")
    print(f"[OK] Attempts:   {summary['attempts_path']}")
    print(f"[OK] Summary:    {summary['summary_path']}")
    return 0



def _build_hud_tracker_settings(cfg):
    tracking_cfg = cfg.get("tracking", {})
    hud_cfg = tracking_cfg.get("hud", {})
    constraints_cfg = hud_cfg.get("constraints", {})

    max_age = hud_cfg.get("max_age_seconds", {})

    return HUDTrackerSettings(
        producer_version=str(
            hud_cfg.get(
                "producer_version",
                "hud-state-tracker-0.5.1",
            )
        ),
        max_age_seconds={
            "stage": float(max_age.get("stage", 45.0)),
            "gold": float(max_age.get("gold", 15.0)),
            "level": float(max_age.get("level", 45.0)),
            "xp": float(max_age.get("xp", 15.0)),
        },
        reject_stage_regression=bool(
            constraints_cfg.get(
                "reject_stage_regression",
                True,
            )
        ),
        max_stage_code_jump_without_confirmation=int(
            constraints_cfg.get(
                "max_stage_code_jump_without_confirmation",
                12,
            )
        ),
        reject_level_regression=bool(
            constraints_cfg.get(
                "reject_level_regression",
                True,
            )
        ),
        max_level_jump_without_confirmation=int(
            constraints_cfg.get(
                "max_level_jump_without_confirmation",
                2,
            )
        ),
        reject_xp_regression_same_requirement=bool(
            constraints_cfg.get(
                "reject_xp_regression_same_requirement",
                True,
            )
        ),
        suspicious_confirmation_count=int(
            hud_cfg.get(
                "suspicious_confirmation_count",
                2,
            )
        ),
    )


def cmd_track_hud(args):
    cfg = load_yaml(Path(args.config))
    settings = _build_hud_tracker_settings(cfg)

    match_dir = Path(args.match_dir)
    tracking_cfg = cfg.get("tracking", {}).get("hud", {})
    pattern = str(
        tracking_cfg.get(
            "input_observation_glob",
            "hud-rapidocr-*.jsonl",
        )
    )

    summary = track_match_hud(
        match_dir,
        settings,
        observations_path=(
            Path(args.observations)
            if args.observations
            else None
        ),
        observation_glob=pattern,
    )

    print(f"[INFO] Match:        {match_dir}")
    print(f"[INFO] Tracker:      {summary['tracker_version']}")
    print(f"[INFO] Observations: {summary['input_observations_path']}")
    print(f"[OK] States:         {summary['state_count']}")
    print(f"[OK] Decisions:      {summary['decision_count']}")

    print("[INFO] Decision actions:")
    for action, count in sorted(summary["decision_actions"].items()):
        print(f"  {action:<10} {count}")

    print("[INFO] Field changes/statuses:")
    for field in ("stage", "gold", "level", "xp"):
        statuses = summary["field_status_counts"].get(field, {})
        print(
            f"  {field:<6} changes={summary['field_value_changes'].get(field, 0):<4} "
            f"observed={statuses.get('observed', 0):<4} "
            f"carried={statuses.get('carried', 0):<4} "
            f"stale={statuses.get('stale', 0):<4} "
            f"unknown={statuses.get('unknown', 0):<4}"
        )

    print(f"[OK] States JSONL:   {summary['states_path']}")
    print(f"[OK] Decisions:      {summary['decisions_path']}")
    print(f"[OK] Summary:        {summary['summary_path']}")

    if args.timeline:
        print()
        print(
            format_hud_timeline(
                summary["states_path"],
                limit=args.timeline_limit,
            )
        )

    return 0


def cmd_hud_timeline(args):
    print(
        format_hud_timeline(
            Path(args.states),
            limit=args.limit,
        )
    )
    return 0



def _build_hud_event_settings(cfg):
    event_cfg = cfg.get("events", {}).get("hud", {})

    return HUDEventDetectorSettings(
        producer_version=str(
            event_cfg.get(
                "producer_version",
                "hud-event-detector-0.6.0",
            )
        ),
        warn_transition_window_seconds=float(
            event_cfg.get(
                "warn_transition_window_seconds",
                20.0,
            )
        ),
        emit_initial_values=bool(
            event_cfg.get(
                "emit_initial_values",
                False,
            )
        ),
    )


def cmd_detect_hud_events(args):
    cfg = load_yaml(Path(args.config))
    settings = _build_hud_event_settings(cfg)

    match_dir = Path(args.match_dir)
    event_cfg = cfg.get("events", {}).get("hud", {})
    pattern = str(
        event_cfg.get(
            "input_states_glob",
            "hud-state-tracker-*.jsonl",
        )
    )

    summary = detect_match_hud_events(
        match_dir,
        settings,
        states_path=(
            Path(args.states)
            if args.states
            else None
        ),
        states_glob=pattern,
    )

    print(f"[INFO] Match:      {match_dir}")
    print(f"[INFO] Detector:   {summary['producer_version']}")
    print(f"[INFO] States:     {summary['input_states_path']}")
    print(f"[OK] State count: {summary['input_state_count']}")
    print(f"[OK] Events:      {summary['event_count']}")

    print("[INFO] Event counts:")
    for event_type, count in sorted(
        summary["event_type_counts"].items()
    ):
        print(f"  {event_type:<16} {count}")

    print("[INFO] Field timing:")
    for field in ("stage", "level", "xp", "gold"):
        stats = summary["field_stats"][field]
        print(
            f"  {field:<6} "
            f"events={stats['event_count']:<4} "
            f"mean_conf={stats['mean_confidence']:.3f} "
            f"mean_window={stats['mean_transition_window_s']:.1f}s "
            f"max_window={stats['max_transition_window_s']:.1f}s "
            f"warnings={stats['timing_warning_count']}"
        )

    print(f"[OK] Events JSONL: {summary['events_path']}")
    print(f"[OK] Summary:      {summary['summary_path']}")

    if args.timeline:
        print()
        print(
            format_hud_event_timeline(
                summary["events_path"],
                limit=args.timeline_limit,
            )
        )

    return 0


def cmd_hud_events(args):
    print(
        format_hud_event_timeline(
            Path(args.events),
            limit=args.limit,
        )
    )
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


    p = sub.add_parser(
        "hud-debug",
        help="Run Stage 2.1 HUD OCR on one captured frame.",
    )
    p.add_argument("image", help="Captured TFT frame PNG/JPEG.")
    p.add_argument("--config", default="configs/default.yaml")
    p.add_argument(
        "--profile",
        default="configs/layouts/tft_16_9_default.yaml",
    )
    p.add_argument("--output")
    p.set_defaults(func=cmd_hud_debug)

    p = sub.add_parser(
        "perceive-hud",
        help="Run HUD perception over saved match evidence.",
    )
    p.add_argument("match_dir")
    p.add_argument("--config", default="configs/default.yaml")
    p.add_argument(
        "--profile",
        default="configs/layouts/tft_16_9_default.yaml",
    )
    p.add_argument(
        "--stride",
        type=int,
        default=1,
        help="Process every Nth saved evidence frame.",
    )
    p.add_argument(
        "--limit",
        type=int,
        help="Stop after this many processed evidence frames.",
    )
    p.set_defaults(func=cmd_perceive_hud)


    p = sub.add_parser(
        "track-hud",
        help="Fuse HUD observations into a stable temporal state timeline.",
    )
    p.add_argument("match_dir")
    p.add_argument("--config", default="configs/default.yaml")
    p.add_argument(
        "--observations",
        help="Explicit observation JSONL. Default: latest hud-rapidocr file.",
    )
    p.add_argument(
        "--timeline",
        action="store_true",
        help="Print compact tracked HUD timeline after processing.",
    )
    p.add_argument(
        "--timeline-limit",
        type=int,
        default=40,
    )
    p.set_defaults(func=cmd_track_hud)

    p = sub.add_parser(
        "hud-timeline",
        help="Print a compact timeline from tracked HUD state JSONL.",
    )
    p.add_argument("states")
    p.add_argument("--limit", type=int)
    p.set_defaults(func=cmd_hud_timeline)


    p = sub.add_parser(
        "detect-hud-events",
        help="Detect primitive semantic HUD events from tracked HUD states.",
    )
    p.add_argument("match_dir")
    p.add_argument("--config", default="configs/default.yaml")
    p.add_argument(
        "--states",
        help="Explicit tracked HUD JSONL. Default: latest tracker version.",
    )
    p.add_argument(
        "--timeline",
        action="store_true",
        help="Print compact primitive event timeline.",
    )
    p.add_argument(
        "--timeline-limit",
        type=int,
        default=80,
    )
    p.set_defaults(func=cmd_detect_hud_events)

    p = sub.add_parser(
        "hud-events",
        help="Print an existing primitive HUD event JSONL as a timeline.",
    )
    p.add_argument("events")
    p.add_argument("--limit", type=int)
    p.set_defaults(func=cmd_hud_events)

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
