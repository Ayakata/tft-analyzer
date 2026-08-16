from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

from tft_analyzer.storage import (
    iter_evidence_records,
    write_observations_atomic,
)

from .recognizer import ShopRecognizer


def _snapshot_signature(observation) -> tuple[str | None, ...]:
    slots = observation.value.get("slots", [])
    return tuple(
        slot.get("resolved_name") if slot.get("occupied") else None
        for slot in slots
    )


def process_match_shop(
    match_dir: Path | str,
    recognizer: ShopRecognizer,
    *,
    stride: int = 1,
    limit: int | None = None,
) -> dict[str, object]:
    """Two-pass post-game shop perception.

    Pass 1: geometry/occupancy/OCR for every evidence frame.
    Pass 2: build exact portrait-hash consensus from lexicon-resolved OCR seeds,
            then emit only complete identity-resolved snapshots.
    """
    match_dir = Path(match_dir)
    stride = max(1, int(stride))

    frame_results = []
    attempts = []

    processed_frames = 0
    shop_present = 0
    raw_complete_snapshots = 0
    occupied_detections = 0
    parsed_ocr_tokens = 0

    presence_sum = 0.0
    ocr_conf_sum = 0.0

    slot_occupied = defaultdict(int)
    slot_ocr_parsed = defaultdict(int)
    raw_tokens = Counter()
    hash_seed_samples = []

    # ----------------------------- pass 1 -----------------------------
    for index, record in enumerate(iter_evidence_records(match_dir)):
        if index % stride != 0:
            continue
        if limit is not None and processed_frames >= limit:
            break

        image_path = match_dir / record.evidence.uri
        if not image_path.exists():
            attempts.append(
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
        )

        # recognizer.recognize() may emit a single-frame lexicon observation;
        # pass 2 rebuilds final observations with match-wide hash consensus.
        result.observations.clear()

        frame_results.append((record, result))
        processed_frames += 1

        if result.shop_present:
            shop_present += 1
            presence_sum += result.shop_presence_score
        if result.complete:
            raw_complete_snapshots += 1

        for slot in result.slots:
            if not slot.occupied:
                continue
            occupied_detections += 1
            slot_occupied[slot.slot_index] += 1

            best = slot.best_name_attempt
            token = (
                best.normalized_name
                if best is not None and best.valid
                and best.confidence >= recognizer.settings.min_name_confidence
                else None
            )
            confidence = (
                float(best.confidence)
                if token is not None and best is not None
                else 0.0
            )

            if token is not None:
                parsed_ocr_tokens += 1
                slot_ocr_parsed[slot.slot_index] += 1
                ocr_conf_sum += confidence
                raw_tokens[token] += 1

            hash_seed_samples.append(
                (slot.visual_hash, token, confidence)
            )

    hash_consensus = recognizer.identity_resolver.build_hash_consensus(
        hash_seed_samples
    )

    # ----------------------------- pass 2 -----------------------------
    observations = []
    identity_complete_snapshots = 0
    accepted_snapshots = 0
    resolved_identity_count = 0
    identity_conf_sum = 0.0
    identity_methods = Counter()
    resolved_names = Counter()
    fuzzy_corrections = Counter()
    hash_fallback_resolutions = 0
    hash_supported_resolutions = 0
    unresolved_occupied = 0
    slot_resolved = defaultdict(int)

    observation_timestamps = []
    semantic_changes = 0
    previous_signature = None

    for record, result in frame_results:
        # Resolve every occupied slot for diagnostics, including frames that
        # will remain incomplete. This keeps identity quality metrics separate
        # from complete-snapshot coverage.
        resolution_by_index = {}
        for slot in result.slots:
            if not slot.occupied:
                continue

            best = slot.best_name_attempt
            token = (
                best.normalized_name
                if best is not None and best.valid
                and best.confidence >= recognizer.settings.min_name_confidence
                else None
            )
            confidence = (
                float(best.confidence)
                if token is not None and best is not None
                else 0.0
            )
            resolution = recognizer.identity_resolver.resolve(
                token,
                confidence,
                visual_hash=slot.visual_hash,
                hash_consensus=hash_consensus,
            )
            if (
                resolution is None
                or resolution.identity_confidence
                < recognizer.settings.min_identity_confidence
            ):
                unresolved_occupied += 1
                continue

            resolution_by_index[slot.slot_index] = resolution
            resolved_identity_count += 1
            slot_resolved[slot.slot_index] += 1
            identity_conf_sum += resolution.identity_confidence
            identity_methods[resolution.identity_method] += 1
            resolved_names[resolution.resolved_name] += 1

            if resolution.hash_support > 0:
                hash_supported_resolutions += 1
            if resolution.identity_method == "hash_consensus":
                hash_fallback_resolutions += 1
            if token and token != resolution.resolved_name:
                fuzzy_corrections[
                    f"{token}->{resolution.resolved_name}"
                ] += 1

        identity_complete = bool(result.slots) and all(
            (not slot.occupied)
            or slot.slot_index in resolution_by_index
            for slot in result.slots
        )
        if identity_complete:
            identity_complete_snapshots += 1

        observation = recognizer.build_observation(
            result,
            match_id=record.evidence.match_id,
            timestamp_s=record.evidence.timestamp_s,
            evidence_id=record.evidence.evidence_id,
            hash_consensus=hash_consensus,
        )

        if observation is not None:
            accepted_snapshots += 1
            observations.append(observation)
            observation_timestamps.append(float(record.evidence.timestamp_s))

            signature = _snapshot_signature(observation)
            if previous_signature is not None and signature != previous_signature:
                semantic_changes += 1
            previous_signature = signature

        payload = {
            "sequence": record.sequence,
            "evidence_id": record.evidence.evidence_id,
            "timestamp_s": record.evidence.timestamp_s,
            "reason": record.reason,
            "shop_present": result.shop_present,
            "shop_presence_score": result.shop_presence_score,
            "raw_complete": result.complete,
            "identity_complete": identity_complete,
            "accepted": observation is not None,
            "resolved_complete": observation is not None,
            "slots": [],
        }

        for slot in result.slots:
            best = slot.best_name_attempt
            resolution = resolution_by_index.get(slot.slot_index)
            payload["slots"].append(
                {
                    "slot_index": slot.slot_index,
                    "occupancy_score": slot.occupancy_score,
                    "occupied": slot.occupied,
                    "occupancy_confidence": slot.occupancy_confidence,
                    "visual_hash": slot.visual_hash,
                    "best_raw_text": best.raw_text if best else "",
                    "best_ocr_token": (
                        best.normalized_name if best and best.valid else None
                    ),
                    "best_ocr_confidence": (
                        best.confidence if best else 0.0
                    ),
                    "resolved_name": (
                        resolution.resolved_name if resolution else None
                    ),
                    "identity_method": (
                        resolution.identity_method if resolution else None
                    ),
                    "identity_confidence": (
                        resolution.identity_confidence if resolution else 0.0
                    ),
                    "identity_similarity": (
                        resolution.similarity if resolution else 0.0
                    ),
                    "identity_fuzzy_margin": (
                        resolution.fuzzy_margin if resolution else 0.0
                    ),
                    "hash_consensus_support": (
                        resolution.hash_support if resolution else 0
                    ),
                    "hash_consensus_ratio": (
                        resolution.hash_ratio if resolution else 0.0
                    ),
                    "name_attempts": [
                        {
                            "variant": a.variant,
                            "raw_text": a.raw_text,
                            "normalized_name": a.normalized_name,
                            "ocr_score": a.ocr_score,
                            "parser_confidence": a.parser_confidence,
                            "confidence": a.confidence,
                        }
                        for a in slot.name_attempts
                    ],
                }
            )
        attempts.append(payload)

    safe_version = (
        recognizer.settings.producer_version.replace("/", "_")
        .replace("\\", "_")
        .replace(" ", "_")
    )
    observations_dir = match_dir / "observations"
    observations_dir.mkdir(parents=True, exist_ok=True)

    observations_path = observations_dir / f"{safe_version}.jsonl"
    attempts_path = observations_dir / f"{safe_version}_attempts.jsonl"
    identity_path = observations_dir / f"{safe_version}_identity.json"
    summary_path = observations_dir / f"{safe_version}_summary.json"

    observation_count = write_observations_atomic(
        observations_path,
        observations,
    )

    tmp_attempts = attempts_path.with_suffix(attempts_path.suffix + ".tmp")
    with tmp_attempts.open("w", encoding="utf-8", newline="\n") as f:
        for payload in sorted(
            attempts,
            key=lambda x: (
                float(x.get("timestamp_s", 0.0)),
                int(x.get("sequence", -1)),
            ),
        ):
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    tmp_attempts.replace(attempts_path)

    identity_payload = {
        "schema_version": 1,
        "producer_version": recognizer.settings.producer_version,
        "lexicon_size": len(recognizer.identity_resolver.lexicon.names),
        "lexicon": list(recognizer.identity_resolver.lexicon.names),
        "hash_consensus_entries": [
            {
                "visual_hash": entry.visual_hash,
                "resolved_name": entry.resolved_name,
                "support": entry.support,
                "total_votes": entry.total_votes,
                "winner_ratio": entry.winner_ratio,
                "confidence": entry.confidence,
            }
            for entry in sorted(
                hash_consensus.values(),
                key=lambda x: (-x.support, x.visual_hash),
            )
        ],
        "fuzzy_corrections": fuzzy_corrections.most_common(),
    }
    tmp_identity = identity_path.with_suffix(identity_path.suffix + ".tmp")
    tmp_identity.write_text(
        json.dumps(identity_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_identity.replace(identity_path)

    summary = {
        "schema_version": 2,
        "producer_version": recognizer.settings.producer_version,
        "processed_frames": processed_frames,
        "observation_count": observation_count,
        "shop_present": shop_present,
        "shop_presence_rate": (
            shop_present / processed_frames if processed_frames else 0.0
        ),
        "mean_shop_presence_score": (
            presence_sum / shop_present if shop_present else 0.0
        ),
        "raw_complete_snapshots": raw_complete_snapshots,
        "identity_complete_snapshots": identity_complete_snapshots,
        "accepted_snapshots": accepted_snapshots,
        # Compatibility aliases retained for 0.9.1 consumers.
        "resolved_complete_snapshots": accepted_snapshots,
        "complete_snapshots": accepted_snapshots,
        "complete_rate_when_present": (
            accepted_snapshots / shop_present
            if shop_present else 0.0
        ),
        "occupied_slot_detections": occupied_detections,
        "parsed_ocr_tokens": parsed_ocr_tokens,
        "ocr_parse_rate_when_occupied": (
            parsed_ocr_tokens / occupied_detections
            if occupied_detections else 0.0
        ),
        "mean_ocr_confidence": (
            ocr_conf_sum / parsed_ocr_tokens if parsed_ocr_tokens else 0.0
        ),
        "resolved_identity_count": resolved_identity_count,
        "mean_identity_confidence": (
            identity_conf_sum / resolved_identity_count
            if resolved_identity_count else 0.0
        ),
        "identity_method_counts": dict(identity_methods),
        "unresolved_occupied_slots": unresolved_occupied,
        "hash_consensus_entry_count": len(hash_consensus),
        "hash_supported_resolutions": hash_supported_resolutions,
        "hash_fallback_resolutions": hash_fallback_resolutions,
        "slot_occupied_counts": {
            str(i): int(slot_occupied[i]) for i in range(5)
        },
        "slot_ocr_parsed_counts": {
            str(i): int(slot_ocr_parsed[i]) for i in range(5)
        },
        "slot_identity_resolved_counts": {
            str(i): int(slot_resolved[i]) for i in range(5)
        },
        "unique_raw_ocr_tokens": len(raw_tokens),
        "top_raw_ocr_tokens": raw_tokens.most_common(25),
        "unique_resolved_names": len(resolved_names),
        "top_resolved_names": resolved_names.most_common(25),
        "fuzzy_corrections": fuzzy_corrections.most_common(25),
        "observed_snapshot_changes": semantic_changes,
        "max_observation_gap_s": (
            max(
                b - a
                for a, b in zip(
                    observation_timestamps,
                    observation_timestamps[1:],
                )
            )
            if len(observation_timestamps) >= 2 else 0.0
        ),
        "stride": stride,
        "observations_path": str(observations_path),
        "attempts_path": str(attempts_path),
        "identity_path": str(identity_path),
    }

    tmp_summary = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_summary.replace(summary_path)

    summary["summary_path"] = str(summary_path)
    return summary
