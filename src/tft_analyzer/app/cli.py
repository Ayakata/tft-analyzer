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
from tft_analyzer.validation.hud import (
    HUDEventValidatorSettings,
    validate_match_hud_events,
)
from tft_analyzer.validation.hud.timeline import format_validation_timeline
from tft_analyzer.reducers.hud import (
    HUDGameStateReducerSettings,
    reduce_match_game_state,
)
from tft_analyzer.reducers.hud.timeline import format_game_state_timeline
from tft_analyzer.perception.layout import ROIRegistry, build_roi_debug
from tft_analyzer.perception.ocr import RapidOCREngine
from tft_analyzer.perception.hud.debug import build_hud_debug
from tft_analyzer.perception.hud.pipeline import process_match_hud
from tft_analyzer.perception.hud.recognizer import HUDRecognizer
from tft_analyzer.perception.hud.presence import HUDPresenceGate
from tft_analyzer.perception.hud.stage_localizer import StageLocalizer
from tft_analyzer.perception.players import (
    PlayerListRecognizer,
    PlayerListRecognizerSettings,
    build_players_debug,
    process_match_players,
)
from tft_analyzer.perception.board import (
    BoardBenchRecognizer,
    BoardBenchRecognizerSettings,
    build_board_debug,
    process_match_board_bench,
)
from tft_analyzer.perception.shop import (
    ShopIdentityLexicon,
    ShopIdentityResolver,
    ShopIdentityResolverSettings,
    ShopRecognizer,
    ShopRecognizerSettings,
    build_shop_debug,
    process_match_shop,
)

from .config import load_yaml


from tft_analyzer.tracking.board import (
    BoardOccupancyTrackerSettings,
    format_board_occupancy_timeline,
    track_match_board_occupancy,
    export_board_formation_qa,
)
from tft_analyzer.actions import (
    ActionFusionSettings,
    format_action_timeline,
    infer_match_actions,
)
from tft_analyzer.decisions import (
    DecisionEpisodeSettings,
    build_match_decision_episodes,
    format_decision_episode_timeline,
)
from tft_analyzer.analyzers import (
    ContextReviewAnalyzerSettings,
    EconomyTempoAnalyzerSettings,
    analyze_match_context,
    analyze_match_episodes,
    format_context_review_timeline,
    format_economy_tempo_findings_timeline,
)
from tft_analyzer.game_data import (
    find_active_catalog_path,
    sync_riot_ddragon_catalog,
)
from tft_analyzer.features import (
    EpisodeContextSettings,
    RosterEvidenceSettings,
    SlotIdentityCurationSettings,
    SlotIdentityDatasetSettings,
    SlotIdentityLabelingSettings,
    IdentityLabelerSettings,
    SlotIdentityHumanAuditSettings,
    build_match_episode_context,
    build_match_roster_evidence,
    curate_slot_identity_dataset,
    export_slot_identity_dataset,
    format_episode_context_timeline,
    format_roster_evidence_timeline,
    format_slot_identity_curation_timeline,
    format_slot_identity_dataset_timeline,
    import_identity_labels,
    prepare_identity_label_package,
    run_identity_labeler,
    audit_identity_labels,
)
from tft_analyzer.reports import (
    MatchReviewReportSettings,
    build_match_review_report,
    format_review_cards_timeline,
)

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

    for field in ("stage", "gold", "level", "xp", "hp", "shop"):
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




def _build_player_recognizer(args, cfg):
    perception_cfg = cfg.get("perception", {})
    players_cfg = perception_cfg.get("players", {})

    profile_path = Path(
        getattr(args, "profile", None)
        or "configs/layouts/tft_16_9_default.yaml"
    )
    registry = ROIRegistry.from_yaml(profile_path)

    engine_name = str(players_cfg.get("engine", "rapidocr")).lower()
    if engine_name != "rapidocr":
        raise ValueError(
            f"Unsupported player OCR engine {engine_name!r}; "
            "currently supported: rapidocr."
        )

    x_starts = tuple(
        float(x)
        for x in players_cfg.get(
            "hp_candidate_x_starts",
            [0.48, 0.56, 0.64, 0.72, 0.80],
        )
    )

    settings = PlayerListRecognizerSettings(
        producer_version=str(
            players_cfg.get(
                "producer_version",
                "players-rapidocr-0.8.1",
            )
        ),
        min_observation_confidence=float(
            players_cfg.get("min_observation_confidence", 0.55)
        ),
        row_count=int(players_cfg.get("row_count", 8)),
        min_panel_score=float(
            players_cfg.get("min_panel_score", 0.22)
        ),
        player_name=(
            str(players_cfg["player_name"])
            if players_cfg.get("player_name")
            else None
        ),
        min_name_match_score=float(
            players_cfg.get("min_name_match_score", 0.60)
        ),
        min_highlight_score=float(
            players_cfg.get("min_highlight_score", 0.24)
        ),
        min_highlight_margin=float(
            players_cfg.get("min_highlight_margin", 0.035)
        ),
        min_combined_self_score=float(
            players_cfg.get("min_combined_self_score", 0.40)
        ),
        min_combined_self_margin=float(
            players_cfg.get("min_combined_self_margin", 0.025)
        ),
        hp_max_value=int(players_cfg.get("hp_max_value", 250)),
        hp_primary_upscale=int(
            players_cfg.get("hp_primary_upscale", 4)
        ),
        hp_fallback_upscale=int(
            players_cfg.get("hp_fallback_upscale", 6)
        ),
        hp_binary_threshold=int(
            players_cfg.get("hp_binary_threshold", 150)
        ),
        hp_primary_candidate_min_confidence=float(
            players_cfg.get(
                "hp_primary_candidate_min_confidence",
                0.60,
            )
        ),
        hp_fallback_min_confidence=float(
            players_cfg.get(
                "hp_fallback_min_confidence",
                0.72,
            )
        ),
        hp_candidate_priors=tuple(
            float(x)
            for x in players_cfg.get(
                "hp_candidate_priors",
                [1.00, 0.70, 0.45, 0.30, 0.20],
            )
        ),
        hp_candidate_x_starts=x_starts,
        hp_candidate_width_ratio=float(
            players_cfg.get("hp_candidate_width_ratio", 0.18)
        ),
        hp_y0=float(players_cfg.get("hp_y0", 0.14)),
        hp_y1=float(players_cfg.get("hp_y1", 0.86)),
    )

    return PlayerListRecognizer(
        registry=registry,
        ocr_engine=RapidOCREngine(),
        settings=settings,
    )


def cmd_players_debug(args):
    cfg = load_yaml(Path(args.config))
    recognizer = _build_player_recognizer(args, cfg)

    image_path = Path(args.image)
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    output_dir = (
        Path(args.output)
        if args.output
        else Path("data/players_debug")
        / f"{image_path.stem}_{recognizer.registry.profile.profile_id}"
    )

    debug = build_players_debug(
        image_path,
        output_dir,
        recognizer,
        manual_row_index=args.self_row,
        player_name=args.player_name,
    )
    result = debug["result"]

    print(f"[INFO] Image:       {image_path}")
    print(f"[INFO] Profile:     {recognizer.registry.profile.profile_id}")
    print(
        f"[INFO] Panel:       "
        f"{'PRESENT' if result.panel_present else 'ABSENT'} "
        f"score={result.panel_score:.3f}"
    )

    ordered = sorted(
        result.rows,
        key=lambda row: row.highlight_score,
        reverse=True,
    )
    print("[INFO] Row candidates:")
    for row in ordered:
        marker = "*" if row.row_index == result.selected_row_index else " "
        print(
            f" {marker} row={row.row_index} "
            f"highlight={row.highlight_score:.3f} "
            f"no_name={row.no_name_score:.3f} "
            f"combined={row.combined_self_score:.3f}"
        )

    if result.selected_row_index is None:
        print(
            "[WARN] Self row not selected. "
            "Use --self-row N to verify HP geometry or --player-name NAME "
            "to test name-assisted localization."
        )
    else:
        print(
            f"[INFO] Self row:    {result.selected_row_index} "
            f"method={result.self_method} "
            f"score={result.self_score:.3f} "
            f"margin={result.self_margin:.3f}"
        )

    best = result.best_hp_attempt
    if best is None:
        print("[WARN] HP:          no attempt")
    else:
        status = (
            "PARSED" if best.valid else "INVALID"
        )
        print(
            f"[INFO] HP:          [{status}] "
            f"value={best.hp} "
            f"raw={best.raw_text!r} "
            f"ocr={best.ocr_score:.3f} "
            f"conf={best.confidence:.3f} "
            f"candidate={best.candidate_name} "
            f"variant={best.variant}"
        )

    if result.observations:
        obs = result.observations[0]
        print(
            f"[OK] Observation:  hp={obs.value['hp']} "
            f"confidence={obs.confidence:.3f}"
        )
    else:
        print("[WARN] Observation: not emitted")

    print(f"[OK] Overlay:      {debug['overlay']}")
    print(f"[OK] Result:       {debug['result_path']}")
    print(f"[OK] Rows:         {debug['rows_dir']}")
    print(f"[OK] HP crops:     {debug['hp_candidates_dir']}")
    return 0


def cmd_perceive_players(args):
    cfg = load_yaml(Path(args.config))
    recognizer = _build_player_recognizer(args, cfg)

    match_dir = Path(args.match_dir)
    if not match_dir.exists():
        raise FileNotFoundError(f"Match directory not found: {match_dir}")

    summary = process_match_players(
        match_dir,
        recognizer,
        stride=args.stride,
        limit=args.limit,
        player_name=args.player_name,
    )

    print(f"[INFO] Match:       {match_dir}")
    print(f"[INFO] Producer:    {summary['producer_version']}")
    print(f"[OK] Frames:       {summary['processed_frames']}")
    print(
        f"[INFO] Panel:       {summary['panel_present']}/"
        f"{summary['processed_frames']} "
        f"({summary['panel_presence_rate'] * 100:.1f}%)"
    )
    print(
        f"[INFO] Self row:    {summary['self_row_selected']}/"
        f"{summary['panel_present']} "
        f"({summary['self_row_selection_rate_when_panel_present'] * 100:.1f}%)"
    )
    print(
        f"[INFO] HP parsed:   {summary['hp_parsed']}/"
        f"{summary['self_row_selected']} "
        f"({summary['hp_parse_rate_when_self_selected'] * 100:.1f}%)"
    )
    print(
        f"[OK] HP accepted:  {summary['hp_accepted']}/"
        f"{summary['self_row_selected']} "
        f"({summary['hp_accept_rate_when_self_selected'] * 100:.1f}%)"
    )
    print(
        f"[INFO] Methods:     {summary['selection_method_counts']}"
    )
    print(
        f"[INFO] Rows:        {summary['selected_row_counts']}"
    )
    print(
        f"[INFO] HP source:   primary={summary['primary_candidate_used']} "
        f"fallback={summary['fallback_candidate_used']} "
        f"primary_rate={summary['primary_candidate_rate'] * 100:.1f}%"
    )
    print(
        f"[INFO] Ambiguous:   {summary['ambiguous_self_rows']} "
        f"no_name_selected={summary['no_name_fallback_selected']}"
    )
    print(
        f"[INFO] Max HP gap:  {summary['max_hp_observation_gap_s']:.1f}s"
    )
    print(f"[OK] JSONL:        {summary['observations_path']}")
    print(f"[OK] Attempts:     {summary['attempts_path']}")
    print(f"[OK] Identity:     {summary['identity_path']}")
    print(f"[OK] Summary:      {summary['summary_path']}")
    return 0




def _build_board_bench_recognizer(args, cfg):
    perception_cfg = cfg.get("perception", {})
    bb_cfg = perception_cfg.get("board_bench", {})
    profile_path = Path(
        getattr(args, "profile", None)
        or "configs/layouts/tft_16_9_default.yaml"
    )
    registry = ROIRegistry.from_yaml(profile_path)

    def points(name, default):
        raw = bb_cfg.get(name, default)
        return tuple((float(x), float(y)) for x, y in raw)

    settings = BoardBenchRecognizerSettings(
        board_producer_version=str(bb_cfg.get("board_producer_version", "board-occupancy-0.12.0")),
        bench_producer_version=str(bb_cfg.get("bench_producer_version", "bench-occupancy-0.12.0")),
        board_rows=int(bb_cfg.get("board_rows", 4)),
        board_cols=int(bb_cfg.get("board_cols", 7)),
        bench_slots=int(bb_cfg.get("bench_slots", 9)),
        min_board_presence_score=float(bb_cfg.get("min_board_presence_score", 0.20)),
        min_bench_presence_score=float(bb_cfg.get("min_bench_presence_score", 0.16)),
        board_empty_below=float(bb_cfg.get("board_empty_below", 0.38)),
        board_occupied_above=float(bb_cfg.get("board_occupied_above", 0.58)),
        bench_empty_below=float(bb_cfg.get("bench_empty_below", 0.34)),
        bench_occupied_above=float(bb_cfg.get("bench_occupied_above", 0.54)),
        board_row_left=points("board_row_left", [[.293,.414],[.319,.478],[.278,.549],[.304,.625]]),
        board_row_right=points("board_row_right", [[.651,.414],[.688,.478],[.663,.549],[.701,.625]]),
        bench_left=tuple(float(x) for x in bb_cfg.get("bench_left", [.230,.745])),
        bench_right=tuple(float(x) for x in bb_cfg.get("bench_right", [.715,.745])),
        board_half_width_px_at_1920=int(
            bb_cfg.get("board_half_width_px_at_1920", 58)
        ),
        board_up_px_at_1080=int(
            bb_cfg.get("board_up_px_at_1080", 72)
        ),
        board_down_px_at_1080=int(
            bb_cfg.get("board_down_px_at_1080", 30)
        ),
        board_half_width_px_at_1920_by_row=tuple(
            int(v)
            for v in bb_cfg.get(
                "board_half_width_px_at_1920_by_row",
                [50, 56, 62, 68],
            )
        ),
        board_up_px_at_1080_by_row=tuple(
            int(v)
            for v in bb_cfg.get(
                "board_up_px_at_1080_by_row",
                [68, 72, 78, 84],
            )
        ),
        board_down_px_at_1080_by_row=tuple(
            int(v)
            for v in bb_cfg.get(
                "board_down_px_at_1080_by_row",
                [26, 28, 30, 32],
            )
        ),
        board_hex_half_width_px_at_1920_by_row=tuple(
            int(v)
            for v in bb_cfg.get(
                "board_hex_half_width_px_at_1920_by_row",
                [52, 55, 58, 61],
            )
        ),
        board_hex_half_height_px_at_1080_by_row=tuple(
            int(v)
            for v in bb_cfg.get(
                "board_hex_half_height_px_at_1080_by_row",
                [38, 41, 45, 48],
            )
        ),
        bench_half_width_px_at_1920=int(
            bb_cfg.get("bench_half_width_px_at_1920", 60)
        ),
        bench_up_px_at_1080=int(
            bb_cfg.get("bench_up_px_at_1080", 142)
        ),
        bench_down_px_at_1080=int(
            bb_cfg.get("bench_down_px_at_1080", 12)
        ),
        bench_footprint_half_width_px_at_1920=int(
            bb_cfg.get("bench_footprint_half_width_px_at_1920", 36)
        ),
        bench_footprint_up_px_at_1080=int(
            bb_cfg.get("bench_footprint_up_px_at_1080", 64)
        ),
        bench_footprint_down_px_at_1080=int(
            bb_cfg.get("bench_footprint_down_px_at_1080", 16)
        ),
    )
    if len(settings.board_row_left) != settings.board_rows or len(settings.board_row_right) != settings.board_rows:
        raise ValueError("board_row_left/right must contain one point per board row")
    return BoardBenchRecognizer(registry=registry, settings=settings)


def cmd_board_debug(args):
    cfg = load_yaml(Path(args.config))
    recognizer = _build_board_bench_recognizer(args, cfg)
    image_path = Path(args.image)
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")
    output_dir = Path(args.output) if args.output else Path("data/board_debug") / f"{image_path.stem}_{recognizer.registry.profile.profile_id}"
    debug = build_board_debug(image_path, output_dir, recognizer)
    result = debug["result"]
    print(f"[INFO] Image:       {image_path}")
    print(f"[INFO] Profile:     {recognizer.registry.profile.profile_id}")
    board_geometry = [
        recognizer.board_box_geometry_at_reference(row)
        for row in range(recognizer.settings.board_rows)
    ]
    print(
        "[INFO] Geometry:    "
        + " ".join(
            f"r{row}=w{half_width * 2}/up{up}/down{down}"
            for row, (half_width, up, down) in enumerate(board_geometry)
        )
    )
    board_hex = [
        recognizer.board_hex_geometry_at_reference(row)
        for row in range(recognizer.settings.board_rows)
    ]
    print(
        "[INFO] Hex grid:    "
        + " ".join(
            f"r{row}=w{half_width * 2}/h{half_height * 2}"
            for row, (half_width, half_height) in enumerate(board_hex)
        )
    )
    print(
        "[INFO] Bench geom:  "
        f"ctx_w{recognizer.settings.bench_half_width_px_at_1920 * 2}/"
        f"up{recognizer.settings.bench_up_px_at_1080}/"
        f"down{recognizer.settings.bench_down_px_at_1080} "
        f"fp_w{recognizer.settings.bench_footprint_half_width_px_at_1920 * 2}/"
        f"up{recognizer.settings.bench_footprint_up_px_at_1080}/"
        f"down{recognizer.settings.bench_footprint_down_px_at_1080} "
        f"anchor_y={recognizer.settings.bench_left[1]:.3f}"
    )
    print(f"[INFO] Board:       {'PRESENT' if result.board_present else 'ABSENT'} score={result.board_presence_score:.3f} occupied={result.board_occupied_count} uncertain={result.board_uncertain_count}/28")
    for row in range(recognizer.settings.board_rows):
        cells=[c for c in result.board_cells if c.row==row]
        symbols=' '.join('O' if c.status=='occupied' else '.' if c.status=='empty' else '?' for c in cells)
        scores=' '.join(f'{c.score:.2f}' for c in cells)
        print(f"  row={row} {symbols}   scores={scores}")
    print(f"[INFO] Bench:       {'PRESENT' if result.bench_present else 'ABSENT'} score={result.bench_presence_score:.3f} occupied={result.bench_occupied_count} uncertain={result.bench_uncertain_count}/9")
    if result.bench_slots:
        print("  " + ' '.join('O' if c.status=='occupied' else '.' if c.status=='empty' else '?' for c in result.bench_slots))
        print("  scores=" + ' '.join(f'{c.score:.2f}' for c in result.bench_slots))
    print("[INFO] Legend:      O=occupied .=empty ?=uncertain")
    print(f"[OK] Overlay:      {debug['overlay']}")
    print(f"[OK] Result:       {debug['result_path']}")
    print(f"[OK] Board cells:  {debug['board_dir']}")
    print(f"[OK] Bench slots:  {debug['bench_dir']}")
    return 0


def cmd_perceive_board(args):
    cfg=load_yaml(Path(args.config)); recognizer=_build_board_bench_recognizer(args,cfg)
    match_dir=Path(args.match_dir)
    if not match_dir.exists(): raise FileNotFoundError(f"Match directory not found: {match_dir}")
    s=process_match_board_bench(match_dir,recognizer,stride=args.stride,limit=args.limit)
    print(f"[INFO] Match:       {match_dir}")
    print(f"[INFO] Producer:    {s['producer_version']}")
    print(f"[OK] Frames:       {s['processed_frames']}")
    print(f"[INFO] Board:       present={s['board_present']}/{s['processed_frames']} ({s['board_presence_rate']*100:.1f}%) observations={s['board_observation_count']}")
    print(f"[INFO] Board occ:   mean={s['mean_board_occupied_count']:.2f}/28 uncertain_mean={s['mean_board_uncertain_count']:.2f} uncertain_rate={s['board_uncertain_rate']*100:.1f}% changes={s['board_snapshot_changes']}")
    print(f"[INFO] Bench:       present={s['bench_present']}/{s['processed_frames']} ({s['bench_presence_rate']*100:.1f}%) observations={s['bench_observation_count']}")
    print(f"[INFO] Bench occ:   mean={s['mean_bench_occupied_count']:.2f}/9 uncertain_mean={s['mean_bench_uncertain_count']:.2f} uncertain_rate={s['bench_uncertain_rate']*100:.1f}% changes={s['bench_snapshot_changes']}")
    print(f"[INFO] Max gaps:    board={s['max_board_observation_gap_s']:.1f}s bench={s['max_bench_observation_gap_s']:.1f}s")
    print(f"[OK] Board JSONL:  {s['board_observations_path']}")
    print(f"[OK] Bench JSONL:  {s['bench_observations_path']}")
    print(f"[OK] Attempts:     {s['attempts_path']}")
    print(f"[OK] Summary:      {s['summary_path']}")
    return 0


def cmd_track_board(args):
    cfg = load_yaml(Path(args.config))
    tracking_cfg = cfg.get("tracking", {}).get("board_occupancy", {})
    settings = BoardOccupancyTrackerSettings(
        background_quantile=float(tracking_cfg.get("background_quantile", 0.22)),
        background_min_candidates=int(tracking_cfg.get("background_min_candidates", 12)),
        foreground_empty_below=float(tracking_cfg.get("foreground_empty_below", 0.34)),
        foreground_occupied_above=float(tracking_cfg.get("foreground_occupied_above", 0.58)),
        confirmation_count=int(tracking_cfg.get("confirmation_count", 2)),
        board_stable_frames_required=int(tracking_cfg.get("board_stable_frames_required", 1)),
        board_max_motion_cells=int(tracking_cfg.get("board_max_motion_cells", 10)),
        board_max_candidate_changes=int(tracking_cfg.get("board_max_candidate_changes", 8)),
        board_max_uncertain_cells=int(tracking_cfg.get("board_max_uncertain_cells", 12)),
        board_motion_delta=float(tracking_cfg.get("board_motion_delta", 0.18)),
        board_min_known_candidates=int(tracking_cfg.get("board_min_known_candidates", 16)),
        use_hud_board_context=bool(tracking_cfg.get("use_hud_board_context", True)),
        planning_min_round_age_s=float(tracking_cfg.get("planning_min_round_age_s", 2.5)),
        planning_max_round_age_s=float(tracking_cfg.get("planning_max_round_age_s", 32.0)),
        full_level_snapshot_max_uncertain=int(tracking_cfg.get("full_level_snapshot_max_uncertain", 14)),
        full_level_snapshot_min_mean_fg=float(tracking_cfg.get("full_level_snapshot_min_mean_fg", 0.60)),
        use_arena_scene_guard=bool(tracking_cfg.get("use_arena_scene_guard", True)),
        scene_guard_descriptor_size=int(tracking_cfg.get("scene_guard_descriptor_size", 48)),
        scene_guard_reference_fraction=float(tracking_cfg.get("scene_guard_reference_fraction", 0.60)),
        scene_guard_score_threshold=float(tracking_cfg.get("scene_guard_score_threshold", 0.12)),
        scene_guard_anchor_threshold=float(tracking_cfg.get("scene_guard_anchor_threshold", 0.15)),
        scene_guard_min_anchor_pass=int(tracking_cfg.get("scene_guard_min_anchor_pass", 3)),
    )
    match_dir = Path(args.match_dir)
    if not match_dir.exists():
        raise FileNotFoundError(f"Match directory not found: {match_dir}")
    summary = track_match_board_occupancy(
        match_dir,
        settings,
        attempts_path=args.attempts,
        hud_states_path=getattr(args, "hud_states", None),
    )
    print(f"[INFO] Match:       {match_dir}")
    print(f"[INFO] Tracker:     {summary['tracker_version']}")
    print(f"[INFO] Background:  board={summary['background_model_counts']['board']} bench={summary['background_model_counts']['bench']}")
    print(
        "[INFO] Raw changes:  "
        f"board={summary['raw_candidate_snapshot_changes']['board']} "
        f"bench={summary['raw_candidate_snapshot_changes']['bench']}"
    )
    gate = summary['board_gate']
    print(
        "[INFO] Board gate:   "
        f"usable={gate['usable_frames']} "
        f"warming={gate['warming_frames']} "
        f"unstable={gate['unstable_frames']} "
        f"rate={gate['usable_rate']*100:.1f}%"
    )
    print(
        "[INFO] HUD gate:     "
        f"aligned={gate['hud_aligned_frames']} "
        f"level_known={gate['hud_level_known_frames']} "
        f"full_cap={gate['strong_snapshot_frames']} "
        f"over_cap={gate['capacity_over_frames']} "
        f"tracked_over_cap={gate['tracked_over_level_frames']}"
    )
    print(
        "[INFO] Scene guard:  "
        f"valid={gate['scene_valid_frames']} "
        f"invalid={gate['scene_invalid_frames']} "
        f"invalid_full_cap={gate['scene_invalid_full_level_candidates']} "
        f"q50={gate['scene_score_stats']['q50']:.3f} "
        f"q90={gate['scene_score_stats']['q90']:.3f}"
    )
    bench_scene_guard = summary.get("bench_scene_guard", {})
    print(
        "[INFO] Bench guard:  "
        f"blocked_frames={bench_scene_guard.get('blocked_frames', 0)} "
        f"blocked_positions={bench_scene_guard.get('blocked_positions', 0)}"
    )
    print(
        "[INFO] Tracked:      "
        f"board_changes={summary['tracked_snapshot_changes']['board']} "
        f"bench_changes={summary['tracked_snapshot_changes']['bench']}"
    )
    print(
        "[INFO] Accepted:     "
        f"board={summary['accepted_semantic_changes']['board']} "
        f"bench={summary['accepted_semantic_changes']['bench']}"
    )
    print(f"[OK] Background:   {summary['background_path']}")
    print(f"[OK] Board states: {summary['board_states_path']}")
    print(f"[OK] Bench states: {summary['bench_states_path']}")
    print(f"[OK] Decisions:    {summary['decisions_path']}")
    print(f"[OK] Summary:      {summary['summary_path']}")
    if args.timeline:
        print()
        print(format_board_occupancy_timeline(
            summary['board_states_path'],
            summary['bench_states_path'],
            limit=args.timeline_limit,
        ))
    return 0


def cmd_board_qa(args):
    match_dir = Path(args.match_dir)
    if not match_dir.exists():
        raise FileNotFoundError(f"Match directory not found: {match_dir}")

    kinds = args.kind or ["full-cap"]
    result = export_board_formation_qa(
        match_dir,
        board_states_path=args.board_states,
        output_dir=args.output,
        kinds=kinds,
        open_gallery=args.open,
    )

    print(f"[INFO] Match:       {match_dir}")
    print(f"[INFO] QA:          {result['qa_version']}")
    print(f"[INFO] Board state: {result['board_states_path']}")
    print(
        "[INFO] Exported:     "
        + " ".join(
            f"{kind}={count}"
            for kind, count in result["kind_counts"].items()
        )
        + f" total={result['exported_count']}"
    )
    if result["missing_evidence_count"]:
        print(
            f"[WARN] Missing:      {result['missing_evidence_count']} evidence frame(s)"
        )
    print(f"[OK] QA directory: {result['output_dir']}")
    print(f"[OK] Manifest:     {result['manifest_path']}")
    print(f"[OK] Gallery:      {result['gallery_path']}")
    return 0


def _build_action_fusion_settings(cfg):
    action_cfg = cfg.get("actions", {}).get("fusion", {})
    return ActionFusionSettings(
        producer_version=str(
            action_cfg.get(
                "producer_version",
                "semantic-action-fusion-0.14.6",
            )
        ),
        reroll_gold_cost=int(
            action_cfg.get("reroll_gold_cost", 2)
        ),
        xp_purchase_gold_cost=int(
            action_cfg.get("xp_purchase_gold_cost", 4)
        ),
        xp_purchase_amount=int(
            action_cfg.get("xp_purchase_amount", 4)
        ),
        shop_refresh_min_changed_slots=int(
            action_cfg.get(
                "shop_refresh_min_changed_slots",
                4,
            )
        ),
        shop_refresh_min_occupied_slots=int(
            action_cfg.get(
                "shop_refresh_min_occupied_slots",
                4,
            )
        ),
        max_window_seconds=float(
            action_cfg.get("max_window_seconds", 20.0)
        ),
        emit_unknown_negative_econ=bool(
            action_cfg.get(
                "emit_unknown_negative_econ",
                True,
            )
        ),
    )




def _build_decision_episode_settings(cfg):
    episode_cfg = cfg.get("decisions", {}).get("episodes", {})
    return DecisionEpisodeSettings(
        producer_version=str(
            episode_cfg.get(
                "producer_version",
                "decision-episode-builder-0.15.0",
            )
        ),
        max_idle_gap_seconds=float(
            episode_cfg.get("max_idle_gap_seconds", 15.0)
        ),
        max_episode_duration_seconds=float(
            episode_cfg.get("max_episode_duration_seconds", 45.0)
        ),
        split_on_stage_change=bool(
            episode_cfg.get("split_on_stage_change", True)
        ),
        include_unknown_economy_only=bool(
            episode_cfg.get("include_unknown_economy_only", True)
        ),
    )



def _build_economy_tempo_analyzer_settings(cfg):
    analyzer_cfg = (
        cfg.get("analysis", {})
        .get("economy_tempo", {})
    )
    return EconomyTempoAnalyzerSettings(
        producer_version=str(
            analyzer_cfg.get(
                "producer_version",
                "economy-tempo-analyzer-0.16.1",
            )
        ),
        large_spend_threshold=int(
            analyzer_cfg.get("large_spend_threshold", 20)
        ),
        low_gold_after_threshold=int(
            analyzer_cfg.get("low_gold_after_threshold", 10)
        ),
        roll_burst_max_count_threshold=int(
            analyzer_cfg.get(
                "roll_burst_max_count_threshold",
                3,
            )
        ),
        emit_unresolved_economy_spend=bool(
            analyzer_cfg.get(
                "emit_unresolved_economy_spend",
                # Backward compatibility for an existing 0.16.0 config.
                analyzer_cfg.get(
                    "emit_required_unexplained_spend",
                    True,
                ),
            )
        ),
        emit_uncertainty_only=bool(
            analyzer_cfg.get("emit_uncertainty_only", False)
        ),
        emit_large_spend=bool(
            analyzer_cfg.get("emit_large_spend", True)
        ),
        emit_low_gold_review_candidate=bool(
            analyzer_cfg.get(
                "emit_low_gold_review_candidate",
                True,
            )
        ),
        emit_roll_activity=bool(
            analyzer_cfg.get("emit_roll_activity", True)
        ),
        emit_xp_investment=bool(
            analyzer_cfg.get("emit_xp_investment", True)
        ),
        emit_positioning_only=bool(
            analyzer_cfg.get("emit_positioning_only", True)
        ),
    )



def _build_episode_context_settings(cfg):
    feature_cfg = (
        cfg.get("features", {})
        .get("episode_context", {})
    )
    return EpisodeContextSettings(
        producer_version=str(
            feature_cfg.get(
                "producer_version",
                "episode-context-builder-0.17.1",
            )
        )
    )


def _build_roster_evidence_settings(cfg):
    feature_cfg = (
        cfg.get("features", {})
        .get("roster_evidence", {})
    )
    return RosterEvidenceSettings(
        producer_version=str(
            feature_cfg.get(
                "producer_version",
                "roster-evidence-builder-0.20.1",
            )
        ),
        min_confirmed_buy_confidence=float(
            feature_cfg.get(
                "min_confirmed_buy_confidence",
                0.68,
            )
        ),
        exclude_cost_conflict_from_confirmed=bool(
            feature_cfg.get(
                "exclude_cost_conflict_from_confirmed",
                True,
            )
        ),
        require_relevant_action_coverage=bool(
            feature_cfg.get(
                "require_relevant_action_coverage",
                True,
            )
        ),
    )


def _build_slot_identity_dataset_settings(cfg):
    feature_cfg = (
        cfg.get("features", {})
        .get("slot_identity_dataset", {})
    )

    statuses = feature_cfg.get(
        "selected_occupancy_statuses",
        ["occupied"],
    )
    return SlotIdentityDatasetSettings(
        producer_version=str(
            feature_cfg.get(
                "producer_version",
                "slot-identity-dataset-exporter-0.21.1",
            )
        ),
        export_board=bool(
            feature_cfg.get(
                "export_board",
                True,
            )
        ),
        export_bench=bool(
            feature_cfg.get(
                "export_bench",
                True,
            )
        ),
        selected_occupancy_statuses=tuple(
            str(value)
            for value in statuses
        ),
        min_raw_occupancy_confidence=float(
            feature_cfg.get(
                "min_raw_occupancy_confidence",
                0.55,
            )
        ),
        require_scene_valid=bool(
            feature_cfg.get(
                "require_scene_valid",
                True,
            )
        ),
    )


def _build_slot_identity_curation_settings(cfg):
    feature_cfg = (
        cfg.get("features", {})
        .get("slot_identity_curation", {})
    )

    return SlotIdentityCurationSettings(
        producer_version=str(
            feature_cfg.get(
                "producer_version",
                "slot-identity-curator-0.21.2",
            )
        ),
        max_temporal_gap_s=float(
            feature_cfg.get(
                "max_temporal_gap_s",
                15.0,
            )
        ),
        dhash_size=int(
            feature_cfg.get(
                "dhash_size",
                8,
            )
        ),
        max_dhash_distance=int(
            feature_cfg.get(
                "max_dhash_distance",
                6,
            )
        ),
        split_on_stage_change=bool(
            feature_cfg.get(
                "split_on_stage_change",
                True,
            )
        ),
    )


def _build_slot_identity_labeling_settings(cfg):
    feature_cfg = (
        cfg.get("features", {})
        .get("slot_identity_labeling", {})
    )

    return SlotIdentityLabelingSettings(
        package_producer_version=str(
            feature_cfg.get(
                "package_producer_version",
                "slot-identity-label-package-0.21.3",
            )
        ),
        import_producer_version=str(
            feature_cfg.get(
                "import_producer_version",
                "slot-identity-label-importer-0.21.3",
            )
        ),
        allow_partial_import=bool(
            feature_cfg.get(
                "allow_partial_import",
                True,
            )
        ),
        require_catalog_for_champion_labels=bool(
            feature_cfg.get(
                "require_catalog_for_champion_labels",
                True,
            )
        ),
    )


def _build_identity_labeler_settings(cfg):
    feature_cfg = (
        cfg.get("features", {})
        .get("slot_identity_labeler", {})
    )
    return IdentityLabelerSettings(
        producer_version=str(
            feature_cfg.get(
                "producer_version",
                "slot-identity-labeler-0.21.6",
            )
        ),
        host=str(
            feature_cfg.get(
                "host",
                "127.0.0.1",
            )
        ),
        port=int(
            feature_cfg.get(
                "port",
                8765,
            )
        ),
        open_browser=bool(
            feature_cfg.get(
                "open_browser",
                True,
            )
        ),
        annotator=(
            str(
                feature_cfg.get(
                    "annotator",
                    "",
                )
            ).strip()
            or None
        ),
    )


def _build_slot_identity_human_audit_settings(cfg):
    feature_cfg = (
        cfg.get("features", {})
        .get("slot_identity_human_audit", {})
    )

    return SlotIdentityHumanAuditSettings(
        producer_version=str(
            feature_cfg.get(
                "producer_version",
                "slot-identity-human-label-audit-0.21.7",
            )
        ),
        primary_evidence_tiers=tuple(
            str(value)
            for value in feature_cfg.get(
                "primary_evidence_tiers",
                ["trusted"],
            )
        ),
        secondary_evidence_tiers=tuple(
            str(value)
            for value in feature_cfg.get(
                "secondary_evidence_tiers",
                ["supported"],
            )
        ),
        recovered_candidate_tiers=tuple(
            str(value)
            for value in feature_cfg.get(
                "recovered_candidate_tiers",
                ["raw_candidate"],
            )
        ),
        export_all_human_no_unit_as_occupancy_hard_negative=bool(
            feature_cfg.get(
                "export_all_human_no_unit_as_occupancy_hard_negative",
                True,
            )
        ),
        hotspot_min_labeled_groups=int(
            feature_cfg.get(
                "hotspot_min_labeled_groups",
                1,
            )
        ),
        hotspot_limit=int(
            feature_cfg.get(
                "hotspot_limit",
                25,
            )
        ),
    )


def _build_context_review_analyzer_settings(cfg):
    analyzer_cfg = (
        cfg.get("analysis", {})
        .get("context_review", {})
    )
    return ContextReviewAnalyzerSettings(
        producer_version=str(
            analyzer_cfg.get(
                "producer_version",
                "context-review-analyzer-0.18.0",
            )
        ),
        pressure_hp_threshold=int(
            analyzer_cfg.get(
                "pressure_hp_threshold",
                35,
            )
        ),
        critical_hp_threshold=int(
            analyzer_cfg.get(
                "critical_hp_threshold",
                20,
            )
        ),
        near_elimination_hp_threshold=int(
            analyzer_cfg.get(
                "near_elimination_hp_threshold",
                10,
            )
        ),
        economy_commitment_spend_threshold=int(
            analyzer_cfg.get(
                "economy_commitment_spend_threshold",
                10,
            )
        ),
        large_spend_under_pressure_threshold=int(
            analyzer_cfg.get(
                "large_spend_under_pressure_threshold",
                20,
            )
        ),
        high_gold_under_pressure_threshold=int(
            analyzer_cfg.get(
                "high_gold_under_pressure_threshold",
                30,
            )
        ),
        emit_economy_commitment_under_pressure=bool(
            analyzer_cfg.get(
                "emit_economy_commitment_under_pressure",
                True,
            )
        ),
        emit_low_hp_roll_activity=bool(
            analyzer_cfg.get(
                "emit_low_hp_roll_activity",
                True,
            )
        ),
        emit_low_hp_level_up=bool(
            analyzer_cfg.get(
                "emit_low_hp_level_up",
                True,
            )
        ),
        emit_high_gold_under_pressure=bool(
            analyzer_cfg.get(
                "emit_high_gold_under_pressure",
                True,
            )
        ),
        emit_near_elimination_activity=bool(
            analyzer_cfg.get(
                "emit_near_elimination_activity",
                True,
            )
        ),
        emit_trusted_board_below_capacity=bool(
            analyzer_cfg.get(
                "emit_trusted_board_below_capacity",
                True,
            )
        ),
    )


def _build_match_review_report_settings(cfg):
    report_cfg = (
        cfg.get("reports", {})
        .get("match_review", {})
    )
    return MatchReviewReportSettings(
        producer_version=str(
            report_cfg.get(
                "producer_version",
                "match-review-report-0.19.0",
            )
        ),
        include_data_quality_cards=bool(
            report_cfg.get(
                "include_data_quality_cards",
                True,
            )
        ),
    )


def _game_data_cfg(cfg):
    return cfg.get("game_data", {})


def _resolve_action_catalog_path(args, cfg):
    if getattr(args, "no_game_data", False):
        return None

    explicit = getattr(args, "game_data_catalog", None)
    if explicit:
        path = Path(explicit)
        if not path.exists():
            raise FileNotFoundError(
                f"Game-data catalog not found: {path}"
            )
        return path

    game_cfg = _game_data_cfg(cfg)

    configured = game_cfg.get("catalog_path")
    if configured:
        path = Path(configured)
        if not path.exists():
            raise FileNotFoundError(
                f"Configured game-data catalog not found: {path}"
            )
        return path

    if not bool(
        game_cfg.get("auto_use_active_catalog", True)
    ):
        return None

    root_dir = Path(
        game_cfg.get(
            "root_dir",
            "data/game_data",
        )
    )
    return find_active_catalog_path(root_dir)


def cmd_sync_game_data(args):
    cfg = load_yaml(Path(args.config))
    game_cfg = _game_data_cfg(cfg)

    provider = str(
        game_cfg.get(
            "provider",
            "riot_ddragon",
        )
    )
    if provider != "riot_ddragon":
        raise ValueError(
            f"Unsupported game-data provider {provider!r}; "
            "currently supported: riot_ddragon"
        )

    version = str(
        args.version
        or game_cfg.get(
            "version",
            "latest",
        )
    )
    locale = str(
        args.locale
        or game_cfg.get(
            "locale",
            "en_US",
        )
    )
    root_dir = Path(
        args.root_dir
        or game_cfg.get(
            "root_dir",
            "data/game_data",
        )
    )
    timeout_seconds = float(
        game_cfg.get(
            "timeout_seconds",
            30.0,
        )
    )

    summary = sync_riot_ddragon_catalog(
        root_dir,
        version=version,
        locale=locale,
        timeout_seconds=timeout_seconds,
        source_file=(
            Path(args.from_file)
            if args.from_file
            else None
        ),
        force=bool(args.force),
    )

    print(f"[INFO] Provider:     {summary['provider']}")
    print(
        "[INFO] Version:      "
        f"requested={summary['requested_version']} "
        f"resolved={summary['version']} "
        f"locale={summary['locale']}"
    )
    print(
        "[INFO] Champions:    "
        f"{summary['champion_count']} "
        f"tiers={summary['tiers']}"
    )
    print(
        "[INFO] Source SHA:   "
        f"{summary['source_sha256']}"
    )
    print(
        "[OK] Catalog:      "
        f"{summary['catalog_path']}"
    )
    print(
        "[OK] Active ptr:   "
        f"{summary['active_pointer_path']}"
    )

    return 0



def cmd_build_episodes(args):
    cfg = load_yaml(Path(args.config))
    settings = _build_decision_episode_settings(cfg)

    summary = build_match_decision_episodes(
        Path(args.match_dir),
        settings,
        action_summary_path=(
            Path(args.action_summary)
            if args.action_summary
            else None
        ),
    )

    print(f"[INFO] Match:       {summary['match_dir']}")
    print(f"[INFO] Episodes:    {summary['producer_version']}")
    print(
        "[INFO] Source:      "
        f"{summary['input_action_producer_version']} "
        f"actions={summary['input_action_count']}"
    )
    print(
        "[OK] Episodes:     "
        f"{summary['episode_count']} "
        f"multi_window={summary['multi_window_episode_count']} "
        f"compound_groups={summary['compound_action_group_count']}"
    )
    print(
        "[INFO] Ordering:    "
        f"{summary['ordering_policy']} "
        f"exact_sequences={summary['exact_sequence_reconstructed_count']}"
    )
    print(
        "[INFO] Coverage:    "
        f"actions={summary['covered_action_count']}/"
        f"{summary['input_action_count']} "
        f"uncovered={summary['uncovered_action_count']}"
    )
    print(
        "[INFO] Economy QA: "
        f"infeasible_episodes={summary['infeasible_episode_count']}"
    )
    print("[INFO] Decision types:")
    for key, value in sorted(summary["decision_type_counts"].items()):
        print(f"  {key:<24} {value}")

    print(f"[OK] Episodes JSONL: {summary['episodes_path']}")
    print(f"[OK] Summary:        {summary['summary_path']}")

    if args.timeline:
        print()
        print(
            format_decision_episode_timeline(
                summary["episodes_path"],
                limit=args.timeline_limit,
            )
        )

    return 0




def cmd_build_episode_context(args):
    cfg = load_yaml(Path(args.config))
    settings = _build_episode_context_settings(cfg)

    summary = build_match_episode_context(
        Path(args.match_dir),
        settings,
        episode_summary_path=(
            Path(args.episode_summary)
            if args.episode_summary
            else None
        ),
        hud_states_path=(
            Path(args.hud_states)
            if args.hud_states
            else None
        ),
        board_states_path=(
            Path(args.board_states)
            if args.board_states
            else None
        ),
        bench_states_path=(
            Path(args.bench_states)
            if args.bench_states
            else None
        ),
    )

    print(f"[INFO] Match:       {summary['match_dir']}")
    print(f"[INFO] Context:     {summary['producer_version']}")
    print(
        "[INFO] Source:      "
        f"{summary['input_episode_producer_version']} "
        f"episodes={summary['episode_count']}"
    )
    print(
        "[OK] Contexts:     "
        f"{summary['context_count']}/{summary['episode_count']} "
        f"fully_exact={summary['fully_exact_context_count']}"
    )
    print(
        "[INFO] Player HUD:  "
        f"hp_both={summary['hp_known_both_count']}/"
        f"{summary['context_count']} "
        f"hp_range={summary['hp_observed_min']}..{summary['hp_observed_max']}"
    )
    print(
        "[INFO] Board:       "
        f"known_both={summary['board_known_both_count']}/"
        f"{summary['context_count']} "
        f"util_both={summary['board_utilization_known_both_count']}/"
        f"{summary['context_count']} "
        f"scene_invalid_boundaries={summary['scene_invalid_boundary_count']}"
    )
    print(
        "[INFO] Trust:       "
        f"hp_usable_both={summary['hp_strategy_usable_both_count']}/"
        f"{summary['context_count']} "
        f"board_exact_both={summary['board_exact_both_count']}/"
        f"{summary['context_count']} "
        f"board_usable_both={summary['board_strategy_usable_both_count']}/"
        f"{summary['context_count']} "
        f"board_lower_bound={summary['board_lower_bound_context_count']} "
        f"board_unusable={summary['board_unusable_context_count']}"
    )
    print(
        "[INFO] Economy QA:  "
        f"infeasible={summary['economy_infeasible_context_count']} "
        f"reconstruction_uncertainty="
        f"{summary['reconstruction_uncertainty_context_count']}"
    )
    game = summary.get("game_context") or {}
    print(
        "[INFO] Game:        "
        f"set={game.get('set_id')} "
        f"patch={game.get('patch')}"
    )
    print(f"[OK] Context JSONL: {summary['contexts_path']}")
    print(f"[OK] Summary:       {summary['summary_path']}")

    if args.timeline:
        print()
        print(
            format_episode_context_timeline(
                summary["contexts_path"],
                limit=args.timeline_limit,
            )
        )
    return 0


def cmd_label_identities(args):
    cfg = load_yaml(Path(args.config))
    defaults = _build_identity_labeler_settings(
        cfg
    )
    catalog_path = _resolve_action_catalog_path(
        args,
        cfg,
    )

    settings = IdentityLabelerSettings(
        producer_version=defaults.producer_version,
        host=(
            args.host
            if args.host is not None
            else defaults.host
        ),
        port=(
            args.port
            if args.port is not None
            else defaults.port
        ),
        open_browser=(
            False
            if args.no_browser
            else defaults.open_browser
        ),
        annotator=(
            args.annotator
            if args.annotator is not None
            else defaults.annotator
        ),
    )

    run_identity_labeler(
        Path(args.match_dir),
        settings,
        package_dir=(
            Path(args.label_package_dir)
            if args.label_package_dir
            else None
        ),
        catalog_path=catalog_path,
    )
    return 0


def cmd_prepare_identity_labeling(args):
    cfg = load_yaml(Path(args.config))
    settings = _build_slot_identity_labeling_settings(
        cfg
    )
    catalog_path = _resolve_action_catalog_path(
        args,
        cfg,
    )

    package = prepare_identity_label_package(
        Path(args.match_dir),
        settings,
        curation_dir=(
            Path(args.curation_dir)
            if args.curation_dir
            else None
        ),
        catalog_path=catalog_path,
        output_dir=(
            Path(args.output_dir)
            if args.output_dir
            else None
        ),
        force=bool(args.force),
    )

    print(f"[INFO] Match:       {package['match_dir']}")
    print(f"[INFO] Package:     {package['producer_version']}")
    print(
        "[INFO] Source:      "
        f"{package['source_curation_producer_version']} "
        f"groups={package['visual_group_count']}"
    )
    queue_counts = package.get("queue_type_counts") or {}
    print(
        "[OK] Queues:       "
        f"identity={queue_counts.get('identity_label', 0)} "
        f"occupancy_qa={queue_counts.get('occupancy_qa', 0)}"
    )
    game = package.get("game_context") or {}
    print(
        "[INFO] Game:        "
        f"set={game.get('set_id')} "
        f"patch={game.get('patch')} "
        f"ddragon={game.get('data_dragon_version')}"
    )
    print(
        "[INFO] Catalog:     "
        f"available={package['catalog_available']} "
        f"champions={package['catalog_champion_count']}"
    )
    print(
        f"[OK] Labels CSV:   {package['labels_path']}"
    )
    print(
        f"[OK] Schema:       {package['label_schema_path']}"
    )
    print(
        f"[OK] CVAT map:     {package['cvat_image_manifest_path']}"
    )
    print(
        f"[OK] Images:       {package['images_dir']}"
    )
    print(
        f"[OK] Package:      {package['package_path']}"
    )
    return 0


def cmd_import_identity_labels(args):
    cfg = load_yaml(Path(args.config))
    settings = _build_slot_identity_labeling_settings(
        cfg
    )
    catalog_path = _resolve_action_catalog_path(
        args,
        cfg,
    )

    summary = import_identity_labels(
        Path(args.match_dir),
        settings,
        labels_path=(
            Path(args.labels)
            if args.labels
            else None
        ),
        label_package_dir=(
            Path(args.label_package_dir)
            if args.label_package_dir
            else None
        ),
        curation_dir=(
            Path(args.curation_dir)
            if args.curation_dir
            else None
        ),
        catalog_path=catalog_path,
        output_dir=(
            Path(args.output_dir)
            if args.output_dir
            else None
        ),
        require_complete=bool(
            args.require_complete
        ),
        require_complete_queue=(
            args.require_complete_queue
        ),
        force=bool(args.force),
    )

    print(f"[INFO] Match:       {summary['match_dir']}")
    print(f"[INFO] Importer:    {summary['producer_version']}")
    print(
        "[OK] Coverage:     "
        f"labeled={summary['labeled_group_count']}/"
        f"{summary['source_visual_group_count']} "
        f"unlabeled={summary['unlabeled_group_count']}"
    )
    print(
        "[INFO] Queues:      "
        f"identity={summary['identity_label_queue_labeled']}/"
        f"{summary['identity_label_queue_total']} "
        f"occupancy_qa={summary['occupancy_qa_queue_labeled']}/"
        f"{summary['occupancy_qa_queue_total']}"
    )
    print("[INFO] Targets:")
    for key in (
        "champion",
        "no_unit",
        "uncertain",
        "unusable",
    ):
        print(
            f"  {key:<12} "
            f"{summary['target_type_counts'].get(key, 0)}"
        )
    print(
        "[INFO] Classes:     "
        f"champions={summary['champion_class_count']} "
        f"training_eligible="
        f"{summary['visual_champion_training_eligible_group_count']} "
        f"no_unit_negatives="
        f"{summary['occupancy_negative_eligible_group_count']}"
    )
    print(
        "[INFO] QA conflicts:"
        f" no_unit_on_identity_queue="
        f"{summary['identity_queue_no_unit_conflict_count']}"
    )

    if summary["per_champion"]:
        print("[INFO] Per champion:")
        for champion, values in sorted(
            summary["per_champion"].items()
        ):
            locations = values.get(
                "locations",
                {},
            )
            print(
                f"  {champion:<22} "
                f"groups={values['visual_group_count']:4d} "
                f"train={values['training_eligible_group_count']:4d} "
                f"matches={values['match_count']:2d} "
                f"board={locations.get('board', 0):4d} "
                f"bench={locations.get('bench', 0):4d}"
            )

    print(
        "[INFO] Split:       unit=match_id "
        f"matches={summary['split_policy']['current_match_count']}"
    )
    print(
        f"[OK] Labeled JSONL:{summary['labeled_visual_groups_path']}"
    )
    print(
        f"[OK] Train CSV:    {summary['visual_champion_training_manifest_path']}"
    )
    print(
        f"[OK] Negatives:    {summary['occupancy_negative_manifest_path']}"
    )
    print(
        f"[OK] Summary:      {summary['summary_path']}"
    )
    return 0


def cmd_audit_identity_labels(args):
    cfg = load_yaml(Path(args.config))
    settings = _build_slot_identity_human_audit_settings(
        cfg
    )

    summary = audit_identity_labels(
        Path(args.match_dir),
        settings,
        label_import_dir=(
            Path(args.label_import_dir)
            if args.label_import_dir
            else None
        ),
        output_dir=(
            Path(args.output_dir)
            if args.output_dir
            else None
        ),
        force=bool(args.force),
    )

    print(f"[INFO] Match:       {summary['match_dir']}")
    print(f"[INFO] Audit:       {summary['producer_version']}")
    print(
        "[INFO] Source:      "
        f"{summary['source_importer_version']} "
        f"labeled={summary['source_labeled_group_count']} "
        f"unlabeled={summary['source_unlabeled_group_count']}"
    )
    print("[INFO] Human targets:")
    for key in (
        "champion",
        "no_unit",
        "uncertain",
        "unusable",
    ):
        print(
            f"  {key:<12} "
            f"{summary['target_type_counts'].get(key, 0)}"
        )

    print(
        "[OK] Identity policy: "
        f"primary={summary['primary_group_count']} "
        f"secondary={summary['secondary_group_count']} "
        f"recovered={summary['recovered_candidate_group_count']} "
        f"human_confirmed={summary['human_confirmed_champion_manifest_group_count']}"
    )
    print(
        "[OK] Occupancy QA:  "
        f"hard_negatives={summary['occupancy_hard_negative_group_count']}"
    )

    target_location = (
        summary[
            "cross_tabs"
        ][
            "target_by_location"
        ]
    )
    print("[INFO] Target x location:")
    for target in (
        "champion",
        "no_unit",
        "uncertain",
        "unusable",
    ):
        row = target_location.get(target, {})
        print(
            f"  {target:<12} "
            f"board={row.get('board', 0):4d} "
            f"bench={row.get('bench', 0):4d}"
        )

    target_tier = (
        summary[
            "cross_tabs"
        ][
            "target_by_representative_tier"
        ]
    )
    print("[INFO] Target x evidence tier:")
    for target in (
        "champion",
        "no_unit",
        "uncertain",
        "unusable",
    ):
        row = target_tier.get(target, {})
        print(
            f"  {target:<12} "
            f"trusted={row.get('trusted', 0):4d} "
            f"supported={row.get('supported', 0):4d} "
            f"raw={row.get('raw_candidate', 0):4d}"
        )

    if summary["occupancy_false_positive_hotspots"]:
        print("[INFO] Occupancy hotspots:")
        for item in summary["occupancy_false_positive_hotspots"][:10]:
            print(
                f"  {item['location']:<5} {item['slot_id']:<5} "
                f"n={item['labeled_group_count']:3d} "
                f"champ={item['champion_count']:3d} "
                f"no_unit={item['no_unit_count']:3d} "
                f"uncertain={item['uncertain_count']:3d} "
                f"no_unit_rate={item['no_unit_rate']:.3f}"
            )

    print("[INFO] Per champion:")
    for champion, values in sorted(
        summary["per_champion"].items()
    ):
        locations = values.get(
            "locations",
            {},
        )
        print(
            f"  {champion:<22} "
            f"human={values['human_confirmed_group_count']:4d} "
            f"P={values['primary_group_count']:4d} "
            f"S={values['secondary_group_count']:4d} "
            f"R={values['recovered_candidate_group_count']:4d} "
            f"matches={values['match_count']:2d} "
            f"board={locations.get('board', 0):4d} "
            f"bench={locations.get('bench', 0):4d}"
        )

    print(
        "[INFO] Split:       unit=match_id "
        f"matches={summary['split_policy']['current_match_count']}"
    )
    print(
        f"[OK] Primary:      {summary['primary_manifest_path']}"
    )
    print(
        f"[OK] Secondary:    {summary['secondary_manifest_path']}"
    )
    print(
        f"[OK] Human all:    {summary['human_confirmed_manifest_path']}"
    )
    print(
        f"[OK] Hard neg:     {summary['occupancy_hard_negative_manifest_path']}"
    )
    print(
        f"[OK] Summary:      {summary['summary_path']}"
    )
    return 0


def cmd_curate_slot_identity_dataset(args):
    cfg = load_yaml(Path(args.config))
    settings = _build_slot_identity_curation_settings(
        cfg
    )

    settings = SlotIdentityCurationSettings(
        producer_version=settings.producer_version,
        max_temporal_gap_s=(
            args.max_gap_seconds
            if args.max_gap_seconds is not None
            else settings.max_temporal_gap_s
        ),
        dhash_size=settings.dhash_size,
        max_dhash_distance=(
            args.max_dhash_distance
            if args.max_dhash_distance is not None
            else settings.max_dhash_distance
        ),
        split_on_stage_change=(
            False
            if args.allow_stage_crossing
            else settings.split_on_stage_change
        ),
        identity_tiers=settings.identity_tiers,
        occupancy_qa_tiers=settings.occupancy_qa_tiers,
    )

    summary = curate_slot_identity_dataset(
        Path(args.match_dir),
        settings,
        source_dataset_dir=(
            Path(args.source_dataset_dir)
            if args.source_dataset_dir
            else None
        ),
        output_dir=(
            Path(args.output_dir)
            if args.output_dir
            else None
        ),
        force=bool(args.force),
    )

    print(f"[INFO] Match:       {summary['match_dir']}")
    print(f"[INFO] Curator:     {summary['producer_version']}")
    print(
        "[INFO] Source:      "
        f"{summary['source_dataset_producer_version']} "
        f"samples={summary['source_sample_count']}"
    )
    print(
        "[INFO] Settings:    "
        f"gap<={summary['settings']['max_temporal_gap_s']:.1f}s "
        f"dhash<={summary['settings']['max_dhash_distance']} "
        f"stage_split={summary['settings']['split_on_stage_change']}"
    )
    print(
        "[OK] Groups:       "
        f"{summary['visual_group_count']} "
        f"identity={summary['identity_label_group_count']} "
        f"occupancy_qa={summary['occupancy_qa_group_count']}"
    )
    print(
        "[INFO] Reduction:   "
        f"identity={summary['identity_temporal_reduction_ratio']:.3f} "
        f"occupancy_qa={summary['occupancy_qa_temporal_reduction_ratio']:.3f}"
    )
    print(
        "[INFO] Mean group:  "
        f"identity={summary['mean_identity_group_size']:.2f} "
        f"occupancy_qa={summary['mean_occupancy_qa_group_size']:.2f}"
    )

    tier_location = (
        summary["cross_tabs"]["tier_by_location"]
    )
    print("[INFO] Tier x location:")
    for tier in (
        "trusted",
        "supported",
        "raw_candidate",
    ):
        row = tier_location.get(tier, {})
        print(
            f"  {tier:<14} "
            f"board={row.get('board', 0):4d} "
            f"bench={row.get('bench', 0):4d}"
        )

    group_location = (
        summary[
            "group_counts_by_queue_and_location"
        ]
    )
    print("[INFO] Groups x location:")
    for queue in (
        "identity_label",
        "occupancy_qa",
    ):
        row = group_location.get(queue, {})
        print(
            f"  {queue:<14} "
            f"board={row.get('board', 0):4d} "
            f"bench={row.get('bench', 0):4d}"
        )

    print(
        "[INFO] Split:       unit=match_id "
        "random_crop_split=False"
    )
    print(
        f"[OK] Groups JSONL: {summary['visual_groups_path']}"
    )
    print(
        f"[OK] Identity CSV: {summary['identity_label_queue_path']}"
    )
    print(
        f"[OK] QA CSV:       {summary['occupancy_qa_queue_path']}"
    )
    print(
        f"[OK] Reps:         {summary['representatives_dir']}"
    )
    print(
        f"[OK] Summary:      {summary['summary_path']}"
    )

    if args.timeline:
        print()
        print(
            format_slot_identity_curation_timeline(
                summary["visual_groups_path"],
                limit=args.timeline_limit,
                queue_type=(
                    args.queue
                    if args.queue != "all"
                    else None
                ),
            )
        )

    return 0


def cmd_export_slot_identity_dataset(args):
    cfg = load_yaml(Path(args.config))
    settings = _build_slot_identity_dataset_settings(
        cfg
    )

    statuses = list(
        settings.selected_occupancy_statuses
    )
    if args.include_uncertain and "uncertain" not in statuses:
        statuses.append("uncertain")
    if args.include_empty and "empty" not in statuses:
        statuses.append("empty")

    settings = SlotIdentityDatasetSettings(
        producer_version=settings.producer_version,
        export_board=(
            settings.export_board
            and not args.bench_only
        ),
        export_bench=(
            settings.export_bench
            and not args.board_only
        ),
        selected_occupancy_statuses=tuple(statuses),
        min_raw_occupancy_confidence=(
            args.min_occupancy_confidence
            if args.min_occupancy_confidence is not None
            else settings.min_raw_occupancy_confidence
        ),
        require_scene_valid=(
            False
            if args.allow_scene_invalid
            else settings.require_scene_valid
        ),
        image_format="png",
    )

    if args.board_only and args.bench_only:
        raise ValueError(
            "--board-only and --bench-only cannot be used together."
        )

    summary = export_slot_identity_dataset(
        Path(args.match_dir),
        settings,
        board_tracker_summary_path=(
            Path(args.board_tracker_summary)
            if args.board_tracker_summary
            else None
        ),
        roster_summary_path=(
            Path(args.roster_summary)
            if args.roster_summary
            else None
        ),
        output_dir=(
            Path(args.output_dir)
            if args.output_dir
            else None
        ),
        force=bool(args.force),
    )

    print(f"[INFO] Match:       {summary['match_dir']}")
    print(f"[INFO] Dataset:     {summary['producer_version']}")
    print(
        "[INFO] Selection:   "
        f"statuses={summary['settings']['selected_occupancy_statuses']} "
        f"min_conf={summary['settings']['min_raw_occupancy_confidence']:.2f} "
        f"scene_valid_only={summary['settings']['require_scene_valid']}"
    )
    game = summary.get("game_context") or {}
    print(
        "[INFO] Game:        "
        f"set={game.get('set_id')} "
        f"patch={game.get('patch')} "
        f"ddragon={game.get('data_dragon_version')}"
    )
    print(
        "[OK] Samples:      "
        f"{summary['sample_count']} "
        f"board={summary['board_sample_count']} "
        f"bench={summary['bench_sample_count']}"
    )
    print(
        "[INFO] Source:      "
        f"attempts={summary['source_attempt_count']} "
        f"scene_valid={summary['scene_valid_attempt_count']} "
        f"scene_invalid={summary['scene_invalid_attempt_count']}"
    )
    print(
        "[INFO] Tracker:     "
        f"current_evidence_samples="
        f"{summary['tracked_current_evidence_sample_count']} "
        f"strong_board_samples="
        f"{summary['board_strong_snapshot_sample_count']}"
    )
    tiers = summary.get("occupancy_evidence_tier_counts") or {}
    print(
        "[INFO] Quality:     "
        f"trusted={tiers.get('trusted', 0)} "
        f"supported={tiers.get('supported', 0)} "
        f"raw_candidate={tiers.get('raw_candidate', 0)}"
    )
    print(
        "[INFO] Recommended: "
        f"train={summary['identity_training_recommended_sample_count']} "
        f"label={summary['identity_labeling_recommended_sample_count']} "
        f"occupancy_review={summary['occupancy_review_recommended_sample_count']}"
    )
    print(
        "[INFO] Priors:      "
        f"with_any={summary['sample_with_acquisition_prior_count']} "
        f"with_confirmed={summary['sample_with_confirmed_acquisition_prior_count']} "
        f"with_candidate={summary['sample_with_candidate_acquisition_prior_count']} "
        f"exhaustive=False"
    )
    print(
        "[INFO] Labels:      "
        f"unlabeled={summary['label_status_counts']['unlabeled']} "
        "inferred=0"
    )
    print(
        f"[OK] Manifest:     {summary['manifest_path']}"
    )
    print(
        f"[OK] Labels CSV:   {summary['labels_template_path']}"
    )
    print(
        f"[OK] Images:       {summary['images_dir']}"
    )
    print(
        f"[OK] Summary:      {summary['summary_path']}"
    )

    if args.timeline:
        print()
        print(
            format_slot_identity_dataset_timeline(
                summary["manifest_path"],
                limit=args.timeline_limit,
            )
        )
    return 0


def cmd_build_roster_evidence(args):
    cfg = load_yaml(Path(args.config))
    settings = _build_roster_evidence_settings(
        cfg
    )

    summary = build_match_roster_evidence(
        Path(args.match_dir),
        settings,
        episode_summary_path=(
            Path(args.episode_summary)
            if args.episode_summary
            else None
        ),
    )

    print(f"[INFO] Match:       {summary['match_dir']}")
    print(f"[INFO] Roster:      {summary['producer_version']}")
    print(
        "[INFO] Source:      "
        f"{summary['input_episode_producer_version']} "
        f"episodes={summary['episode_count']} "
        f"actions={summary['input_action_count']}"
    )
    game = summary.get("game_context") or {}
    print(
        "[INFO] Game:        "
        f"set={game.get('set_id')} "
        f"patch={game.get('patch')} "
        f"ddragon={game.get('data_dragon_version')}"
    )
    print(
        "[OK] Coverage:     "
        f"relevant="
        f"{summary['covered_roster_relevant_action_count']}/"
        f"{summary['roster_relevant_action_count']} "
        f"uncovered="
        f"{summary['uncovered_roster_relevant_action_count']}"
    )
    print(
        "[INFO] BUY identity:"
        f" confirmed={summary['confirmed_identity_buy_copy_count']} "
        f"candidate={summary['candidate_identity_buy_copy_count']} "
        f"unidentified="
        f"{summary['unidentified_confirmed_buy_copy_count'] + summary['unidentified_candidate_buy_copy_count']} "
        f"coverage={summary['confirmed_buy_identity_coverage']:.3f}"
    )
    print(
        "[INFO] SELL/econ:   "
        f"identified_sell_units="
        f"{summary['identified_sell_unit_count']} "
        f"unknown_sell_units>="
        f"{summary['unidentified_sell_unit_count_lower_bound']} "
        f"unknown_econ="
        f"{summary['unknown_economy_action_count']}"
    )
    print(
        "[INFO] Acquisition: historical_lower_bound "
        f"current_ownership="
        f"{summary['current_ownership_status']} "
        f"complete_sell_history="
        f"{summary['complete_sell_history_known']}"
    )
    print("[INFO] Final confirmed acquisition lower bounds:")
    final_bounds = (
        summary[
            "final_confirmed_acquisition_copy_lower_bounds"
        ]
    )
    if final_bounds:
        for champion, count in final_bounds.items():
            print(f"  {champion:<24} acquired>= {count}")
    else:
        print("  -")

    candidates = summary[
        "final_candidate_acquisitions"
    ]
    if candidates:
        print("[INFO] Candidate acquisitions:")
        for champion, count in candidates.items():
            print(f"  {champion:<24} ?= {count}")

    print(
        f"[OK] Roster JSONL: "
        f"{summary['contexts_path']}"
    )
    print(
        f"[OK] Summary:      "
        f"{summary['summary_path']}"
    )

    if args.timeline:
        print()
        print(
            format_roster_evidence_timeline(
                summary["contexts_path"],
                limit=args.timeline_limit,
                changes_only=bool(
                    args.changes_only
                ),
            )
        )
    return 0


def cmd_build_review_report(args):
    cfg = load_yaml(Path(args.config))
    settings = _build_match_review_report_settings(cfg)

    summary = build_match_review_report(
        Path(args.match_dir),
        settings,
        context_review_summary_path=(
            Path(args.context_review_summary)
            if args.context_review_summary
            else None
        ),
    )

    print(f"[INFO] Match:       {summary['match_dir']}")
    print(f"[INFO] Report:      {summary['producer_version']}")
    print(
        "[INFO] Source:      "
        f"{summary['input_context_review_producer_version']} "
        f"findings={summary['input_finding_count']}"
    )
    game = summary.get("game_context") or {}
    print(
        "[INFO] Game:        "
        f"set={game.get('set_id')} "
        f"patch={game.get('patch')}"
    )
    print(
        "[OK] Cards:        "
        f"{summary['card_count']} "
        f"gameplay={summary['gameplay_review_card_count']} "
        f"data_quality={summary['data_quality_card_count']} "
        f"decision_grades={summary['decision_grade_count']}"
    )
    print("[INFO] Priorities:")
    for key in ("critical", "high", "medium", "low"):
        if key in summary["priority_counts"]:
            print(f"  {key:<10} {summary['priority_counts'][key]}")
    print(f"[OK] Cards JSONL:  {summary['cards_path']}")
    print(f"[OK] Markdown:     {summary['markdown_path']}")
    print(f"[OK] Summary:      {summary['summary_path']}")

    if args.timeline:
        from tft_analyzer.reports.review.models import MatchReviewCard
        cards = []
        with Path(summary["cards_path"]).open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    cards.append(MatchReviewCard.model_validate_json(line))
        print()
        print(format_review_cards_timeline(cards, limit=args.timeline_limit))
    return 0


def cmd_analyze_context(args):
    cfg = load_yaml(Path(args.config))
    settings = _build_context_review_analyzer_settings(
        cfg
    )

    summary = analyze_match_context(
        Path(args.match_dir),
        settings,
        context_summary_path=(
            Path(args.context_summary)
            if args.context_summary
            else None
        ),
    )

    print(f"[INFO] Match:       {summary['match_dir']}")
    print(f"[INFO] Analyzer:    {summary['producer_version']}")
    print(
        "[INFO] Source:      "
        f"{summary['input_context_producer_version']} "
        f"contexts={summary['context_count']}/"
        f"{summary['episode_count']}"
    )
    game = summary.get("game_context") or {}
    print(
        "[INFO] Game:        "
        f"set={game.get('set_id')} "
        f"patch={game.get('patch')}"
    )
    print(
        "[OK] Findings:     "
        f"{summary['finding_count']} "
        f"review_episodes="
        f"{summary['review_candidate_episode_count']} "
        f"decision_grades={summary['decision_grade_count']}"
    )
    print(
        "[INFO] Guards:      "
        f"infeasible_blocked="
        f"{summary['strategic_episode_blocked_infeasible_count']} "
        f"missing_context="
        f"{summary['missing_context_episode_count']} "
        f"board_eligible="
        f"{summary['board_rule_eligible_episode_count']} "
        f"board_skipped_untrusted="
        f"{summary['board_rule_skipped_untrusted_episode_count']}"
    )
    print("[INFO] Finding codes:")
    for key, value in sorted(
        summary["finding_code_counts"].items()
    ):
        print(f"  {key:<38} {value}")

    print(
        f"[OK] Findings JSONL: "
        f"{summary['findings_path']}"
    )
    print(
        f"[OK] Summary:        "
        f"{summary['summary_path']}"
    )

    if args.timeline:
        print()
        print(
            format_context_review_timeline(
                summary["findings_path"],
                limit=args.timeline_limit,
            )
        )
    return 0


def cmd_analyze_episodes(args):
    cfg = load_yaml(Path(args.config))
    settings = _build_economy_tempo_analyzer_settings(cfg)

    summary = analyze_match_episodes(
        Path(args.match_dir),
        settings,
        episode_summary_path=(
            Path(args.episode_summary)
            if args.episode_summary
            else None
        ),
    )

    print(f"[INFO] Match:       {summary['match_dir']}")
    print(f"[INFO] Analyzer:    {summary['producer_version']}")
    print(
        "[INFO] Source:      "
        f"{summary['input_episode_producer_version']} "
        f"episodes={summary['episode_count']}"
    )
    ctx = summary.get("game_context", {})
    print(
        "[INFO] Context:     "
        f"set={ctx.get('set_id')} "
        f"patch={ctx.get('patch')} "
        f"ddragon={ctx.get('data_dragon_version')}"
    )
    print(
        "[OK] Findings:     "
        f"{summary['finding_count']} "
        f"episodes={summary['episodes_with_findings_count']}/"
        f"{summary['episode_count']}"
    )
    print(
        "[INFO] Policy:      "
        f"{summary['analysis_policy']} "
        f"decision_grades={summary['decision_grade_count']}"
    )
    print(
        "[INFO] QA/review:   "
        f"hard_data_quality={summary['hard_data_quality_episode_count']} "
        f"reconstruction_uncertainty="
        f"{summary['reconstruction_uncertainty_episode_count']} "
        f"review_candidates={summary['review_candidate_episode_count']}"
    )
    print("[INFO] Finding codes:")
    for key, value in sorted(summary["finding_code_counts"].items()):
        print(f"  {key:<34} {value}")

    print(f"[OK] Findings JSONL: {summary['findings_path']}")
    print(f"[OK] Summary:        {summary['summary_path']}")

    if args.timeline:
        print()
        print(
            format_economy_tempo_findings_timeline(
                summary["findings_path"],
                limit=args.timeline_limit,
            )
        )
    return 0


def cmd_infer_actions(args):
    cfg = load_yaml(Path(args.config))
    settings = _build_action_fusion_settings(cfg)
    champion_catalog_path = _resolve_action_catalog_path(
        args,
        cfg,
    )

    match_dir = Path(args.match_dir)
    summary = infer_match_actions(
        match_dir,
        settings,
        hud_states_path=(
            Path(args.hud_states)
            if args.hud_states
            else None
        ),
        board_states_path=(
            Path(args.board_states)
            if args.board_states
            else None
        ),
        bench_states_path=(
            Path(args.bench_states)
            if args.bench_states
            else None
        ),
        champion_catalog_path=champion_catalog_path,
        explicit_set=args.set_id,
        explicit_patch=args.patch,
        config_set=cfg.get("game", {}).get("set"),
        config_patch=cfg.get("game", {}).get("patch"),
        allow_auto_set=(
            not args.no_auto_set
            and bool(
                cfg.get(
                    "game",
                    {},
                ).get(
                    "auto_infer_set",
                    True,
                )
            )
        ),
        force_game_context=bool(
            args.force_game_context
        ),
    )

    print(f"[INFO] Match:       {match_dir}")
    print(f"[INFO] Fusion:      {summary['producer_version']}")
    print(
        "[INFO] Inputs:      "
        f"hud={summary['hud_state_count']} "
        f"board={summary['board_state_count']} "
        f"bench={summary['bench_state_count']} "
        f"aligned={summary['aligned_snapshot_count']}"
    )
    print(
        "[OK] Windows:      "
        f"{summary['window_count']} "
        f"compound={summary['compound_window_count']} "
        f"long={summary['long_window_count']}"
    )
    print(f"[OK] Actions:      {summary['action_count']}")

    print("[INFO] Action types:")
    for action_type, count in sorted(
        summary["action_type_counts"].items()
    ):
        print(f"  {action_type:<22} {count}")

    print("[INFO] Quality:")
    for quality, count in sorted(
        summary["quality_counts"].items()
    ):
        print(f"  {quality:<12} {count}")

    print(
        "[INFO] Safeguards:  "
        f"auto_shop_refresh={summary['automatic_shop_refresh_candidate_count']}"
    )

    xp = summary["xp_progress"]
    print(
        "[INFO] XP progress: "
        f"base_level={xp['base_level']} "
        f"absolute={xp['absolute_snapshot_count']}/{summary['aligned_snapshot_count']} "
        f"requirements={xp['requirement_map']}"
    )

    ledger = summary["economy_ledger"]
    print(
        "[INFO] Econ ledger: "
        f"spend={ledger['observed_spend_total']} "
        f"required=[{ledger['required_action_spend_min_total']}..{ledger['required_action_spend_max_known_total']}] "
        f"compatible=[{ledger['compatible_action_spend_min_total']}..{ledger['compatible_action_spend_max_total']}] "
        f"unallocated=[{ledger['unallocated_spend_min_total']}..{ledger['unallocated_spend_max_total']}] "
        f"infeasible={ledger['infeasible_spend_window_count']} "
        f"deficit={ledger['spend_deficit_min_total']}"
    )

    game_data = summary["game_data"]
    if game_data["enabled"]:
        print(
            "[INFO] Game data:   "
            f"{game_data['provider']} "
            f"{game_data['version']} "
            f"set={game_data['set_id']} "
            f"patch={game_data['patch']} "
            f"context={game_data['context_resolution_source']} "
            f"catalog={game_data['catalog_champion_count']} "
            f"scoped={game_data['scoped_champion_count']} "
            f"buy_priced={game_data['priced_buy_champion_count']}/"
            f"{game_data['buy_champion_count']} "
            f"buy_spend={game_data['priced_buy_spend_total']}"
        )
        print(
            "[INFO] Buy cost QA: "
            + " ".join(
                f"{key}={value}"
                for key, value in sorted(
                    game_data[
                        "buy_cost_validation_counts"
                    ].items()
                )
            )
        )
        if game_data["unresolved_buy_champion_count"]:
            print(
                "[WARN] Buy pricing: "
                f"unresolved={game_data['unresolved_buy_champion_count']}"
            )
    else:
        print(
            "[WARN] Game data:   no active champion catalog; "
            "BUY_UNIT remains unpriced. Run `tft-analyzer sync-game-data`."
        )

    print(f"[OK] Actions JSONL: {summary['actions_path']}")
    print(f"[OK] Windows JSONL: {summary['windows_path']}")
    print(f"[OK] Ledger JSONL:  {summary['ledger_path']}")
    print(f"[OK] Summary:       {summary['summary_path']}")

    if args.timeline:
        print()
        print(
            format_action_timeline(
                summary["actions_path"],
                summary["windows_path"],
                summary["ledger_path"],
                limit=args.timeline_limit,
            )
        )

    return 0


def _build_shop_recognizer(args, cfg):
    perception_cfg = cfg.get("perception", {})
    shop_cfg = perception_cfg.get("shop", {})

    profile_path = Path(
        getattr(args, "profile", None)
        or "configs/layouts/tft_16_9_default.yaml"
    )
    registry = ROIRegistry.from_yaml(profile_path)

    engine_name = str(shop_cfg.get("engine", "rapidocr")).lower()
    if engine_name != "rapidocr":
        raise ValueError(
            f"Unsupported shop OCR engine {engine_name!r}; "
            "currently supported: rapidocr."
        )

    settings = ShopRecognizerSettings(
        producer_version=str(
            shop_cfg.get(
                "producer_version",
                "shop-rapidocr-0.9.1",
            )
        ),
        min_shop_presence_score=float(
            shop_cfg.get("min_shop_presence_score", 0.25)
        ),
        min_occupied_score=float(
            shop_cfg.get("min_occupied_score", 0.30)
        ),
        min_name_confidence=float(
            shop_cfg.get("min_name_confidence", 0.55)
        ),
        min_identity_confidence=float(
            shop_cfg.get("min_identity_confidence", 0.55)
        ),
        min_observation_confidence=float(
            shop_cfg.get("min_observation_confidence", 0.55)
        ),
        name_x0=float(shop_cfg.get("name_x0", 0.03)),
        name_x1=float(shop_cfg.get("name_x1", 0.72)),
        name_y0=float(shop_cfg.get("name_y0", 0.70)),
        name_y1=float(shop_cfg.get("name_y1", 0.91)),
        name_primary_upscale=int(
            shop_cfg.get("name_primary_upscale", 3)
        ),
        name_fallback_upscale=int(
            shop_cfg.get("name_fallback_upscale", 4)
        ),
        name_binary_threshold=int(
            shop_cfg.get("name_binary_threshold", 150)
        ),
        portrait_hash_size=int(
            shop_cfg.get("portrait_hash_size", 8)
        ),
    )

    lexicon_path = Path(
        shop_cfg.get(
            "identity_lexicon_path",
            "game_data/shop_identity_lexicon_v1.txt",
        )
    )
    identity_resolver = ShopIdentityResolver(
        ShopIdentityLexicon.from_file(lexicon_path),
        ShopIdentityResolverSettings(
            min_fuzzy_similarity=float(
                shop_cfg.get("identity_min_fuzzy_similarity", 0.82)
            ),
            min_fuzzy_margin=float(
                shop_cfg.get("identity_min_fuzzy_margin", 0.06)
            ),
            min_hash_support=int(
                shop_cfg.get("hash_consensus_min_support", 2)
            ),
            min_hash_ratio=float(
                shop_cfg.get("hash_consensus_min_ratio", 0.75)
            ),
            min_consensus_seed_confidence=float(
                shop_cfg.get(
                    "hash_consensus_min_seed_confidence",
                    0.70,
                )
            ),
            min_hash_identity_confidence=float(
                shop_cfg.get(
                    "hash_consensus_min_identity_confidence",
                    0.72,
                )
            ),
        ),
    )

    return ShopRecognizer(
        registry=registry,
        ocr_engine=RapidOCREngine(),
        settings=settings,
        identity_resolver=identity_resolver,
    )


def cmd_shop_debug(args):
    cfg = load_yaml(Path(args.config))
    recognizer = _build_shop_recognizer(args, cfg)

    image_path = Path(args.image)
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    output_dir = (
        Path(args.output)
        if args.output
        else Path("data/shop_debug")
        / f"{image_path.stem}_{recognizer.registry.profile.profile_id}"
    )

    debug = build_shop_debug(
        image_path,
        output_dir,
        recognizer,
    )
    result = debug["result"]

    print(f"[INFO] Image:       {image_path}")
    print(f"[INFO] Profile:     {recognizer.registry.profile.profile_id}")
    print(
        f"[INFO] Shop:        "
        f"{'PRESENT' if result.shop_present else 'ABSENT'} "
        f"score={result.shop_presence_score:.3f}"
    )

    resolved_slots = (
        {int(s["index"]): s for s in result.observations[0].value["slots"]}
        if result.observations else {}
    )
    for slot in result.slots:
        best = slot.best_name_attempt
        if not slot.occupied:
            print(
                f"  slot={slot.slot_index} EMPTY "
                f"occ={slot.occupancy_score:.3f}"
            )
            continue

        resolved = resolved_slots.get(slot.slot_index, {})
        print(
            f"  slot={slot.slot_index} OCCUPIED "
            f"occ={slot.occupancy_score:.3f} "
            f"ocr={(best.normalized_name if best else None)!r} "
            f"resolved={resolved.get('resolved_name')!r} "
            f"method={resolved.get('identity_method')} "
            f"ocr_conf={(best.confidence if best else 0.0):.3f} "
            f"id_conf={float(resolved.get('identity_confidence', 0.0)):.3f} "
            f"hash={slot.visual_hash}"
        )

    if result.observations:
        obs = result.observations[0]
        semantic = [
            slot["normalized_name"] if slot["occupied"] else None
            for slot in obs.value["slots"]
        ]
        print(
            f"[OK] Observation:  slots={semantic} "
            f"confidence={obs.confidence:.3f}"
        )
    else:
        print(
            f"[WARN] Observation: not emitted "
            f"complete={result.complete}"
        )

    print(f"[OK] Overlay:      {debug['overlay']}")
    print(f"[OK] Result:       {debug['result_path']}")
    print(f"[OK] Cards:        {debug['cards_dir']}")
    print(f"[OK] Portraits:    {debug['portraits_dir']}")
    print(f"[OK] Names:        {debug['names_dir']}")
    return 0


def cmd_perceive_shop(args):
    cfg = load_yaml(Path(args.config))
    recognizer = _build_shop_recognizer(args, cfg)

    match_dir = Path(args.match_dir)
    if not match_dir.exists():
        raise FileNotFoundError(f"Match directory not found: {match_dir}")

    summary = process_match_shop(
        match_dir,
        recognizer,
        stride=args.stride,
        limit=args.limit,
    )

    print(f"[INFO] Match:       {match_dir}")
    print(f"[INFO] Producer:    {summary['producer_version']}")
    print(f"[OK] Frames:       {summary['processed_frames']}")
    print(
        f"[INFO] Shop:        {summary['shop_present']}/"
        f"{summary['processed_frames']} "
        f"({summary['shop_presence_rate'] * 100:.1f}%)"
    )
    print(
        f"[INFO] Complete:    {summary['resolved_complete_snapshots']}/"
        f"{summary['shop_present']} "
        f"({summary['complete_rate_when_present'] * 100:.1f}%) "
        f"raw_complete={summary['raw_complete_snapshots']}"
    )
    print(
        f"[INFO] OCR tokens:  {summary['parsed_ocr_tokens']}/"
        f"{summary['occupied_slot_detections']} "
        f"({summary['ocr_parse_rate_when_occupied'] * 100:.1f}%) "
        f"mean_conf={summary['mean_ocr_confidence']:.3f}"
    )
    print(
        f"[INFO] Identity:    resolved={summary['resolved_identity_count']} "
        f"mean_conf={summary['mean_identity_confidence']:.3f} "
        f"methods={summary['identity_method_counts']}"
    )
    print(
        f"[INFO] Hash:        entries={summary['hash_consensus_entry_count']} "
        f"supported={summary['hash_supported_resolutions']} "
        f"fallback={summary['hash_fallback_resolutions']}"
    )
    print(
        f"[INFO] Corrections: {summary['fuzzy_corrections'][:10]}"
    )
    print(
        f"[INFO] Changes:     {summary['observed_snapshot_changes']}"
    )
    print(
        f"[INFO] Unique ids:  {summary['unique_resolved_names']}"
    )
    print(
        f"[INFO] Max gap:     {summary['max_observation_gap_s']:.1f}s"
    )
    print(f"[OK] JSONL:        {summary['observations_path']}")
    print(f"[OK] Attempts:     {summary['attempts_path']}")
    print(f"[OK] Identity:     {summary['identity_path']}")
    print(f"[OK] Summary:      {summary['summary_path']}")
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
                "hud-state-tracker-0.10.0",
            )
        ),
        max_age_seconds={
            "stage": float(max_age.get("stage", 45.0)),
            "gold": float(max_age.get("gold", 15.0)),
            "level": float(max_age.get("level", 45.0)),
            "xp": float(max_age.get("xp", 15.0)),
            "hp": float(max_age.get("hp", 60.0)),
            "shop": float(max_age.get("shop", 45.0)),
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
        hp_max_jump_without_confirmation=int(
            hud_cfg.get(
                "hp_max_jump_without_confirmation",
                25,
            )
        ),
        hp_single_digit_min_confidence=float(
            hud_cfg.get(
                "hp_single_digit_min_confidence",
                0.90,
            )
        ),
        shop_change_min_confidence=float(
            hud_cfg.get(
                "shop_change_min_confidence",
                0.80,
            )
        ),
    )


def cmd_track_hud(args):
    cfg = load_yaml(Path(args.config))
    settings = _build_hud_tracker_settings(cfg)

    match_dir = Path(args.match_dir)
    tracking_cfg = cfg.get("tracking", {}).get("hud", {})
    patterns = tracking_cfg.get(
        "input_observation_globs",
        [
            "hud-rapidocr-*.jsonl",
            "players-rapidocr-*.jsonl",
            "shop-rapidocr-*.jsonl",
        ],
    )
    patterns = [str(x) for x in patterns]

    explicit = (
        [Path(path) for path in args.observations]
        if args.observations
        else None
    )

    summary = track_match_hud(
        match_dir,
        settings,
        observations_paths=explicit,
        observation_globs=patterns,
    )

    print(f"[INFO] Match:        {match_dir}")
    print(f"[INFO] Tracker:      {summary['tracker_version']}")
    print("[INFO] Observations:")
    for path in summary["input_observations_paths"]:
        print(f"  {path}")
    print(f"[OK] States:         {summary['state_count']}")
    print(f"[OK] Decisions:      {summary['decision_count']}")

    print("[INFO] Decision actions:")
    for action, count in sorted(summary["decision_actions"].items()):
        print(f"  {action:<10} {count}")

    print("[INFO] Field changes/statuses:")
    for field in ("stage", "gold", "level", "xp", "hp", "shop"):
        statuses = summary["field_status_counts"].get(field, {})
        print(
            f"  {field:<6} changes={summary['field_value_changes'].get(field, 0):<4} "
            f"observed={statuses.get('observed', 0):<4} "
            f"carried={statuses.get('carried', 0):<4} "
            f"stale={statuses.get('stale', 0):<4} "
            f"unknown={statuses.get('unknown', 0):<4}"
        )

    hp_stab = summary.get("hp_stabilization", {})
    print(
        "[INFO] HP stabilization: "
        f"pending={hp_stab.get('pending_count', 0)} "
        f"rejected={hp_stab.get('rejected_count', 0)} "
        f"changes={hp_stab.get('confirmed_change_count', 0)} "
        f"large_jump_flags={hp_stab.get('large_jump_reason_count', 0)}"
    )

    shop_stab = summary.get("shop_stabilization", {})
    print(
        "[INFO] Shop tracking: "
        f"accepted={shop_stab.get('accepted_count', 0)} "
        f"refreshed={shop_stab.get('refreshed_count', 0)} "
        f"pending={shop_stab.get('pending_count', 0)} "
        f"rejected={shop_stab.get('rejected_count', 0)} "
        f"changes={shop_stab.get('confirmed_change_count', 0)}"
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
                "hud-event-detector-0.10.0",
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
    for field in ("stage", "level", "xp", "gold", "hp", "shop"):
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



def _build_hud_validator_settings(cfg):
    val_cfg = cfg.get("validation", {}).get("hud", {})

    prev = val_cfg.get("min_previous_confidence", {})
    target = val_cfg.get("min_target_confidence", {})

    return HUDEventValidatorSettings(
        producer_version=str(
            val_cfg.get(
                "producer_version",
                "hud-event-validator-0.10.0",
            )
        ),
        min_previous_confidence={
            "stage": float(prev.get("stage", 0.90)),
            "level": float(prev.get("level", 0.90)),
            "xp": float(prev.get("xp", 0.85)),
            "gold": float(prev.get("gold", 0.85)),
            "hp": float(prev.get("hp", 0.85)),
            "shop": float(prev.get("shop", 0.80)),
        },
        min_target_confidence={
            "stage": float(target.get("stage", 0.90)),
            "level": float(target.get("level", 0.90)),
            "xp": float(target.get("xp", 0.85)),
            "gold": float(target.get("gold", 0.85)),
            "hp": float(target.get("hp", 0.85)),
            "shop": float(target.get("shop", 0.80)),
        },
        timing_uncertain_after_seconds=float(
            val_cfg.get(
                "timing_uncertain_after_seconds",
                20.0,
            )
        ),
        flag_non_adjacent_stage_transition=bool(
            val_cfg.get(
                "flag_non_adjacent_stage_transition",
                True,
            )
        ),
    )


def cmd_validate_hud_events(args):
    cfg = load_yaml(Path(args.config))
    settings = _build_hud_validator_settings(cfg)

    match_dir = Path(args.match_dir)
    val_cfg = cfg.get("validation", {}).get("hud", {})

    summary = validate_match_hud_events(
        match_dir,
        settings,
        events_path=Path(args.events) if args.events else None,
        states_path=Path(args.states) if args.states else None,
        events_glob=str(
            val_cfg.get(
                "input_events_glob",
                "hud-event-detector-*.jsonl",
            )
        ),
        states_glob=str(
            val_cfg.get(
                "input_states_glob",
                "hud-state-tracker-*.jsonl",
            )
        ),
    )

    print(f"[INFO] Match:       {match_dir}")
    print(f"[INFO] Validator:   {summary['validator_version']}")
    print(f"[INFO] Events:      {summary['input_events_path']}")
    print(f"[INFO] States:      {summary['input_states_path']}")
    print(f"[OK] Validations:  {summary['validation_count']}")

    print("[INFO] Quality:")
    for quality, count in sorted(summary["quality_counts"].items()):
        print(f"  {quality:<18} {count}")

    print("[INFO] Apply recommendations:")
    for field in ("stage", "level", "xp", "gold", "hp", "shop"):
        counts = summary["field_apply_recommendations"][field]
        print(
            f"  {field:<6} "
            f"apply={counts['apply']:<4} "
            f"skip={counts['skip']:<4}"
        )

    print(f"[OK] JSONL:         {summary['validations_path']}")
    print(f"[OK] Summary:       {summary['summary_path']}")

    if args.timeline:
        print()
        print(
            format_validation_timeline(
                summary["input_events_path"],
                summary["validations_path"],
                limit=args.timeline_limit,
            )
        )

    return 0


def _build_hud_reducer_settings(cfg):
    reducer_cfg = cfg.get("reducer", {}).get("hud", {})

    return HUDGameStateReducerSettings(
        producer_version=str(
            reducer_cfg.get(
                "producer_version",
                "hud-game-state-reducer-0.10.0",
            )
        ),
        bootstrap_from_tracked_states=bool(
            reducer_cfg.get(
                "bootstrap_from_tracked_states",
                True,
            )
        ),
    )


def cmd_reduce_game_state(args):
    cfg = load_yaml(Path(args.config))
    settings = _build_hud_reducer_settings(cfg)

    match_dir = Path(args.match_dir)
    reducer_cfg = cfg.get("reducer", {}).get("hud", {})

    summary = reduce_match_game_state(
        match_dir,
        settings,
        events_path=Path(args.events) if args.events else None,
        validations_path=(
            Path(args.validations)
            if args.validations
            else None
        ),
        tracked_states_path=(
            Path(args.tracked_states)
            if args.tracked_states
            else None
        ),
        events_glob=str(
            reducer_cfg.get(
                "input_events_glob",
                "hud-event-detector-*.jsonl",
            )
        ),
        validations_glob=str(
            reducer_cfg.get(
                "input_validations_glob",
                "hud-event-validator-*.jsonl",
            )
        ),
        tracked_states_glob=str(
            reducer_cfg.get(
                "input_states_glob",
                "hud-state-tracker-*.jsonl",
            )
        ),
    )

    print(f"[INFO] Match:        {match_dir}")
    print(f"[INFO] Reducer:      {summary['reducer_version']}")
    print(f"[INFO] Events:       {summary['input_events_path']}")
    print(f"[INFO] Validations:  {summary['input_validations_path']}")
    print(f"[INFO] Tracked:      {summary['input_tracked_states_path']}")
    print(f"[OK] Canon states:  {summary['canonical_state_count']}")
    print(f"[OK] Decisions:     {summary['decision_count']}")

    print("[INFO] Reduction actions:")
    for action, count in sorted(summary["decision_actions"].items()):
        print(f"  {action:<24} {count}")

    print(
        "[INFO] Direct provenance: "
        f"max_events/state={summary['max_direct_event_ids_per_state']} "
        f"max_sources/state={summary['max_direct_source_state_ids_per_state']}"
    )
    print(
        "[INFO] Metadata refreshes: "
        f"{summary['metadata_refresh_count']}"
    )

    print(f"[OK] States JSONL:  {summary['states_path']}")
    print(f"[OK] Decisions:     {summary['decisions_path']}")
    print(f"[OK] Summary:       {summary['summary_path']}")

    if args.timeline:
        print()
        print(
            format_game_state_timeline(
                summary["states_path"],
                limit=args.timeline_limit,
            )
        )

    return 0


def cmd_game_states(args):
    print(
        format_game_state_timeline(
            Path(args.states),
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
        "players-debug",
        help="Debug dynamic player-list self-row and HP recognition.",
    )
    p.add_argument("image", help="Captured TFT frame PNG/JPEG.")
    p.add_argument("--config", default="configs/default.yaml")
    p.add_argument(
        "--profile",
        default="configs/layouts/tft_16_9_default.yaml",
    )
    p.add_argument("--output")
    p.add_argument(
        "--self-row",
        type=int,
        choices=range(0, 8),
        help="Manual row override for geometry/OCR calibration.",
    )
    p.add_argument(
        "--player-name",
        help="Optional own Riot/game name for OCR-assisted row localization.",
    )
    p.set_defaults(func=cmd_players_debug)

    p = sub.add_parser(
        "perceive-players",
        help="Run dynamic self-player HP perception over saved evidence.",
    )
    p.add_argument("match_dir")
    p.add_argument("--config", default="configs/default.yaml")
    p.add_argument(
        "--profile",
        default="configs/layouts/tft_16_9_default.yaml",
    )
    p.add_argument("--player-name")
    p.add_argument("--stride", type=int, default=1)
    p.add_argument("--limit", type=int)
    p.set_defaults(func=cmd_perceive_players)



    p = sub.add_parser(
        "board-debug",
        help="Debug 4x7 board and 9-slot bench geometry/occupancy.",
    )
    p.add_argument("image", help="Captured TFT frame PNG/JPEG.")
    p.add_argument("--config", default="configs/default.yaml")
    p.add_argument("--profile", default="configs/layouts/tft_16_9_default.yaml")
    p.add_argument("--output")
    p.set_defaults(func=cmd_board_debug)

    p = sub.add_parser(
        "perceive-board",
        help="Run board + bench occupancy perception over saved evidence.",
    )
    p.add_argument("match_dir")
    p.add_argument("--config", default="configs/default.yaml")
    p.add_argument("--profile", default="configs/layouts/tft_16_9_default.yaml")
    p.add_argument("--stride", type=int, default=1)
    p.add_argument("--limit", type=int)
    p.set_defaults(func=cmd_perceive_board)

    p = sub.add_parser(
        "track-board",
        help="Build match-local background models and temporally stabilize board/bench occupancy.",
    )
    p.add_argument("match_dir")
    p.add_argument("--config", default="configs/default.yaml")
    p.add_argument("--attempts", help="Optional explicit board-bench occupancy attempts JSONL.")
    p.add_argument("--hud-states", help="Optional explicit tracked HUD states JSONL; otherwise auto-discovered.")
    p.add_argument("--timeline", action="store_true")
    p.add_argument("--timeline-limit", type=int)
    p.set_defaults(func=cmd_track_board)

    p = sub.add_parser(
        "board-qa",
        help="Export full-cap/plan-ok board evidence frames for visual formation QA.",
    )
    p.add_argument("match_dir")
    p.add_argument(
        "--board-states",
        help="Optional explicit board-occupancy-tracker JSONL; latest is auto-discovered.",
    )
    p.add_argument(
        "--kind",
        action="append",
        choices=("full-cap", "plan-ok", "scene-invalid"),
        help="QA frame kind to export. Repeat to combine kinds. Default: full-cap.",
    )
    p.add_argument(
        "--output",
        help="Optional output directory. Default: tracking/board-formation-qa-0.13.3",
    )
    p.add_argument(
        "--open",
        action="store_true",
        help="Open the generated local HTML gallery in the default browser.",
    )
    p.set_defaults(func=cmd_board_qa)

    p = sub.add_parser(
        "sync-game-data",
        help="Sync a versioned TFT champion-cost catalog from Riot Data Dragon.",
    )
    p.add_argument("--config", default="configs/default.yaml")
    p.add_argument(
        "--version",
        help="Data Dragon version or 'latest'. Default: configs/default.yaml.",
    )
    p.add_argument("--locale")
    p.add_argument("--root-dir")
    p.add_argument(
        "--from-file",
        help=(
            "Build the catalog from a local Riot tft-champion.json instead "
            "of downloading it. Useful for offline/proxied environments."
        ),
    )
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_sync_game_data)

    p = sub.add_parser(
        "build-episode-context",
        help=(
            "Attach evidence-aligned player-state features to DecisionEpisodes "
            "without reconstructing hidden actions."
        ),
    )
    p.add_argument("match_dir")
    p.add_argument("--config", default="configs/default.yaml")
    p.add_argument(
        "--episode-summary",
        help="Explicit decision-episode-builder summary JSON. Default: latest.",
    )
    p.add_argument("--hud-states")
    p.add_argument("--board-states")
    p.add_argument("--bench-states")
    p.add_argument("--timeline", action="store_true")
    p.add_argument("--timeline-limit", type=int, default=120)
    p.set_defaults(func=cmd_build_episode_context)

    p = sub.add_parser(
        "label-identities",
        help=(
            "Open a local browser-based categorical labeler for an existing "
            "identity label package. Champion buttons come from the pinned "
            "current-set catalog and selections are saved directly to labels.csv."
        ),
    )
    p.add_argument("match_dir")
    p.add_argument("--config", default="configs/default.yaml")
    p.add_argument(
        "--label-package-dir",
        help=(
            "Explicit slot-identity-label-package directory. "
            "Default: latest."
        ),
    )
    p.add_argument(
        "--game-data-catalog",
        help=(
            "Explicit pinned Data Dragon champion catalog. "
            "Default: active configured catalog/package catalog."
        ),
    )
    p.add_argument("--host")
    p.add_argument("--port", type=int)
    p.add_argument(
        "--annotator",
        help="Default annotator name written on new labels.",
    )
    p.add_argument(
        "--no-browser",
        action="store_true",
        help="Start the local server without opening a browser automatically.",
    )
    p.set_defaults(func=cmd_label_identities)

    p = sub.add_parser(
        "prepare-identity-labeling",
        help=(
            "Build a self-contained labeling package from curated slot visual "
            "groups, including representative images, editable labels.csv, "
            "pinned-set champion schema and an external-UI/CVAT image map."
        ),
    )
    p.add_argument("match_dir")
    p.add_argument("--config", default="configs/default.yaml")
    p.add_argument(
        "--curation-dir",
        help="Explicit slot-identity-curator directory. Default: latest.",
    )
    p.add_argument(
        "--game-data-catalog",
        help=(
            "Explicit pinned Data Dragon champion catalog. "
            "Default: active configured catalog."
        ),
    )
    p.add_argument(
        "--output-dir",
        help=(
            "Optional package directory. Default: "
            "<match>/labeling/slot-identity-label-package-0.21.3."
        ),
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing labeling package.",
    )
    p.set_defaults(func=cmd_prepare_identity_labeling)

    p = sub.add_parser(
        "import-identity-labels",
        help=(
            "Validate labels.csv against curated visual groups and the pinned "
            "TFT set catalog, then write canonical labeled JSONL and downstream "
            "training/negative manifests."
        ),
    )
    p.add_argument("match_dir")
    p.add_argument("--config", default="configs/default.yaml")
    p.add_argument(
        "--label-package-dir",
        help="Explicit label package directory. Default: latest.",
    )
    p.add_argument(
        "--labels",
        help="Explicit edited labels CSV. Default: <package>/labels.csv.",
    )
    p.add_argument(
        "--curation-dir",
        help=(
            "Explicit slot-identity-curator directory. "
            "Default: package source."
        ),
    )
    p.add_argument(
        "--game-data-catalog",
        help=(
            "Explicit pinned Data Dragon champion catalog. "
            "Default: active configured catalog."
        ),
    )
    p.add_argument(
        "--output-dir",
        help=(
            "Optional import output. Default: "
            "<match>/labels/slot-identity-label-importer-0.21.3."
        ),
    )
    p.add_argument(
        "--require-complete",
        action="store_true",
        help="Reject import if any curated visual group remains unlabeled.",
    )
    p.add_argument(
        "--require-complete-queue",
        choices=[
            "identity_label",
            "occupancy_qa",
        ],
        help=(
            "Reject import only if the selected curation queue still has "
            "unlabeled groups. May be used without --require-complete."
        ),
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing imported-label artifact.",
    )
    p.set_defaults(func=cmd_import_identity_labels)

    p = sub.add_parser(
        "audit-identity-labels",
        help=(
            "Audit imported human identity labels, separate primary/secondary "
            "visual champion evidence and report occupancy false-positive "
            "hotspots without changing human labels or perception."
        ),
    )
    p.add_argument("match_dir")
    p.add_argument("--config", default="configs/default.yaml")
    p.add_argument(
        "--label-import-dir",
        help=(
            "Explicit slot-identity-label-importer directory. "
            "Default: latest."
        ),
    )
    p.add_argument(
        "--output-dir",
        help=(
            "Optional audit directory. Default: "
            "<match>/audits/slot-identity-human-label-audit-0.21.7."
        ),
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing human-label audit artifact.",
    )
    p.set_defaults(func=cmd_audit_identity_labels)

    p = sub.add_parser(
        "curate-slot-identity-dataset",
        help=(
            "Curate a 0.21.1 slot-identity observation pool into temporal "
            "near-duplicate visual groups, identity-label representatives and "
            "occupancy/hard-negative QA representatives."
        ),
    )
    p.add_argument("match_dir")
    p.add_argument("--config", default="configs/default.yaml")
    p.add_argument(
        "--source-dataset-dir",
        help=(
            "Explicit slot-identity-dataset-exporter directory. "
            "Default: latest."
        ),
    )
    p.add_argument(
        "--output-dir",
        help=(
            "Optional curation directory. Default: "
            "<match>/datasets/slot-identity-curator-0.21.2."
        ),
    )
    p.add_argument(
        "--max-gap-seconds",
        type=float,
        help="Override temporal near-duplicate gap.",
    )
    p.add_argument(
        "--max-dhash-distance",
        type=int,
        help="Override 64-bit dHash Hamming-distance threshold.",
    )
    p.add_argument(
        "--allow-stage-crossing",
        action="store_true",
        help="Allow a visual group to cross stage boundaries.",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing curation directory.",
    )
    p.add_argument("--timeline", action="store_true")
    p.add_argument("--timeline-limit", type=int, default=80)
    p.add_argument(
        "--queue",
        choices=[
            "all",
            "identity_label",
            "occupancy_qa",
        ],
        default="all",
    )
    p.set_defaults(func=cmd_curate_slot_identity_dataset)

    p = sub.add_parser(
        "export-slot-identity-dataset",
        help=(
            "Export calibrated board/bench context crops plus occupancy, "
            "scene/tracker provenance and non-exhaustive acquisition priors "
            "for future champion identity labeling/modeling."
        ),
    )
    p.add_argument("match_dir")
    p.add_argument("--config", default="configs/default.yaml")
    p.add_argument(
        "--board-tracker-summary",
        help=(
            "Explicit board-bench-occupancy-tracker summary JSON. "
            "Default: latest."
        ),
    )
    p.add_argument(
        "--roster-summary",
        help=(
            "Explicit roster-evidence-builder summary JSON. "
            "Default: latest."
        ),
    )
    p.add_argument(
        "--output-dir",
        help=(
            "Optional dataset directory. Default: "
            "<match>/datasets/slot-identity-dataset-exporter-0.21.1."
        ),
    )
    p.add_argument(
        "--min-occupancy-confidence",
        type=float,
    )
    p.add_argument(
        "--include-uncertain",
        action="store_true",
        help="Also export raw uncertain slot crops.",
    )
    p.add_argument(
        "--include-empty",
        action="store_true",
        help="Also export raw empty slot crops for negative/QA data.",
    )
    p.add_argument(
        "--allow-scene-invalid",
        action="store_true",
        help=(
            "Allow scene-invalid frames. Off by default because these are "
            "unsafe identity training examples."
        ),
    )
    p.add_argument(
        "--board-only",
        action="store_true",
    )
    p.add_argument(
        "--bench-only",
        action="store_true",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing generated dataset directory.",
    )
    p.add_argument("--timeline", action="store_true")
    p.add_argument("--timeline-limit", type=int, default=80)
    p.set_defaults(func=cmd_export_slot_identity_dataset)

    p = sub.add_parser(
        "build-roster-evidence",
        help=(
            "Build an evidence-aware lower-bound player roster from confirmed "
            "semantic BUY/SELL actions without inventing a complete roster."
        ),
    )
    p.add_argument("match_dir")
    p.add_argument("--config", default="configs/default.yaml")
    p.add_argument(
        "--episode-summary",
        help=(
            "Explicit decision-episode-builder summary JSON. "
            "Default: latest."
        ),
    )
    p.add_argument("--timeline", action="store_true")
    p.add_argument("--timeline-limit", type=int, default=120)
    p.add_argument(
        "--changes-only",
        action="store_true",
        help=(
            "With --timeline, hide episodes with no roster/economy evidence."
        ),
    )
    p.set_defaults(func=cmd_build_roster_evidence)

    p = sub.add_parser(
        "build-review-report",
        help=(
            "Aggregate context-aware findings into one post-game review card "
            "per episode and render a Markdown review report."
        ),
    )
    p.add_argument("match_dir")
    p.add_argument("--config", default="configs/default.yaml")
    p.add_argument(
        "--context-review-summary",
        help=(
            "Explicit context-review-analyzer summary JSON. "
            "Default: latest."
        ),
    )
    p.add_argument("--timeline", action="store_true")
    p.add_argument("--timeline-limit", type=int, default=120)
    p.set_defaults(func=cmd_build_review_report)

    p = sub.add_parser(
        "analyze-context",
        help=(
            "Run context-aware post-game review over DecisionEpisodes and "
            "trusted EpisodePlayerContext features without grading decisions."
        ),
    )
    p.add_argument("match_dir")
    p.add_argument("--config", default="configs/default.yaml")
    p.add_argument(
        "--context-summary",
        help=(
            "Explicit episode-context-builder summary JSON. "
            "Default: latest."
        ),
    )
    p.add_argument("--timeline", action="store_true")
    p.add_argument("--timeline-limit", type=int, default=160)
    p.set_defaults(func=cmd_analyze_context)

    p = sub.add_parser(
        "analyze-episodes",
        help=(
            "Run conservative economy/tempo analysis over DecisionEpisodes "
            "without grading TFT meta decisions."
        ),
    )
    p.add_argument("match_dir")
    p.add_argument("--config", default="configs/default.yaml")
    p.add_argument(
        "--episode-summary",
        help="Explicit decision-episode-builder summary JSON. Default: latest.",
    )
    p.add_argument("--timeline", action="store_true")
    p.add_argument("--timeline-limit", type=int, default=160)
    p.set_defaults(func=cmd_analyze_episodes)

    p = sub.add_parser(
        "build-episodes",
        help=(
            "Group sparse semantic-action windows into bounded decision episodes "
            "without reconstructing exact click order."
        ),
    )
    p.add_argument("match_dir")
    p.add_argument("--config", default="configs/default.yaml")
    p.add_argument(
        "--action-summary",
        help="Explicit semantic-action-fusion summary JSON. Default: latest.",
    )
    p.add_argument("--timeline", action="store_true")
    p.add_argument("--timeline-limit", type=int, default=120)
    p.set_defaults(func=cmd_build_episodes)

    p = sub.add_parser(
        "infer-actions",
        help="Fuse HUD/shop/board/bench trajectories into semantic action candidates.",
    )
    p.add_argument("match_dir")
    p.add_argument("--config", default="configs/default.yaml")
    p.add_argument("--hud-states")
    p.add_argument("--board-states")
    p.add_argument("--bench-states")
    p.add_argument(
        "--set",
        dest="set_id",
        help="Explicit TFT set, e.g. TFT17. Highest-priority game context.",
    )
    p.add_argument(
        "--patch",
        help="Explicit game patch, e.g. 16.16. Must match catalog version.",
    )
    p.add_argument(
        "--force-game-context",
        action="store_true",
        help="Replace conflicting persisted game_context.json.",
    )
    p.add_argument(
        "--no-auto-set",
        action="store_true",
        help="Disable fallback set inference when no explicit/persisted set exists.",
    )
    p.add_argument(
        "--game-data-catalog",
        help="Explicit versioned champion catalog JSON.",
    )
    p.add_argument(
        "--no-game-data",
        action="store_true",
        help="Disable champion-cost pricing for this inference run.",
    )
    p.add_argument("--timeline", action="store_true")
    p.add_argument("--timeline-limit", type=int, default=120)
    p.set_defaults(func=cmd_infer_actions)

    p = sub.add_parser(
        "shop-debug",
        help="Debug five-slot shop occupancy and champion-name OCR.",
    )
    p.add_argument("image", help="Captured TFT frame PNG/JPEG.")
    p.add_argument("--config", default="configs/default.yaml")
    p.add_argument(
        "--profile",
        default="configs/layouts/tft_16_9_default.yaml",
    )
    p.add_argument("--output")
    p.set_defaults(func=cmd_shop_debug)

    p = sub.add_parser(
        "perceive-shop",
        help="Run shop snapshot perception over saved match evidence.",
    )
    p.add_argument("match_dir")
    p.add_argument("--config", default="configs/default.yaml")
    p.add_argument(
        "--profile",
        default="configs/layouts/tft_16_9_default.yaml",
    )
    p.add_argument("--stride", type=int, default=1)
    p.add_argument("--limit", type=int)
    p.set_defaults(func=cmd_perceive_shop)

    p = sub.add_parser(
        "track-hud",
        help="Fuse HUD observations into a stable temporal state timeline.",
    )
    p.add_argument("match_dir")
    p.add_argument("--config", default="configs/default.yaml")
    p.add_argument(
        "--observations",
        action="append",
        help=(
            "Explicit observation JSONL. May be repeated. "
            "Default: latest configured HUD/player streams."
        ),
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


    p = sub.add_parser(
        "validate-hud-events",
        help="Validate primitive HUD events using source tracked states.",
    )
    p.add_argument("match_dir")
    p.add_argument("--config", default="configs/default.yaml")
    p.add_argument("--events")
    p.add_argument("--states")
    p.add_argument("--timeline", action="store_true")
    p.add_argument("--timeline-limit", type=int, default=160)
    p.set_defaults(func=cmd_validate_hud_events)

    p = sub.add_parser(
        "reduce-game-state",
        help="Build canonical GameState sequence from validated HUD events.",
    )
    p.add_argument("match_dir")
    p.add_argument("--config", default="configs/default.yaml")
    p.add_argument("--events")
    p.add_argument("--validations")
    p.add_argument("--tracked-states")
    p.add_argument("--timeline", action="store_true")
    p.add_argument("--timeline-limit", type=int, default=160)
    p.set_defaults(func=cmd_reduce_game_state)

    p = sub.add_parser(
        "game-states",
        help="Print a canonical GameState JSONL timeline.",
    )
    p.add_argument("states")
    p.add_argument("--limit", type=int)
    p.set_defaults(func=cmd_game_states)

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
