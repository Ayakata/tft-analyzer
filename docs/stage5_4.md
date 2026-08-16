# Stage 5.4 — Local Identity Labeler

Current release: 0.21.6

## Goal

Remove manual filename-to-CSV lookup from Stage 5.3.

The task is categorical labeling of already curated crops, so a lightweight
local browser UI is preferable to a geometry annotation system.

## Compatibility

0.21.4 consumes the existing:

```text
slot-identity-label-package-0.21.3
```

without rebuilding it.

It directly edits that package's `labels.csv`.

The 0.21.3 importer remains the canonical validation/commit step.

## Champion buttons

The labeler resolves the active pinned Data Dragon catalog and the TFT set
stored in `label_schema.json`.

Buttons use human display names:

```text
Rek'Sai
Lissandra
Rhaast
...
```

while saving normalized canonical values:

```text
reksai
lissandra
rhaast
```

If a catalog cannot be loaded, the normalized labels already embedded in the
package schema are used as a fallback.

## UI behavior

Default filters:

```text
queue = identity_label
location = all
status = unlabeled
```

Selecting any target immediately:

```text
validates the target
writes labels.csv atomically
sets label_status=human_labeled
preserves annotator/notes
advances to the next crop
```

Special target shortcuts:

```text
N -> no_unit
U -> uncertain
X -> unusable
```

Champion search can be focused with `/`; `Enter` selects the first filtered
champion.

## Data integrity

Images are never physically moved between class directories during annotation.

The stable relation is:

```text
visual_group_id -> representative image -> categorical label
```

This avoids invalidating curation paths/provenance and permits labels to be
changed or cleared safely.

Class-directory materialization, if ever needed by a training framework, is a
downstream export concern.

## Local-only server

The default bind address is:

```text
127.0.0.1:8765
```

No external service, account or database is required.

Optional CLI controls:

```text
--label-package-dir
--game-data-catalog
--host
--port
--annotator
--no-browser
```

The server stops with `Ctrl+C`.

## Canonical commit

The UI is an editing frontend, not the final semantic artifact.

After a partial or complete session:

```text
tft-analyzer import-identity-labels <match_dir>
```

validates champion names against the pinned set and creates the canonical
`labeled_visual_groups.jsonl`.


## 0.21.5 proxy-safe regression tests

The local server contract remains unchanged from 0.21.4.

HTTP integration tests explicitly bypass workstation proxy configuration for
all `127.0.0.1` requests. This isolates the test from Hiddify, corporate proxy
settings and `HTTP_PROXY` / `HTTPS_PROXY` environment variables while keeping
normal application behavior unchanged.


## 0.21.6 undo support

Every label/clear mutation stores the previous editable row state in a
session-local undo stack.

The UI exposes:

```text
Undo last
Ctrl+Z
```

Undo restores the exact prior categorical label and metadata, writes the
restored state atomically to `labels.csv`, and navigates back to that visual
group.

The stack is not persisted across labeler restarts; durable project truth
continues to be `labels.csv` plus the canonical 0.21.3 importer output.
