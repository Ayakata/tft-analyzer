from __future__ import annotations

import csv
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import threading
from urllib.parse import unquote, urlparse
import webbrowser

from tft_analyzer.features.slot_identity_labeling.pipeline import (
    find_latest_identity_label_package,
)
from tft_analyzer.game_data import load_champion_cost_catalog


_EDITABLE_FIELDS = (
    "target_type",
    "champion_label",
    "label_status",
    "annotator",
    "notes",
)


@dataclass(frozen=True)
class IdentityLabelerSettings:
    producer_version: str = "slot-identity-labeler-0.21.6"
    host: str = "127.0.0.1"
    port: int = 8765
    open_browser: bool = True
    annotator: str | None = None


class IdentityLabelStore:
    def __init__(
        self,
        package_dir: Path | str,
        *,
        catalog_path: Path | str | None = None,
        default_annotator: str | None = None,
    ) -> None:
        self.package_dir = Path(package_dir).resolve()
        self.labels_path = self.package_dir / "labels.csv"
        self.schema_path = self.package_dir / "label_schema.json"
        self.package_path = self.package_dir / "package.json"

        if not self.labels_path.is_file():
            raise FileNotFoundError(self.labels_path)
        if not self.schema_path.is_file():
            raise FileNotFoundError(self.schema_path)
        if not self.package_path.is_file():
            raise FileNotFoundError(self.package_path)

        self.default_annotator = default_annotator
        self._lock = threading.Lock()
        self._undo_stack: list[tuple[str, dict[str, str]]] = []

        self._package = json.loads(
            self.package_path.read_text(encoding="utf-8")
        )
        self._schema = json.loads(
            self.schema_path.read_text(encoding="utf-8")
        )

        self._fieldnames: list[str] = []
        self._rows: list[dict[str, str]] = []
        self._row_by_id: dict[str, dict[str, str]] = {}
        self._load_rows()

        self._champion_options = self._load_champion_options(
            catalog_path=catalog_path,
        )

    @property
    def champion_options(self) -> list[dict[str, str]]:
        return list(self._champion_options)

    def _load_rows(self) -> None:
        with self.labels_path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as f:
            reader = csv.DictReader(f)
            self._fieldnames = list(reader.fieldnames or ())
            self._rows = [
                {
                    key: (value or "")
                    for key, value in row.items()
                }
                for row in reader
            ]

        required = {
            "visual_group_id",
            "image_uri",
            "queue_type",
            "location",
            "target_type",
            "champion_label",
            "label_status",
            "annotator",
            "notes",
        }
        missing = required - set(self._fieldnames)
        if missing:
            raise ValueError(
                "labels.csv is missing required columns: "
                + ", ".join(sorted(missing))
            )

        self._row_by_id = {}
        for row in self._rows:
            group_id = row["visual_group_id"].strip()
            if not group_id:
                raise ValueError("labels.csv contains empty visual_group_id")
            if group_id in self._row_by_id:
                raise ValueError(
                    f"Duplicate visual_group_id in labels.csv: {group_id}"
                )
            self._row_by_id[group_id] = row

    def _load_champion_options(
        self,
        *,
        catalog_path: Path | str | None,
    ) -> list[dict[str, str]]:
        schema_catalog = self._schema.get("champion_catalog") or {}
        set_id = schema_catalog.get("set_id")

        candidate_catalog_path = (
            Path(catalog_path)
            if catalog_path is not None
            else (
                Path(schema_catalog["catalog_path"])
                if schema_catalog.get("catalog_path")
                else None
            )
        )

        options = []
        if (
            candidate_catalog_path is not None
            and candidate_catalog_path.is_file()
            and set_id
        ):
            catalog = load_champion_cost_catalog(candidate_catalog_path)
            entries = catalog.entries_for_set(str(set_id))
            seen = set()
            for entry in sorted(
                entries,
                key=lambda item: (
                    item.name.casefold(),
                    item.champion_id,
                ),
            ):
                normalized = str(entry.normalized_name).strip()
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                options.append(
                    {
                        "value": normalized,
                        "display": entry.name,
                        "champion_id": entry.champion_id,
                    }
                )

        if options:
            return options

        labels = schema_catalog.get("champion_labels") or []
        for label in sorted(
            {
                str(value).strip()
                for value in labels
                if str(value).strip()
            }
        ):
            options.append(
                {
                    "value": label,
                    "display": label,
                    "champion_id": "",
                }
            )
        return options

    def rows_for_client(self) -> list[dict[str, object]]:
        values = []
        for row in self._rows:
            values.append(
                {
                    "visual_group_id": row["visual_group_id"],
                    "image_uri": row["image_uri"],
                    "queue_type": row["queue_type"],
                    "match_id": row.get("match_id", ""),
                    "location": row["location"],
                    "slot_id": row.get("slot_id", ""),
                    "stage_start": row.get("stage_start", ""),
                    "stage_end": row.get("stage_end", ""),
                    "start_timestamp_s": row.get("start_timestamp_s", ""),
                    "end_timestamp_s": row.get("end_timestamp_s", ""),
                    "member_count": row.get("member_count", ""),
                    "representative_tier": row.get("representative_tier", ""),
                    "representative_tracked_source": row.get(
                        "representative_tracked_source",
                        "",
                    ),
                    "recommended_for_identity_training_after_label": row.get(
                        "recommended_for_identity_training_after_label",
                        "",
                    ),
                    "target_type": row["target_type"],
                    "champion_label": row["champion_label"],
                    "label_status": row["label_status"],
                    "annotator": row["annotator"],
                    "notes": row["notes"],
                }
            )
        return values

    def progress(self) -> dict[str, object]:
        total = len(self._rows)
        labeled = sum(
            bool(row["target_type"].strip())
            for row in self._rows
        )
        by_queue = {}
        for queue in ("identity_label", "occupancy_qa"):
            queue_rows = [
                row
                for row in self._rows
                if row["queue_type"] == queue
            ]
            queue_labeled = sum(
                bool(row["target_type"].strip())
                for row in queue_rows
            )
            by_queue[queue] = {
                "total": len(queue_rows),
                "labeled": queue_labeled,
                "unlabeled": len(queue_rows) - queue_labeled,
            }

        return {
            "total": total,
            "labeled": labeled,
            "unlabeled": total - labeled,
            "by_queue": by_queue,
        }

    def _validate_label(
        self,
        *,
        target_type: str,
        champion_label: str,
    ) -> tuple[str, str]:
        target_type = target_type.strip()
        champion_label = champion_label.strip()

        allowed = {
            "champion",
            "no_unit",
            "uncertain",
            "unusable",
        }
        if target_type not in allowed:
            raise ValueError(
                f"Unsupported target_type={target_type!r}"
            )

        if target_type == "champion":
            if not champion_label:
                raise ValueError(
                    "target_type=champion requires champion_label"
                )
            known = {
                option["value"]
                for option in self._champion_options
            }
            if known and champion_label not in known:
                raise ValueError(
                    f"Unknown champion label for current set: {champion_label}"
                )
        else:
            champion_label = ""

        return target_type, champion_label

    def _editable_snapshot(
        self,
        row: dict[str, str],
    ) -> dict[str, str]:
        return {
            field: row.get(field, "")
            for field in _EDITABLE_FIELDS
        }

    def _push_undo(
        self,
        row: dict[str, str],
    ) -> None:
        self._undo_stack.append(
            (
                row["visual_group_id"],
                self._editable_snapshot(row),
            )
        )

    def undo_last(self) -> dict[str, object]:
        with self._lock:
            if not self._undo_stack:
                raise ValueError("Nothing to undo")

            visual_group_id, previous = self._undo_stack.pop()
            row = self._row_by_id.get(visual_group_id)
            if row is None:
                raise KeyError(visual_group_id)

            for field in _EDITABLE_FIELDS:
                row[field] = previous.get(field, "")

            self._atomic_write()
            return {
                "row": self._client_row(row),
                "progress": self.progress(),
                "visual_group_id": visual_group_id,
                "undo_remaining": len(self._undo_stack),
            }

    def save_label(
        self,
        *,
        visual_group_id: str,
        target_type: str,
        champion_label: str = "",
        annotator: str | None = None,
        notes: str | None = None,
    ) -> dict[str, object]:
        with self._lock:
            row = self._row_by_id.get(visual_group_id)
            if row is None:
                raise KeyError(visual_group_id)

            target_type, champion_label = self._validate_label(
                target_type=target_type,
                champion_label=champion_label,
            )

            self._push_undo(row)

            row["target_type"] = target_type
            row["champion_label"] = champion_label
            row["label_status"] = "human_labeled"
            row["annotator"] = (
                (annotator or "").strip()
                or row.get("annotator", "").strip()
                or (self.default_annotator or "")
            )
            if notes is not None:
                row["notes"] = notes.strip()

            self._atomic_write()
            return {
                "row": self._client_row(row),
                "progress": self.progress(),
            }

    def clear_label(
        self,
        *,
        visual_group_id: str,
    ) -> dict[str, object]:
        with self._lock:
            row = self._row_by_id.get(visual_group_id)
            if row is None:
                raise KeyError(visual_group_id)

            self._push_undo(row)

            for field in _EDITABLE_FIELDS:
                row[field] = ""

            self._atomic_write()
            return {
                "row": self._client_row(row),
                "progress": self.progress(),
            }

    def _client_row(
        self,
        row: dict[str, str],
    ) -> dict[str, object]:
        group_id = row["visual_group_id"]
        return next(
            value
            for value in self.rows_for_client()
            if value["visual_group_id"] == group_id
        )

    def _atomic_write(self) -> None:
        tmp = self.labels_path.with_suffix(
            self.labels_path.suffix + ".tmp"
        )
        with tmp.open(
            "w",
            encoding="utf-8",
            newline="",
        ) as f:
            writer = csv.DictWriter(
                f,
                fieldnames=self._fieldnames,
            )
            writer.writeheader()
            writer.writerows(self._rows)
        tmp.replace(self.labels_path)

    def resolve_image(
        self,
        image_uri: str,
    ) -> Path:
        candidate = (
            self.package_dir / unquote(image_uri)
        ).resolve()
        try:
            candidate.relative_to(self.package_dir)
        except ValueError as exc:
            raise PermissionError(
                "Image path escapes label package"
            ) from exc

        if not candidate.is_file():
            raise FileNotFoundError(candidate)
        return candidate


def _html_page() -> str:
    return r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TFT Identity Labeler</title>
<style>
:root {
  font-family: Inter, Segoe UI, Arial, sans-serif;
  color-scheme: dark;
  --bg: #111418;
  --panel: #1a1f26;
  --panel2: #222934;
  --text: #edf2f7;
  --muted: #a8b2c0;
  --border: #394352;
  --accent: #7aa2ff;
  --ok: #55c68a;
  --warn: #e0a85a;
  --danger: #dc6d7a;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  height: 100vh;
  overflow: hidden;
}
header {
  height: 58px;
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--panel);
}
header strong { font-size: 18px; }
.progress { color: var(--muted); }
main {
  display: grid;
  grid-template-columns: minmax(430px, 54vw) 1fr;
  height: calc(100vh - 58px);
}
.viewer {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 14px;
  border-right: 1px solid var(--border);
  overflow: hidden;
}
.image-wrap {
  position: relative;
  flex: 1 1 0;
  min-height: 0;
  display: grid;
  place-items: center;
  background: #080a0d;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}
#image {
  position: absolute;
  inset: 0;
  display: block;
  width: 100%;
  height: 100%;
  max-width: 100%;
  max-height: 100%;
  image-rendering: auto;
  object-fit: contain;
}
#image[hidden] { display: none; }
.meta {
  min-height: 82px;
  margin-top: 10px;
  display: grid;
  grid-template-columns: repeat(4, auto);
  gap: 5px 14px;
  align-content: start;
  color: var(--muted);
  font-size: 13px;
}
.meta b { color: var(--text); }
.nav {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}
.controls {
  min-width: 0;
  display: flex;
  flex-direction: column;
  padding: 12px;
  overflow: hidden;
}
.filters {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 7px;
  margin-bottom: 9px;
}
input, select, textarea, button {
  background: var(--panel2);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
}
input, select, textarea { padding: 8px; }
button {
  cursor: pointer;
  padding: 8px 10px;
}
button:hover { border-color: var(--accent); }
button.current { outline: 2px solid var(--ok); }
.specials {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 7px;
  margin-bottom: 9px;
}
.specials button[data-target="no_unit"] { border-color: #7891a8; }
.specials button[data-target="uncertain"] { border-color: var(--warn); }
.specials button[data-target="unusable"] { border-color: var(--danger); }
.champion-search {
  display: flex;
  gap: 7px;
  margin-bottom: 8px;
}
#champSearch { flex: 1; font-size: 15px; }
.champions {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(118px, 1fr));
  grid-auto-rows: min-content;
  gap: 6px;
  padding-right: 4px;
}
.champion {
  text-align: left;
  min-height: 38px;
}
.editor {
  display: grid;
  grid-template-columns: 160px 1fr;
  gap: 7px;
  margin-top: 8px;
}
#notes { resize: none; height: 52px; }
.statusbar {
  margin-top: 7px;
  color: var(--muted);
  min-height: 20px;
}
.statusbar.error { color: var(--danger); }
.empty {
  color: var(--muted);
  font-size: 18px;
}
kbd {
  border: 1px solid var(--border);
  background: #11161d;
  border-radius: 4px;
  padding: 1px 5px;
}
</style>
</head>
<body>
<header>
  <strong>TFT Identity Labeler</strong>
  <span class="progress" id="globalProgress"></span>
  <span class="progress" id="filteredProgress"></span>
  <span style="margin-left:auto;color:var(--muted)">
    <kbd>←</kbd>/<kbd>→</kbd> navigate ·
    <kbd>Ctrl+Z</kbd> undo · <kbd>N</kbd> no unit · <kbd>U</kbd> uncertain · <kbd>X</kbd> unusable
  </span>
</header>
<main>
<section class="viewer">
  <div class="image-wrap" id="imageWrap">
    <img id="image" alt="current crop">
    <div class="empty" id="empty" hidden>No samples match current filters.</div>
  </div>
  <div class="meta" id="meta"></div>
  <div class="nav">
    <button id="prev">← Previous</button>
    <button id="next">Next →</button>
    <button id="clear">Clear label</button>
    <button id="undo">↶ Undo last</button>
    <button id="openUnlabeled">Next unlabeled</button>
  </div>
</section>

<section class="controls">
  <div class="filters">
    <select id="queueFilter">
      <option value="all">All queues</option>
      <option value="identity_label" selected>Identity label</option>
      <option value="occupancy_qa">Occupancy QA</option>
    </select>
    <select id="locationFilter">
      <option value="all">Board + bench</option>
      <option value="board">Board</option>
      <option value="bench">Bench</option>
    </select>
    <select id="statusFilter">
      <option value="unlabeled" selected>Unlabeled only</option>
      <option value="labeled">Labeled only</option>
      <option value="all">All statuses</option>
    </select>
  </div>

  <div class="specials">
    <button data-target="no_unit">No unit <kbd>N</kbd></button>
    <button data-target="uncertain">Uncertain <kbd>U</kbd></button>
    <button data-target="unusable">Unusable <kbd>X</kbd></button>
    <button id="repeatLast">Repeat last label</button>
  </div>

  <div class="champion-search">
    <input id="champSearch" placeholder="Filter champions… (type, Enter selects first)">
  </div>
  <div class="champions" id="champions"></div>

  <div class="editor">
    <input id="annotator" placeholder="Annotator">
    <textarea id="notes" placeholder="Notes (optional)"></textarea>
  </div>
  <div class="statusbar" id="statusbar"></div>
</section>
</main>

<script>
const state = {
  rows: [],
  champions: [],
  progress: {},
  filtered: [],
  currentId: null,
  lastLabel: null,
};

const $ = id => document.getElementById(id);

function isLabeled(row) {
  return !!(row.target_type || "").trim();
}

function filteredRows() {
  const q = $("queueFilter").value;
  const loc = $("locationFilter").value;
  const status = $("statusFilter").value;

  return state.rows.filter(row => {
    if (q !== "all" && row.queue_type !== q) return false;
    if (loc !== "all" && row.location !== loc) return false;
    const labeled = isLabeled(row);
    if (status === "unlabeled" && labeled) return false;
    if (status === "labeled" && !labeled) return false;
    return true;
  });
}

function currentIndex() {
  return state.filtered.findIndex(row => row.visual_group_id === state.currentId);
}

function chooseCurrent(preferredId=null, fallbackIndex=0) {
  state.filtered = filteredRows();
  if (!state.filtered.length) {
    state.currentId = null;
    render();
    return;
  }
  const preferred = preferredId && state.filtered.find(
    row => row.visual_group_id === preferredId
  );
  if (preferred) {
    state.currentId = preferred.visual_group_id;
  } else {
    const index = Math.max(0, Math.min(fallbackIndex, state.filtered.length - 1));
    state.currentId = state.filtered[index].visual_group_id;
  }
  render();
}

function currentRow() {
  return state.rows.find(row => row.visual_group_id === state.currentId) || null;
}

function updateRow(updated) {
  const idx = state.rows.findIndex(
    row => row.visual_group_id === updated.visual_group_id
  );
  if (idx >= 0) state.rows[idx] = updated;
}

function render() {
  state.filtered = filteredRows();
  const row = currentRow();
  $("globalProgress").textContent =
    `${state.progress.labeled || 0}/${state.progress.total || 0} labeled`;
  $("filteredProgress").textContent =
    `· filtered ${state.filtered.length}`;

  if (!row || !state.filtered.some(x => x.visual_group_id === row.visual_group_id)) {
    if (state.filtered.length) {
      state.currentId = state.filtered[0].visual_group_id;
      return render();
    }
    $("image").hidden = true;
    $("empty").hidden = false;
    $("meta").innerHTML = "";
    return;
  }

  $("image").hidden = false;
  $("empty").hidden = true;
  $("image").src = `/image/${encodeURIComponent(row.image_uri)}`;
  $("annotator").value = row.annotator || $("annotator").value || "";
  $("notes").value = row.notes || "";

  const idx = currentIndex();
  $("meta").innerHTML = `
    <span><b>${idx + 1}/${state.filtered.length}</b></span>
    <span>queue <b>${row.queue_type}</b></span>
    <span>location <b>${row.location}</b></span>
    <span>slot <b>${row.slot_id}</b></span>
    <span>stage <b>${row.stage_start || "-"}</b></span>
    <span>tier <b>${row.representative_tier || "-"}</b></span>
    <span>tracker <b>${row.representative_tracked_source || "-"}</b></span>
    <span>members <b>${row.member_count || "-"}</b></span>
    <span>label <b>${row.target_type || "unlabeled"}</b></span>
    <span>champion <b>${row.champion_label || "-"}</b></span>
    <span style="grid-column:span 2">id <b>${row.visual_group_id}</b></span>
  `;

  document.querySelectorAll(".champion").forEach(btn => {
    btn.classList.toggle(
      "current",
      row.target_type === "champion" &&
      row.champion_label === btn.dataset.value
    );
  });
  document.querySelectorAll(".specials button[data-target]").forEach(btn => {
    btn.classList.toggle("current", row.target_type === btn.dataset.target);
  });
}

function renderChampionButtons() {
  const query = $("champSearch").value.trim().toLowerCase();
  const visible = state.champions.filter(option =>
    option.display.toLowerCase().includes(query) ||
    option.value.toLowerCase().includes(query)
  );
  $("champions").innerHTML = "";
  for (const option of visible) {
    const btn = document.createElement("button");
    btn.className = "champion";
    btn.dataset.value = option.value;
    btn.textContent = option.display;
    btn.title = option.value;
    btn.onclick = () => saveLabel("champion", option.value);
    $("champions").appendChild(btn);
  }
  render();
}

function setStatus(text, error=false) {
  $("statusbar").textContent = text;
  $("statusbar").classList.toggle("error", error);
}

async function saveLabel(targetType, championLabel="") {
  const row = currentRow();
  if (!row) return;
  const oldFiltered = filteredRows();
  const oldIndex = oldFiltered.findIndex(
    x => x.visual_group_id === row.visual_group_id
  );

  const payload = {
    visual_group_id: row.visual_group_id,
    target_type: targetType,
    champion_label: championLabel,
    annotator: $("annotator").value,
    notes: $("notes").value,
  };

  try {
    const response = await fetch("/api/label", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Save failed");

    updateRow(result.row);
    state.progress = result.progress;
    state.lastLabel = {
      target_type: targetType,
      champion_label: championLabel,
    };
    setStatus(
      targetType === "champion"
        ? `Saved: ${championLabel}`
        : `Saved: ${targetType}`
    );

    const newFiltered = filteredRows();
    if (!newFiltered.length) {
      state.currentId = null;
    } else if ($("statusFilter").value === "unlabeled") {
      const nextIndex = Math.max(0, Math.min(oldIndex, newFiltered.length - 1));
      state.currentId = newFiltered[nextIndex].visual_group_id;
    } else {
      const nextIndex = Math.min(oldIndex + 1, newFiltered.length - 1);
      state.currentId = newFiltered[nextIndex].visual_group_id;
    }
    render();
  } catch (err) {
    setStatus(err.message, true);
  }
}

async function clearLabel() {
  const row = currentRow();
  if (!row) return;
  try {
    const response = await fetch("/api/clear", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({visual_group_id: row.visual_group_id}),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Clear failed");
    updateRow(result.row);
    state.progress = result.progress;
    setStatus("Label cleared");
    chooseCurrent(row.visual_group_id, currentIndex());
  } catch (err) {
    setStatus(err.message, true);
  }
}

async function undoLast() {
  try {
    const response = await fetch("/api/undo", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: "{}",
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Undo failed");

    updateRow(result.row);
    state.progress = result.progress;

    // Undo may restore an already-filtered row to unlabeled or vice versa.
    // Show the exact reverted crop even if the current filter would hide it.
    $("statusFilter").value = "all";
    $("queueFilter").value = result.row.queue_type;
    $("locationFilter").value = "all";
    state.currentId = result.visual_group_id;
    setStatus("Last label reverted");
    render();
  } catch (err) {
    setStatus(err.message, true);
  }
}

function move(delta) {
  state.filtered = filteredRows();
  if (!state.filtered.length) return;
  let idx = currentIndex();
  if (idx < 0) idx = 0;
  idx = Math.max(0, Math.min(idx + delta, state.filtered.length - 1));
  state.currentId = state.filtered[idx].visual_group_id;
  render();
}

function nextUnlabeled() {
  const rows = state.rows.filter(row => !isLabeled(row));
  if (!rows.length) return;
  const current = currentRow();
  let idx = current
    ? rows.findIndex(row => row.visual_group_id === current.visual_group_id)
    : -1;
  const next = rows[(idx + 1 + rows.length) % rows.length];
  $("statusFilter").value = "unlabeled";
  $("queueFilter").value = "all";
  $("locationFilter").value = "all";
  state.currentId = next.visual_group_id;
  render();
}

async function init() {
  const response = await fetch("/api/state");
  const data = await response.json();
  state.rows = data.rows;
  state.champions = data.champions;
  state.progress = data.progress;
  $("annotator").value = data.default_annotator || "";
  renderChampionButtons();
  chooseCurrent(null, 0);
}

["queueFilter", "locationFilter", "statusFilter"].forEach(id => {
  $(id).addEventListener("change", () => chooseCurrent(null, 0));
});
$("champSearch").addEventListener("input", renderChampionButtons);
$("champSearch").addEventListener("keydown", event => {
  if (event.key === "Enter") {
    const first = document.querySelector(".champion");
    if (first) {
      event.preventDefault();
      first.click();
    }
  }
});
$("prev").onclick = () => move(-1);
$("next").onclick = () => move(1);
$("clear").onclick = clearLabel;
$("undo").onclick = undoLast;
$("openUnlabeled").onclick = nextUnlabeled;
$("repeatLast").onclick = () => {
  if (state.lastLabel) {
    saveLabel(state.lastLabel.target_type, state.lastLabel.champion_label);
  }
};
document.querySelectorAll(".specials button[data-target]").forEach(btn => {
  btn.onclick = () => saveLabel(btn.dataset.target, "");
});

document.addEventListener("keydown", event => {
  if (
    (event.ctrlKey || event.metaKey) &&
    event.key.toLowerCase() === "z"
  ) {
    event.preventDefault();
    undoLast();
    return;
  }

  if (
    event.target.tagName === "INPUT" ||
    event.target.tagName === "TEXTAREA" ||
    event.target.tagName === "SELECT"
  ) return;

  if (event.key === "ArrowLeft") {
    event.preventDefault();
    move(-1);
  } else if (event.key === "ArrowRight") {
    event.preventDefault();
    move(1);
  } else if (event.key.toLowerCase() === "n") {
    event.preventDefault();
    saveLabel("no_unit", "");
  } else if (event.key.toLowerCase() === "u") {
    event.preventDefault();
    saveLabel("uncertain", "");
  } else if (event.key.toLowerCase() === "x") {
    event.preventDefault();
    saveLabel("unusable", "");
  } else if (event.key === "/") {
    event.preventDefault();
    $("champSearch").focus();
  }
});

init().catch(err => setStatus(err.message, true));
</script>
</body>
</html>'''


def make_identity_labeler_handler(
    store: IdentityLabelStore,
):
    html = _html_page().encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        server_version = "TFTIdentityLabeler/0.21.6"

        def log_message(self, format, *args):
            return

        def _json(
            self,
            payload: dict[str, object],
            *,
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            body = json.dumps(
                payload,
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_response(status)
            self.send_header(
                "Content-Type",
                "application/json; charset=utf-8",
            )
            self.send_header(
                "Content-Length",
                str(len(body)),
            )
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self.send_response(HTTPStatus.OK)
                self.send_header(
                    "Content-Type",
                    "text/html; charset=utf-8",
                )
                self.send_header(
                    "Content-Length",
                    str(len(html)),
                )
                self.end_headers()
                self.wfile.write(html)
                return

            if parsed.path == "/api/state":
                self._json(
                    {
                        "producer_version": (
                            "slot-identity-labeler-0.21.6"
                        ),
                        "rows": store.rows_for_client(),
                        "champions": store.champion_options,
                        "progress": store.progress(),
                        "default_annotator": (
                            store.default_annotator or ""
                        ),
                        "package": store._package,
                    }
                )
                return

            if parsed.path.startswith("/image/"):
                image_uri = parsed.path[len("/image/"):]
                try:
                    image_path = store.resolve_image(image_uri)
                    body = image_path.read_bytes()
                except FileNotFoundError:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                except PermissionError:
                    self.send_error(HTTPStatus.FORBIDDEN)
                    return

                mime, _ = mimetypes.guess_type(image_path.name)
                self.send_response(HTTPStatus.OK)
                self.send_header(
                    "Content-Type",
                    mime or "application/octet-stream",
                )
                self.send_header(
                    "Content-Length",
                    str(len(body)),
                )
                self.send_header(
                    "Cache-Control",
                    "no-store",
                )
                self.end_headers()
                self.wfile.write(body)
                return

            self.send_error(HTTPStatus.NOT_FOUND)

        def _read_json_body(self) -> dict[str, object]:
            length = int(
                self.headers.get(
                    "Content-Length",
                    "0",
                )
            )
            body = self.rfile.read(length)
            if not body:
                return {}
            value = json.loads(
                body.decode("utf-8")
            )
            if not isinstance(value, dict):
                raise ValueError("JSON body must be an object")
            return value

        def do_POST(self):
            parsed = urlparse(self.path)
            try:
                payload = self._read_json_body()

                if parsed.path == "/api/label":
                    result = store.save_label(
                        visual_group_id=str(
                            payload.get("visual_group_id", "")
                        ),
                        target_type=str(
                            payload.get("target_type", "")
                        ),
                        champion_label=str(
                            payload.get("champion_label", "")
                        ),
                        annotator=(
                            str(payload["annotator"])
                            if payload.get("annotator") is not None
                            else None
                        ),
                        notes=(
                            str(payload["notes"])
                            if payload.get("notes") is not None
                            else None
                        ),
                    )
                    self._json(result)
                    return

                if parsed.path == "/api/undo":
                    result = store.undo_last()
                    self._json(result)
                    return

                if parsed.path == "/api/clear":
                    result = store.clear_label(
                        visual_group_id=str(
                            payload.get("visual_group_id", "")
                        )
                    )
                    self._json(result)
                    return

                self.send_error(HTTPStatus.NOT_FOUND)
            except KeyError as exc:
                self._json(
                    {
                        "error": f"Unknown visual_group_id: {exc.args[0]}"
                    },
                    status=HTTPStatus.NOT_FOUND,
                )
            except (
                ValueError,
                json.JSONDecodeError,
            ) as exc:
                self._json(
                    {
                        "error": str(exc)
                    },
                    status=HTTPStatus.BAD_REQUEST,
                )
            except Exception as exc:
                self._json(
                    {
                        "error": f"{type(exc).__name__}: {exc}"
                    },
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )

    return Handler


def create_identity_labeler_server(
    store: IdentityLabelStore,
    *,
    host: str,
    port: int,
) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(
        (host, port),
        make_identity_labeler_handler(store),
    )


def run_identity_labeler(
    match_dir: Path | str,
    settings: IdentityLabelerSettings,
    *,
    package_dir: Path | str | None = None,
    catalog_path: Path | str | None = None,
) -> None:
    match_dir = Path(match_dir)
    package_dir = (
        Path(package_dir)
        if package_dir is not None
        else find_latest_identity_label_package(
            match_dir
        )
    )

    store = IdentityLabelStore(
        package_dir,
        catalog_path=catalog_path,
        default_annotator=settings.annotator,
    )
    server = create_identity_labeler_server(
        store,
        host=settings.host,
        port=settings.port,
    )

    actual_host, actual_port = server.server_address[:2]
    url_host = (
        "127.0.0.1"
        if actual_host in {"0.0.0.0", "::"}
        else actual_host
    )
    url = f"http://{url_host}:{actual_port}/"

    progress = store.progress()
    print(f"[INFO] Labeler:     {settings.producer_version}")
    print(f"[INFO] Package:     {package_dir}")
    print(
        "[INFO] Samples:     "
        f"{progress['total']} "
        f"labeled={progress['labeled']} "
        f"unlabeled={progress['unlabeled']}"
    )
    print(
        "[INFO] Champions:   "
        f"{len(store.champion_options)}"
    )
    print(f"[OK] Open:         {url}")
    print("[INFO] Stop:        Ctrl+C")

    if settings.open_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
