# Stage 4.3 — Episode Player Context Features (0.17.0)

## Goal

Convert a semantic `DecisionEpisode` from:

```text
{ROLL} -> {XP+BUY}
observed spend = 42
```

into the same episode plus the player state in which that activity occurred.
This layer is descriptive feature extraction only. It does not grade decisions.

## Artifact

```text
<match>/features/
  episode-context-builder-0.17.1.jsonl
  episode-context-builder-0.17.1_summary.json
```

One context record is emitted per DecisionEpisode.

## Boundary contract

Primary join key is the exact evidence ID already stored by Stage 4.1:

```text
episode.state_before.evidence_id
episode.state_after.evidence_id
```

Those IDs are joined against the exact HUD, board and bench tracker artifacts
referenced by the source action summary. No nearest-timestamp substitution is
performed.

If a tracker stream is missing at one boundary, the context record remains in
the dataset and falls back only to values already accepted in the episode
boundary. Missing HP/quality fields remain null and the alignment is marked
`episode_boundary_fallback`.

## Player-state feature

Each boundary exposes:

```text
stage
HP
gold
level
XP current / required / absolute

board occupied count
board capacity (= observed level when known)
board utilization = occupied / capacity

bench occupied count
bench utilization = occupied / 9

board usable / stability / gate reason
scene valid / scene score
capacity status / strong snapshot
board and bench uncertainty counts

HUD status / confidence / age / source evidence per field
```

`xp_absolute` is reused from the accepted action/episode progression rather than
re-derived by a second independent XP model.

## Delta contract

The feature stores observed boundary deltas:

```text
HP
gold
level
absolute XP
board count
bench count
board utilization
```

These are state transitions between sparse evidence boundaries, not inferred
click-level transitions.

## Quality contract

Quality explicitly records:

```text
before/after exact evidence alignment
HP known
board/bench known
board utilization known
scene validity
board usability
economy feasibility
sparse reconstruction uncertainty
missing core fields
```

There is intentionally no synthetic aggregate "quality score" in 0.17.0. Raw
signals remain available so later analyzers can choose context-specific gates.

## Next use

This artifact is the input contract for context-aware post-game findings such
as low-HP spend/roll landmarks. Those future findings should initially remain
`review_candidate` rather than `decision_grade` until board strength, lobby and
meta context are available.
