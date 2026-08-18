from __future__ import annotations

from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import re
import shutil
import time


MULTIMATCH_PRODUCER_VERSION = "slot-identity-multimatch-0.22.0"

_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")
_MANIFEST_FIELDS = [
    "visual_group_id",
    "match_id",
    "split_key",
    "training_tier",
    "location",
    "slot_id",
    "representative_tier",
    "representative_tracked_source",
    "champion_label",
    "champion_id",
    "member_count",
    "image_path",
    "source_audit_dir",
    "source_curation_dir",
]
_PROTOCOL_TIERS = {
    "human_confirmed": [
        "primary",
        "secondary",
        "recovered_candidate",
    ],
    "clean": [
        "primary",
        "secondary",
    ],
}


def _version_key(path: Path) -> tuple[int, int, int, float]:
    matches = list(_VERSION_RE.finditer(path.name))
    version = (
        tuple(int(value) for value in matches[-1].groups())
        if matches
        else (0, 0, 0)
    )
    return (*version, path.stat().st_mtime)


def find_latest_identity_audit(match_dir: Path | str) -> Path:
    audits_dir = Path(match_dir) / "audits"
    candidates = [
        path
        for path in audits_dir.glob("slot-identity-human-label-audit-*")
        if path.is_dir()
        and (path / "summary.json").is_file()
        and (path / "visual_champion_human_confirmed_manifest.csv").is_file()
    ]
    if not candidates:
        raise FileNotFoundError(
            f"No completed identity audit under {audits_dir}. Run "
            "`tft-analyzer audit-identity-labels <match_dir>` first."
        )
    return max(candidates, key=_version_key)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_recorded_path(raw_path: str, *, match_dir: Path) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path.resolve()

    match_dir = match_dir.resolve()
    candidates = [Path.cwd() / path]
    if len(match_dir.parents) >= 3:
        candidates.append(match_dir.parents[2] / path)
    candidates.extend([match_dir / path, match_dir.parent / path])
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return candidates[0].resolve()


def _replace_directory_with_retry(
    source: Path,
    destination: Path,
    *,
    attempts: int = 8,
    initial_delay_s: float = 0.05,
) -> None:
    delay_s = initial_delay_s
    for attempt in range(attempts):
        try:
            source.replace(destination)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay_s)
            delay_s = min(delay_s * 2.0, 0.5)


def _read_source_rows(match_dir: Path) -> tuple[list[dict], dict]:
    audit_dir = find_latest_identity_audit(match_dir).resolve()
    audit_summary = _load_json(audit_dir / "summary.json")
    if int(audit_summary.get("source_unlabeled_group_count", -1)) != 0:
        raise ValueError(f"Identity audit is incomplete: {audit_dir}")

    import_dir = _resolve_recorded_path(
        str(audit_summary["source_label_import_dir"]),
        match_dir=match_dir,
    )
    import_summary_path = import_dir / "summary.json"
    if not import_summary_path.is_file():
        raise FileNotFoundError(import_summary_path)
    import_summary = _load_json(import_summary_path)
    curation_dir = _resolve_recorded_path(
        str(import_summary["source_curation_dir"]),
        match_dir=match_dir,
    )

    manifest_path = audit_dir / "visual_champion_human_confirmed_manifest.csv"
    with manifest_path.open("r", encoding="utf-8", newline="") as f:
        source_rows = list(csv.DictReader(f))

    match_id = match_dir.name
    rows = []
    for source in source_rows:
        if source.get("match_id") != match_id:
            raise ValueError(
                f"Manifest match_id mismatch in {manifest_path}: "
                f"{source.get('match_id')!r} != {match_id!r}"
            )
        tier = str(source.get("training_tier") or "")
        if tier not in _PROTOCOL_TIERS["human_confirmed"]:
            raise ValueError(f"Unsupported training tier {tier!r} in {manifest_path}")
        image_path = (curation_dir / str(source["representative_crop_uri"])).resolve()
        if not image_path.is_file():
            raise FileNotFoundError(image_path)
        rows.append(
            {
                "visual_group_id": source["visual_group_id"],
                "match_id": match_id,
                "split_key": source.get("split_key") or match_id,
                "training_tier": tier,
                "location": source["location"],
                "slot_id": source["slot_id"],
                "representative_tier": source["representative_tier"],
                "representative_tracked_source": source[
                    "representative_tracked_source"
                ],
                "champion_label": source["champion_label"],
                "champion_id": source["champion_id"],
                "member_count": int(source["member_count"]),
                "image_path": str(image_path),
                "source_audit_dir": str(audit_dir),
                "source_curation_dir": str(curation_dir),
            }
        )

    game = import_summary.get("game_context") or {}
    context = {
        "set_id": game.get("set_id"),
        "patch": game.get("patch"),
        "data_dragon_version": game.get("data_dragon_version"),
        "catalog_source_sha256": game.get("catalog_source_sha256"),
        "audit_dir": str(audit_dir),
        "import_dir": str(import_dir),
        "curation_dir": str(curation_dir),
    }
    return rows, context


def _classes_in_every_match(
    rows: list[dict],
    *,
    match_ids: list[str],
    tiers: list[str],
) -> list[str]:
    matches_by_class: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row["training_tier"] in tiers:
            matches_by_class[row["champion_label"]].add(row["match_id"])
    expected = set(match_ids)
    return sorted(
        champion
        for champion, present in matches_by_class.items()
        if present == expected
    )


def _protocol_summary(
    rows: list[dict],
    *,
    name: str,
    match_ids: list[str],
) -> dict:
    tiers = _PROTOCOL_TIERS[name]
    classes = _classes_in_every_match(rows, match_ids=match_ids, tiers=tiers)
    selected = [
        row
        for row in rows
        if row["training_tier"] in tiers
        and row["champion_label"] in classes
    ]
    folds = []
    for validation_match_id in match_ids:
        validation = [
            row for row in selected if row["match_id"] == validation_match_id
        ]
        training = [
            row for row in selected if row["match_id"] != validation_match_id
        ]
        folds.append(
            {
                "fold_id": f"holdout-{validation_match_id}",
                "validation_match_id": validation_match_id,
                "training_match_ids": [
                    value for value in match_ids if value != validation_match_id
                ],
                "training_group_count": len(training),
                "validation_group_count": len(validation),
                "training_class_counts": dict(
                    sorted(Counter(row["champion_label"] for row in training).items())
                ),
                "validation_class_counts": dict(
                    sorted(Counter(row["champion_label"] for row in validation).items())
                ),
            }
        )
    return {
        "name": name,
        "training_tiers": tiers,
        "class_count": len(classes),
        "classes": classes,
        "group_count": len(selected),
        "folds": folds,
    }


def build_multimatch_identity_dataset(
    match_dirs: list[Path | str],
    *,
    output_dir: Path | str = Path("data/datasets") / MULTIMATCH_PRODUCER_VERSION,
    force: bool = False,
) -> dict:
    if len(match_dirs) < 2:
        raise ValueError("At least two match directories are required")

    resolved_matches = [Path(value).resolve() for value in match_dirs]
    for match_dir in resolved_matches:
        if not match_dir.is_dir():
            raise FileNotFoundError(match_dir)
    match_ids = [path.name for path in resolved_matches]
    if len(set(match_ids)) != len(match_ids):
        raise ValueError("Duplicate match_id values are not allowed")

    rows: list[dict] = []
    source_contexts = {}
    seen_groups: set[tuple[str, str]] = set()
    for match_dir in resolved_matches:
        match_rows, context = _read_source_rows(match_dir)
        source_contexts[match_dir.name] = context
        for row in match_rows:
            key = (row["match_id"], row["visual_group_id"])
            if key in seen_groups:
                raise ValueError(f"Duplicate visual group: {key}")
            seen_groups.add(key)
            rows.append(row)

    set_ids = {value.get("set_id") for value in source_contexts.values()}
    catalog_hashes = {
        value.get("catalog_source_sha256") for value in source_contexts.values()
    }
    if len(set_ids) != 1 or None in set_ids:
        raise ValueError(f"Matches do not share one TFT set: {sorted(set_ids, key=str)}")
    if len(catalog_hashes) != 1 or None in catalog_hashes:
        raise ValueError("Matches do not share one pinned champion catalog")

    rows.sort(
        key=lambda value: (
            value["match_id"],
            value["champion_label"],
            value["visual_group_id"],
        )
    )
    protocol_summaries = {
        name: _protocol_summary(rows, name=name, match_ids=match_ids)
        for name in _PROTOCOL_TIERS
    }

    per_class = {}
    for champion in sorted({row["champion_label"] for row in rows}):
        selected = [row for row in rows if row["champion_label"] == champion]
        per_class[champion] = {
            "group_count": len(selected),
            "match_count": len({row["match_id"] for row in selected}),
            "tier_counts": dict(
                sorted(Counter(row["training_tier"] for row in selected).items())
            ),
            "match_group_counts": dict(
                sorted(Counter(row["match_id"] for row in selected).items())
            ),
        }

    output_dir = Path(output_dir).resolve()
    temp_dir = output_dir.with_name(output_dir.name + ".tmp")
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    if output_dir.exists() and not force:
        raise FileExistsError(f"Output already exists: {output_dir}; pass --force")
    temp_dir.mkdir(parents=True)

    manifest_path = temp_dir / "manifest.csv"
    with manifest_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    folds_path = temp_dir / "folds.json"
    folds_path.write_text(
        json.dumps(protocol_summaries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    classes_path = temp_dir / "classes.csv"
    with classes_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "champion_label",
                "match_count",
                "group_count",
                "primary_count",
                "secondary_count",
                "recovered_candidate_count",
            ]
        )
        for champion, value in per_class.items():
            tiers = value["tier_counts"]
            writer.writerow(
                [
                    champion,
                    value["match_count"],
                    value["group_count"],
                    tiers.get("primary", 0),
                    tiers.get("secondary", 0),
                    tiers.get("recovered_candidate", 0),
                ]
            )

    summary = {
        "schema_version": 1,
        "producer_version": MULTIMATCH_PRODUCER_VERSION,
        "match_count": len(match_ids),
        "match_ids": match_ids,
        "source_match_dirs": [str(path) for path in resolved_matches],
        "source_contexts": source_contexts,
        "set_id": next(iter(set_ids)),
        "catalog_source_sha256": next(iter(catalog_hashes)),
        "visual_group_count": len(rows),
        "champion_class_count": len(per_class),
        "tier_counts": dict(
            sorted(Counter(row["training_tier"] for row in rows).items())
        ),
        "location_counts": dict(
            sorted(Counter(row["location"] for row in rows).items())
        ),
        "per_match_group_counts": dict(
            sorted(Counter(row["match_id"] for row in rows).items())
        ),
        "per_class": per_class,
        "protocols": protocol_summaries,
        "split_policy": {
            "split_unit": "match_id",
            "leave_one_match_out": True,
            "random_crop_split_forbidden": True,
            "random_visual_group_split_across_same_match_forbidden": True,
        },
        "manifest_path": str(output_dir / "manifest.csv"),
        "folds_path": str(output_dir / "folds.json"),
        "classes_path": str(output_dir / "classes.csv"),
        "summary_path": str(output_dir / "summary.json"),
        "output_dir": str(output_dir),
    }
    (temp_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if output_dir.exists():
        shutil.rmtree(output_dir)
    _replace_directory_with_retry(temp_dir, output_dir)
    return summary
