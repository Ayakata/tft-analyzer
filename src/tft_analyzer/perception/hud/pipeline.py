from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from PIL import Image

from tft_analyzer.storage import (
    iter_evidence_records,
    write_observations_atomic,
)

from .recognizer import HUDRecognizer


def _attempt_to_json(attempt, *, acceptance_threshold: float) -> dict:
    parsed = attempt.parsed
    return {
        "field": attempt.field,
        "roi_name": attempt.roi_name,
        "variant": attempt.variant,
        "raw_text": attempt.raw_text,
        "ocr_score": attempt.ocr_score,
        "confidence": attempt.confidence,
        "presence_passed": attempt.presence_passed,
        "presence_score": attempt.presence_score,
        "presence_reason": attempt.presence_reason,
        "candidate_name": attempt.candidate_name,
        "candidate_box": attempt.candidate_box,
        "accepted_by_threshold": (
            attempt.valid
            and attempt.confidence >= acceptance_threshold
        ),
        "parsed": (
            {
                "value": parsed.value,
                "normalized_text": parsed.normalized_text,
                "parser_confidence": parsed.parser_confidence,
            }
            if parsed is not None
            else None
        ),
    }


def process_match_hud(
    match_dir: Path | str,
    recognizer: HUDRecognizer,
    *,
    stride: int = 1,
    limit: int | None = None,
) -> dict[str, object]:
    match_dir = Path(match_dir)
    stride = max(1, int(stride))

    observations = []
    attempts_records = []
    processed_frames = 0

    field_total = defaultdict(int)
    field_present = defaultdict(int)
    field_parsed = defaultdict(int)
    field_accepted = defaultdict(int)

    parsed_conf_sum = defaultdict(float)
    accepted_conf_sum = defaultdict(float)
    presence_score_sum = defaultdict(float)

    for index, record in enumerate(iter_evidence_records(match_dir)):
        if index % stride != 0:
            continue
        if limit is not None and processed_frames >= limit:
            break

        image_path = match_dir / record.evidence.uri
        if not image_path.exists():
            attempts_records.append(
                {
                    "sequence": record.sequence,
                    "evidence_id": record.evidence.evidence_id,
                    "timestamp_s": record.evidence.timestamp_s,
                    "error": f"missing_image:{image_path}",
                    "attempts": [],
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
        )
        observations.extend(result.observations)

        for field in ("stage", "gold", "level", "xp"):
            field_total[field] += 1
            attempts = [a for a in result.attempts if a.field == field]

            if attempts and any(a.presence_passed for a in attempts):
                field_present[field] += 1
                presence_score_sum[field] += max(
                    a.presence_score for a in attempts
                )

            best = result.best_attempt(field)
            if best is not None and best.valid:
                field_parsed[field] += 1
                parsed_conf_sum[field] += best.confidence

                if best.confidence >= recognizer.min_observation_confidence:
                    field_accepted[field] += 1
                    accepted_conf_sum[field] += best.confidence

        attempts_records.append(
            {
                "sequence": record.sequence,
                "evidence_id": record.evidence.evidence_id,
                "timestamp_s": record.evidence.timestamp_s,
                "reason": record.reason,
                "attempts": [
                    _attempt_to_json(
                        a,
                        acceptance_threshold=recognizer.min_observation_confidence,
                    )
                    for a in result.attempts
                ],
                "observations": [
                    o.model_dump(mode="json")
                    for o in result.observations
                ],
            }
        )
        processed_frames += 1

    safe_version = (
        recognizer.producer_version.replace("/", "_")
        .replace("\\", "_")
        .replace(" ", "_")
    )

    observations_dir = match_dir / "observations"
    observations_path = observations_dir / f"{safe_version}.jsonl"
    attempts_path = observations_dir / f"{safe_version}_attempts.jsonl"
    summary_path = observations_dir / f"{safe_version}_summary.json"

    observation_count = write_observations_atomic(
        observations_path, observations
    )

    observations_dir.mkdir(parents=True, exist_ok=True)
    tmp_attempts = attempts_path.with_suffix(attempts_path.suffix + ".tmp")
    with tmp_attempts.open("w", encoding="utf-8", newline="\n") as f:
        for payload in attempts_records:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    tmp_attempts.replace(attempts_path)

    fields = {}
    for field in ("stage", "gold", "level", "xp"):
        total = field_total[field]
        present = field_present[field]
        parsed = field_parsed[field]
        accepted = field_accepted[field]

        fields[field] = {
            "frames": total,
            "present": present,
            "presence_rate": (present / total) if total else 0.0,
            "mean_presence_score": (
                presence_score_sum[field] / present if present else 0.0
            ),
            "parse_valid": parsed,
            "parse_rate_all_frames": (parsed / total) if total else 0.0,
            "parse_rate_when_present": (
                parsed / present if present else 0.0
            ),
            "accepted": accepted,
            "accepted_rate_all_frames": (
                accepted / total if total else 0.0
            ),
            "accepted_rate_when_present": (
                accepted / present if present else 0.0
            ),
            "mean_parsed_confidence": (
                parsed_conf_sum[field] / parsed if parsed else 0.0
            ),
            "mean_accepted_confidence": (
                accepted_conf_sum[field] / accepted if accepted else 0.0
            ),
        }

    summary = {
        "schema_version": 3,
        "producer_version": recognizer.producer_version,
        "acceptance_threshold": recognizer.min_observation_confidence,
        "processed_frames": processed_frames,
        "observation_count": observation_count,
        "stride": stride,
        "fields": fields,
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
