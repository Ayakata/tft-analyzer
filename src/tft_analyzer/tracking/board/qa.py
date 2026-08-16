from __future__ import annotations

import html
import json
import shutil
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont

from tft_analyzer.storage import iter_evidence_records


QA_VERSION = "board-formation-qa-0.13.4"

_KIND_TO_REASON = {
    "full-cap": "full_level_snapshot",
    "plan-ok": "planning_visual_stable",
    "scene-invalid": "scene_invalid",
}


@dataclass(frozen=True, slots=True)
class QAExportItem:
    sequence: int
    timestamp_s: float
    evidence_id: str
    source_uri: str
    kind: str
    gate_reason: str
    stage: str | None
    level: int | None
    candidate_occupied_count: int
    canonical_occupied_count: int
    uncertain_count: int
    round_age_s: float | None
    strong_snapshot: bool
    canonical_rows: tuple[str, ...]
    image_path: str


def _version_key(path: Path) -> tuple[int, int, int, float]:
    import re

    matches = re.findall(r"(\d+)\.(\d+)\.(\d+)", path.name)
    version = (
        tuple(int(x) for x in matches[-1])
        if matches
        else (0, 0, 0)
    )
    return (*version, path.stat().st_mtime)


def find_latest_board_states(match_dir: Path | str) -> Path:
    tracking_dir = Path(match_dir) / "tracking"
    candidates = list(
        tracking_dir.glob("board-occupancy-tracker-*.jsonl")
    )
    if not candidates:
        raise FileNotFoundError(
            f"No tracked board states in {tracking_dir}; run track-board first."
        )
    return max(candidates, key=_version_key)


def _read_jsonl(path: Path) -> list[dict]:
    values: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                values.append(json.loads(line))
    return values


def _state_rows(state: dict) -> tuple[str, ...]:
    cells = state.get("cells", [])
    rows: list[str] = []
    for row in range(4):
        current = cells[row * 7 : (row + 1) * 7]
        rows.append(
            "".join(
                "O"
                if cell.get("status") == "occupied"
                else "."
                if cell.get("status") == "empty"
                else "?"
                for cell in current
            )
        )
    return tuple(rows)


def _kind_for_reason(reason: str) -> str | None:
    for kind, mapped_reason in _KIND_TO_REASON.items():
        if reason == mapped_reason:
            return kind
    return None


def _text_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    try:
        box = draw.textbbox((0, 0), text, font=font)
        return int(box[2] - box[0])
    except AttributeError:
        return int(draw.textlength(text, font=font))


def _annotate(
    source: Path,
    destination: Path,
    *,
    lines: list[str],
) -> None:
    with Image.open(source) as src:
        image = src.convert("RGB")

    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()

    padding = 8
    line_height = 15
    banner_height = padding * 2 + line_height * len(lines)

    # Use a plain opaque banner so screenshots remain readable on any arena.
    draw.rectangle(
        (0, 0, image.width, banner_height),
        fill=(20, 20, 20),
    )

    y = padding
    for line in lines:
        draw.text(
            (padding, y),
            line,
            fill=(245, 245, 245),
            font=font,
        )
        y += line_height

    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination)


def _build_gallery(items: list[QAExportItem], output_dir: Path) -> Path:
    sections: list[str] = []

    for item in items:
        rel = Path(item.image_path).relative_to(output_dir).as_posix()
        rows = " | ".join(item.canonical_rows)
        stage = item.stage or "?"
        level = f"L{item.level}" if item.level is not None else "L?"
        age = (
            f"{item.round_age_s:.1f}s"
            if item.round_age_s is not None
            else "?"
        )

        sections.append(
            f"""
            <article class="card">
              <h2>{html.escape(item.kind)} · {item.timestamp_s:.1f}s · {html.escape(stage)} · {level}</h2>
              <p>
                gate={html.escape(item.gate_reason)}
                · candidate={item.candidate_occupied_count}
                · canonical={item.canonical_occupied_count}
                · uncertain={item.uncertain_count}
                · round_age={age}
              </p>
              <p class="rows">{html.escape(rows)}</p>
              <a href="{html.escape(rel)}">
                <img src="{html.escape(rel)}" loading="lazy">
              </a>
            </article>
            """
        )

    gallery = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>TFT Board Formation QA</title>
<style>
body {{
  font-family: system-ui, sans-serif;
  margin: 24px;
  background: #111;
  color: #eee;
}}
h1 {{ margin-bottom: 4px; }}
.summary {{ color: #bbb; margin-bottom: 28px; }}
.card {{
  margin: 0 0 32px 0;
  padding: 16px;
  border: 1px solid #444;
  border-radius: 8px;
  background: #1b1b1b;
}}
.card h2 {{ margin-top: 0; }}
.card p {{ color: #ccc; }}
.rows {{ font-family: monospace; }}
img {{
  max-width: 100%;
  height: auto;
  display: block;
  border: 1px solid #333;
}}
</style>
</head>
<body>
<h1>TFT Board Formation QA</h1>
<p class="summary">
QA version: {QA_VERSION}<br>
Frames: {len(items)}<br>
Open the full image by clicking its preview.
</p>
{''.join(sections)}
</body>
</html>
"""
    path = output_dir / "index.html"
    path.write_text(gallery, encoding="utf-8")
    return path


def export_board_formation_qa(
    match_dir: Path | str,
    *,
    board_states_path: Path | str | None = None,
    output_dir: Path | str | None = None,
    kinds: Iterable[str] = ("full-cap",),
    open_gallery: bool = False,
) -> dict[str, object]:
    match_dir = Path(match_dir)
    board_states_path = (
        Path(board_states_path)
        if board_states_path is not None
        else find_latest_board_states(match_dir)
    )

    selected_kinds = tuple(dict.fromkeys(str(x) for x in kinds))
    invalid = [x for x in selected_kinds if x not in _KIND_TO_REASON]
    if invalid:
        raise ValueError(
            f"Unsupported QA kinds: {invalid}; "
            f"supported={sorted(_KIND_TO_REASON)}"
        )

    output_dir = (
        Path(output_dir)
        if output_dir is not None
        else match_dir / "tracking" / QA_VERSION
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    evidence_by_id = {
        record.evidence.evidence_id: record
        for record in iter_evidence_records(match_dir)
    }

    states = _read_jsonl(board_states_path)
    items: list[QAExportItem] = []
    missing_evidence: list[str] = []

    for state in states:
        reason = str(state.get("gate_reason", ""))
        kind = _kind_for_reason(reason)
        if kind is None or kind not in selected_kinds:
            continue

        evidence_id = str(state["evidence_id"])
        record = evidence_by_id.get(evidence_id)
        if record is None:
            missing_evidence.append(evidence_id)
            continue

        source = match_dir / record.evidence.uri
        if not source.exists():
            missing_evidence.append(evidence_id)
            continue

        stage = state.get("hud_stage")
        level = state.get("hud_level")
        timestamp_s = float(state["timestamp_s"])
        sequence = int(record.sequence)

        filename = (
            f"{sequence:08d}_"
            f"{timestamp_s:010.3f}_"
            f"{kind}_"
            f"{stage or 'stage-unknown'}_"
            f"L{level if level is not None else 'unknown'}.png"
        )
        destination = output_dir / kind / filename

        canonical_rows = _state_rows(state)
        lines = [
            (
                f"{kind} | t={timestamp_s:.3f}s | stage={stage or '?'} | "
                f"L{level if level is not None else '?'} | "
                f"round_age={state.get('round_age_s')!s}"
            ),
            (
                f"candidate={int(state.get('candidate_occupied_count', 0))} | "
                f"canonical={int(state.get('occupied_count', 0))} | "
                f"uncertain={int(state.get('uncertain_count', 0))} | "
                f"gate={reason}"
            ),
            "canonical: " + " | ".join(canonical_rows),
        ]

        _annotate(source, destination, lines=lines)

        items.append(
            QAExportItem(
                sequence=sequence,
                timestamp_s=timestamp_s,
                evidence_id=evidence_id,
                source_uri=record.evidence.uri,
                kind=kind,
                gate_reason=reason,
                stage=stage,
                level=int(level) if level is not None else None,
                candidate_occupied_count=int(
                    state.get("candidate_occupied_count", 0)
                ),
                canonical_occupied_count=int(
                    state.get("occupied_count", 0)
                ),
                uncertain_count=int(state.get("uncertain_count", 0)),
                round_age_s=(
                    float(state["round_age_s"])
                    if state.get("round_age_s") is not None
                    else None
                ),
                strong_snapshot=bool(state.get("strong_snapshot", False)),
                canonical_rows=canonical_rows,
                image_path=str(destination),
            )
        )

    manifest = {
        "schema_version": 1,
        "qa_version": QA_VERSION,
        "match_dir": str(match_dir),
        "board_states_path": str(board_states_path),
        "selected_kinds": list(selected_kinds),
        "exported_count": len(items),
        "missing_evidence_count": len(missing_evidence),
        "missing_evidence_ids": missing_evidence,
        "items": [
            {
                "sequence": item.sequence,
                "timestamp_s": item.timestamp_s,
                "evidence_id": item.evidence_id,
                "source_uri": item.source_uri,
                "kind": item.kind,
                "gate_reason": item.gate_reason,
                "stage": item.stage,
                "level": item.level,
                "candidate_occupied_count": item.candidate_occupied_count,
                "canonical_occupied_count": item.canonical_occupied_count,
                "uncertain_count": item.uncertain_count,
                "round_age_s": item.round_age_s,
                "strong_snapshot": item.strong_snapshot,
                "canonical_rows": list(item.canonical_rows),
                "image_path": item.image_path,
            }
            for item in items
        ],
    }

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    gallery_path = _build_gallery(items, output_dir)

    if open_gallery:
        webbrowser.open(gallery_path.resolve().as_uri())

    return {
        "qa_version": QA_VERSION,
        "board_states_path": str(board_states_path),
        "output_dir": str(output_dir),
        "manifest_path": str(manifest_path),
        "gallery_path": str(gallery_path),
        "exported_count": len(items),
        "missing_evidence_count": len(missing_evidence),
        "kind_counts": {
            kind: sum(item.kind == kind for item in items)
            for kind in selected_kinds
        },
    }
