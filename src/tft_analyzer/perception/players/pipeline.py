from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from PIL import Image

from tft_analyzer.storage import (
    iter_evidence_records,
    write_observations_atomic,
)

from .recognizer import PlayerListRecognizer


def process_match_players(
    match_dir: Path | str,
    recognizer: PlayerListRecognizer,
    *,
    stride: int = 1,
    limit: int | None = None,
    player_name: str | None = None,
) -> dict[str, object]:
    match_dir = Path(match_dir)
    stride = max(1, int(stride))

    observations = []
    debug_records = []

    processed_frames = 0
    panel_present = 0
    self_selected = 0
    hp_parsed = 0
    hp_accepted = 0

    panel_score_sum = 0.0
    self_score_sum = 0.0
    hp_conf_sum = 0.0
    primary_candidate_used = 0
    fallback_candidate_used = 0
    ambiguous_self_rows = 0
    no_name_fallback_selected = 0
    accepted_hp_timestamps = []

    method_counts = defaultdict(int)
    row_counts = defaultdict(int)

    for index, record in enumerate(iter_evidence_records(match_dir)):
        if index % stride != 0:
            continue
        if limit is not None and processed_frames >= limit:
            break

        image_path = match_dir / record.evidence.uri
        if not image_path.exists():
            debug_records.append(
                {
                    "sequence": record.sequence,
                    "evidence_id": record.evidence.evidence_id,
                    "timestamp_s": record.evidence.timestamp_s,
                    "error": f"missing_image:{image_path}",
                }
            )
            processed_frames += 1
            continue

        with Image.open(image_path) as src:
            image = src.convert("RGB")

        result = recognizer.recognize(
            image,
            match_id=record.evidence.match_id,
            timestamp_s=record.evidence.timestamp_s,
            evidence_id=record.evidence.evidence_id,
            player_name=player_name,
        )

        observations.extend(result.observations)

        if result.panel_present:
            panel_present += 1
            panel_score_sum += result.panel_score

        if result.selected_row_index is None and result.panel_present:
            ambiguous_self_rows += 1

        if result.selected_row_index is not None:
            self_selected += 1
            self_score_sum += result.self_score
            method_counts[result.self_method or "unknown"] += 1
            row_counts[result.selected_row_index] += 1
            if result.self_method == "highlight_no_name":
                no_name_fallback_selected += 1

        best = result.best_hp_attempt
        if best is not None and best.valid:
            hp_parsed += 1
            hp_conf_sum += best.confidence

        if result.observations:
            hp_accepted += 1
            accepted_hp_timestamps.append(float(record.evidence.timestamp_s))
            candidate = str(result.observations[0].value.get("ocr_candidate", ""))
            if candidate == "hp_candidate_0":
                primary_candidate_used += 1
            else:
                fallback_candidate_used += 1

        debug_records.append(
            {
                "sequence": record.sequence,
                "evidence_id": record.evidence.evidence_id,
                "timestamp_s": record.evidence.timestamp_s,
                "reason": record.reason,
                "panel_present": result.panel_present,
                "panel_score": result.panel_score,
                "selected_row_index": result.selected_row_index,
                "self_method": result.self_method,
                "self_score": result.self_score,
                "self_margin": result.self_margin,
                "rows": [
                    {
                        "row_index": row.row_index,
                        "box": row.box,
                        "highlight_score": row.highlight_score,
                        "name_presence_score": row.name_presence_score,
                        "no_name_score": row.no_name_score,
                        "name_text": row.name_text,
                        "name_ocr_score": row.name_ocr_score,
                        "name_match_score": row.name_match_score,
                        "combined_self_score": row.combined_self_score,
                    }
                    for row in result.rows
                ],
                "hp_attempts": [
                    {
                        "row_index": attempt.row_index,
                        "candidate_name": attempt.candidate_name,
                        "candidate_box": attempt.candidate_box,
                        "variant": attempt.variant,
                        "raw_text": attempt.raw_text,
                        "ocr_score": attempt.ocr_score,
                        "hp": attempt.hp,
                        "parser_confidence": attempt.parser_confidence,
                        "confidence": attempt.confidence,
                    }
                    for attempt in result.hp_attempts
                ],
                "observations": [
                    o.model_dump(mode="json")
                    for o in result.observations
                ],
            }
        )
        processed_frames += 1

    safe_version = (
        recognizer.settings.producer_version.replace("/", "_")
        .replace("\\", "_")
        .replace(" ", "_")
    )

    observations_dir = match_dir / "observations"
    observations_dir.mkdir(parents=True, exist_ok=True)

    observations_path = observations_dir / f"{safe_version}.jsonl"
    attempts_path = observations_dir / f"{safe_version}_attempts.jsonl"
    summary_path = observations_dir / f"{safe_version}_summary.json"

    observation_count = write_observations_atomic(
        observations_path,
        observations,
    )

    tmp_attempts = attempts_path.with_suffix(
        attempts_path.suffix + ".tmp"
    )
    with tmp_attempts.open("w", encoding="utf-8", newline="\n") as f:
        for payload in debug_records:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    tmp_attempts.replace(attempts_path)

    summary = {
        "schema_version": 1,
        "producer_version": recognizer.settings.producer_version,
        "processed_frames": processed_frames,
        "observation_count": observation_count,
        "panel_present": panel_present,
        "panel_presence_rate": (
            panel_present / processed_frames
            if processed_frames
            else 0.0
        ),
        "mean_panel_score": (
            panel_score_sum / panel_present
            if panel_present
            else 0.0
        ),
        "self_row_selected": self_selected,
        "self_row_selection_rate_when_panel_present": (
            self_selected / panel_present
            if panel_present
            else 0.0
        ),
        "mean_self_score": (
            self_score_sum / self_selected
            if self_selected
            else 0.0
        ),
        "selection_method_counts": dict(method_counts),
        "selected_row_counts": {
            str(k): v for k, v in sorted(row_counts.items())
        },
        "hp_parsed": hp_parsed,
        "hp_parse_rate_when_self_selected": (
            hp_parsed / self_selected
            if self_selected
            else 0.0
        ),
        "mean_hp_ocr_confidence": (
            hp_conf_sum / hp_parsed
            if hp_parsed
            else 0.0
        ),
        "hp_accepted": hp_accepted,
        "hp_accept_rate_when_self_selected": (
            hp_accepted / self_selected
            if self_selected
            else 0.0
        ),
        "primary_candidate_used": primary_candidate_used,
        "fallback_candidate_used": fallback_candidate_used,
        "primary_candidate_rate": (
            primary_candidate_used / hp_accepted
            if hp_accepted
            else 0.0
        ),
        "ambiguous_self_rows": ambiguous_self_rows,
        "no_name_fallback_selected": no_name_fallback_selected,
        "max_hp_observation_gap_s": (
            max(
                b - a
                for a, b in zip(
                    accepted_hp_timestamps,
                    accepted_hp_timestamps[1:],
                )
            )
            if len(accepted_hp_timestamps) >= 2
            else 0.0
        ),
        "stride": stride,
        "player_name_query": player_name,
        "observations_path": str(observations_path),
        "attempts_path": str(attempts_path),
    }

    tmp_summary = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_summary.replace(summary_path)

    summary["summary_path"] = str(summary_path)
    return summary
