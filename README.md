# TFT Analyzer

Trajectory-first Teamfight Tactics recorder, post-game analyzer and future ML/RL research platform.

## Status

- Stage 0: domain/contracts - complete
- Stage 1: recorder/replay - complete
- Stage 1.1: HWND/WGC capture - complete
- Stage 2.0: normalized layout / ROI contract - complete
- Stage 2.1: HUD perception - implemented\n- Stage 2.1.1: tight HUD OCR + accepted metrics - complete
- Stage 2.1.2: HUD presence + dynamic stage localization - complete
- Stage 2.1.3: presence confidence semantics cleanup - complete
- Stage 2.2: temporal fusion / HUD tracking - complete
- Stage 2.2.1: tracker stabilization - complete
- Stage 2.3: primitive HUD event detector - complete
- Stage 2.4: event validation + canonical GameState reducer - complete
- Stage 2.4.1: canonical state stabilization - complete
- Stage 3.0: dynamic player list / self HP perception - implemented
- Stage 3.0.1: player HP stabilization - complete
- Stage 3.1: shop snapshot perception MVP - implemented
- Stage 3.1.1: shop identity stabilization - complete
- Stage 3.2: temporal shop state + primitive SHOP_CHANGED - implemented

Current version: **0.21.7**

## Install/update on Windows

```powershell
python -m pip install -e ".[dev]"
pytest
```

## Recorder

```powershell
tft-analyzer windows --process-regex "League"
tft-analyzer record --handle <HWND> --backend wgc --no-fallback
```

## ROI debug

```powershell
tft-analyzer roi-debug <frame.png> --open
```

## HUD OCR debug

```powershell
tft-analyzer hud-debug <frame.png>
```

## Process a saved match

Smoke test:

```powershell
tft-analyzer perceive-hud .\data\matches\<match_id> --limit 20
```

Full saved evidence:

```powershell
tft-analyzer perceive-hud .\data\matches\<match_id>
```

See `docs/stage2_1.md`.


## 0.4.1 baseline comparison

Re-run the same first 20 saved evidence frames:

```powershell
tft-analyzer perceive-hud .\data\matches\<match_id> --limit 20
```

The console now reports both `parsed` and `accepted`.


## 0.4.2

Run the same 20-frame baseline:

```powershell
tft-analyzer perceive-hud .\data\matches\<match_id> --limit 20
```

The summary now reports `present`, `parsed`, and `accepted` separately.


## 0.4.3

Presence diagnostics are now semantically consistent:

```text
PRESENT => score 1.0
ABSENT  => score < 1.0
```

No OCR/ROI behavior changed.


## HUD temporal tracking

```powershell
tft-analyzer track-hud .\data\matches\<match_id> --timeline
```

The tracker automatically consumes the latest versioned HUD observation JSONL
and creates a stable timeline with provenance, freshness and rejection
diagnostics.


## 0.5.1 tracker stabilization

Tracked HUD values are semantic-only. Freshness defaults are now stage/level 45s and gold/xp 15s.


## Primitive HUD events

```powershell
tft-analyzer detect-hud-events `
  .\data\matches\<match_id> `
  --timeline
```

The detector consumes the latest tracked HUD states and emits versioned
`ROUND_START`, `LEVEL_CHANGED`, `XP_CHANGED`, and `GOLD_CHANGED` events.


## Event validation and canonical state

```powershell
tft-analyzer validate-hud-events .\data\matches\<match_id> --timeline

tft-analyzer reduce-game-state .\data\matches\<match_id> --timeline
```

The validator keeps primitive events immutable and attaches derived quality.
The reducer uses target-side confidence to avoid contaminating canonical state
with weak OCR values while still allowing recovery to later strong values.


## 0.7.1 canonical state stabilization

Canonical states now use parent-linked, direct provenance and field-level
confidence/freshness. Repeated observations refresh metadata without creating
new semantic states.

```powershell
tft-analyzer reduce-game-state .\data\matches\<match_id> --timeline
```


## Dynamic player HP

Stage 3.0 adds independent player-list perception:

```powershell
tft-analyzer players-debug <frame>

tft-analyzer perceive-players .\data\matches\<match_id>

tft-analyzer track-hud .\data\matches\<match_id> --timeline
```

The tracker merges the latest fixed-HUD and player observation streams, so
stable HUD OCR does not need to be rerun when player-list perception changes.


## 0.8.1 player HP stabilization

HP candidate 0 is now the calibrated primary geometry. Ambiguous self-row frames can use a lazy numeric-only/no-opponent-name OCR tie-breaker, and temporal tracking confirms large jumps, HP increases and high-confidence transitions into single-digit HP.

```powershell
tft-analyzer perceive-players .\data\matches\<match_id>
tft-analyzer track-hud .\data\matches\<match_id> --timeline
```
\n\n## Shop snapshot perception\n\n```powershell\ntft-analyzer shop-debug <frame.png>\ntft-analyzer perceive-shop .\\data\\matches\\<match_id>\n```\n\nStage 3.1 recognizes five shop slot occupancies and OCR champion-name tokens.\nThe shop stream remains independent from temporal tracking until full-match\nperception quality is accepted.\n

## 0.9.1 Shop identity stabilization

Shop OCR tokens are no longer treated as semantic identities. A replaceable
lexicon plus exact portrait-hash consensus resolves canonical shop names and
records separate OCR and identity confidence.

```powershell
tft-analyzer perceive-shop .\data\matches\<match_id>
```


## 0.10.0 temporal shop state

Existing `shop-rapidocr-0.9.1.jsonl` joins the other observation streams
automatically:

```powershell
tft-analyzer track-hud .\data\matches\<match_id> --timeline
tft-analyzer detect-hud-events .\data\matches\<match_id> --timeline
tft-analyzer validate-hud-events .\data\matches\<match_id> --timeline
tft-analyzer reduce-game-state .\data\matches\<match_id> --timeline
```

`SHOP_CHANGED` remains a primitive state-difference event. Purchase/reroll
inference is deferred to analyzer logic.


## 0.11.0 board + bench occupancy MVP

Adds a perspective 4x7 board lattice and a 9-slot bench lattice with conservative three-way occupancy (`occupied`, `empty`, `uncertain`). No champion identity is inferred yet.

```powershell
tft-analyzer board-debug .\data\matches\<match>\evidence\frames\<frame>.png
tft-analyzer perceive-board .\data\matches\<match>
```

The first acceptance target is geometry and occupancy calibration on real evidence. Board/bench observations are intentionally not added to temporal/canonical state until that calibration passes.


## 0.11.1 board/bench geometry calibration

The calibrated lattice centres from 0.11.0 are retained. Sampling windows are
now perspective-aware across the four board rows, and bench crops include more
of the champion body with less lower-HUD contamination.

Re-run the same real-frame geometry check:

```powershell
tft-analyzer board-debug `
  .\data\matches\20260812T164303Z_4c85a55ea6\evidence\frames\00000093_00000690.062_5423f282c294.png
```

Do not calibrate occupancy thresholds until the new overlay is accepted.


## 0.11.2

Bench geometry is re-calibrated from a real planning-phase frame. `board-debug` now draws a thin context crop and a stronger footprint box so slot placement is easier to inspect.

```powershell
tft-analyzer board-debug <frame.png>
```

Bench debug output now prints both context (`ctx_*`) and footprint (`fp_*`) geometry.


## 0.11.3 bench vertical anchor correction

Real debug overlays showed that the 0.11.2 horizontal bench span is correct,
but the logical slot anchor was about 48 px too low at 1920x1080.

Only the normalized bench Y coordinate changes:

```text
0.790 -> 0.745
```

Horizontal anchors, board geometry, context/footprint dimensions and occupancy
thresholds are unchanged.


## 0.11.4 native board hex calibration

Board row centers are calibrated against TFT's native cyan placement grid.
`board-debug` now draws a native six-point hex footprint for every board slot
while retaining the taller rectangular context crop for visual features.

Bench geometry and occupancy thresholds are unchanged.


## 0.12.0 footprint-first occupancy

Occupancy is measured from board hex / bench slot footprints. Context crops are retained only for future identity/debug. Raw feature vectors are now persisted for calibration.


## 0.13.0 match-local occupancy tracking

Build position-specific background models and temporally stabilize board/bench:

```powershell
tft-analyzer track-board .\data\matches\<match_id> --timeline
```

Board formation changes are gated by cross-frame stability; bench remains
independently tracked throughout the match.


## 0.13.1 HUD-aware board capacity

`track-board` now auto-discovers the latest `hud-state-tracker-*.jsonl`.

- HUD level is a hard upper bound for canonical board occupancy.
- stage changes define a conservative planning window.
- exact full-level snapshots are applied atomically.
- over-cap and outside-planning frames cannot mutate canonical board.
- bench tracking is unchanged.

Use `--hud-states PATH` only to override automatic HUD discovery.


## 0.13.2 HUD level contract fix

`TrackedHUDState.level.value` is a semantic object:

```json
{"level": 8}
```

0.13.1 incorrectly expected a scalar `8`, so HUD evidence alignment succeeded
while `level_known` stayed zero and board tracking fell back to the visual gate.

0.13.2 fixes only this normalization. Geometry, perception, background scoring,
thresholds and bench tracking are unchanged.


## 0.13.3 Board formation QA export

This is a diagnostic-only release. The 0.13.2 board/bench tracking algorithm
is unchanged.

Export all atomic full-level board snapshots:

```powershell
tft-analyzer board-qa `
  .\data\matches\<match_id> `
  --kind full-cap `
  --open
```

Export both high-value classes:

```powershell
tft-analyzer board-qa `
  .\data\matches\<match_id> `
  --kind full-cap `
  --kind plan-ok `
  --open
```

Output:

```text
tracking/board-formation-qa-0.13.3/
  full-cap/
  plan-ok/
  manifest.json
  index.html
```

Each image receives a compact header with timestamp, stage, level, round age,
candidate occupancy, canonical occupancy and gate reason.


## 0.13.4 Match-local arena scene guard

Board tracking now fits four static arena anchors from the match itself. A
candidate board frame is canonicalizable only if the arena scene is valid.

The guard intentionally avoids the lower shop/choice UI so overlays such as
`Choose One` can remain valid while full-screen special scenes are rejected.

Diagnostics:

```text
tracking/arena-scene-guard-0.13.4/
  scene_guard.json
  anchors/*_reference.png
```

QA can export rejected scenes:

```powershell
tft-analyzer board-qa `
  .\data\matches\<match_id> `
  --kind full-cap `
  --kind scene-invalid `
  --open
```


## 0.13.5 Scene-aware bench tracking

The 0.13.4 arena scene guard now protects canonical bench state as well as
canonical board state.

On `scene_invalid` frames:

- raw bench candidates are still retained in perception/diagnostics;
- canonical bench status is not changed;
- canonical source timestamp/evidence is not refreshed;
- pending temporal confirmation is neither advanced nor cleared.

This prevents full-screen choice/end scenes from falsely collapsing the bench
to `0/9`.

Board tracking, arena-scene thresholds, occupancy/background scoring and
geometry are unchanged.


## 0.14.0 Semantic action fusion MVP

Stage 4.0 begins cross-stream semantic action inference from:

```text
tracked HUD/shop
+ canonical board
+ canonical bench
```

Run:

```powershell
tft-analyzer infer-actions `
  .\data\matches\<match_id> `
  --timeline
```

The first MVP emits bounded-window action candidates:

```text
refresh_shop
buy_unit
purchase_xp
sell_unit
bench_to_board
board_to_bench
move_unit (board_reposition)
unknown_econ_action
```

Because current evidence cadence is sparse, output timestamps are windows rather
than claimed exact click times. Automatic round shop refreshes are explicitly
not classified as rerolls.


## 0.14.1 Economy ledger + absolute XP

Semantic action windows now contain an explicit economy ledger.

Fixed-price actions are allocated first:

```text
reroll
purchase_xp
```

Champion purchases remain **unpriced** until champion-cost game data is part of
the project. The remaining spend is therefore either:

```text
exact residual
```

or:

```text
upper-bound residual because recognized buys are still unpriced
```

A residual `unknown_econ_action` is emitted even when other known actions exist,
so a `-19g` window is no longer treated as fully explained by one reroll.

XP progress is reconstructed across levels from the match-local HUD
`level -> required XP` trajectory, allowing `BUY_XP[xN]` to survive level-up
boundaries.


## 0.14.2 Bounded Economy Ledger

Economy uncertainty is now represented as intervals.

```text
-19g + visible shop refresh
=> REROLL x1..9
=> recognized action spend [2..18]
=> unallocated spend [1..17]
```

```text
-35g + absolute XP +32 + recognized BUY[rhaast]
=> BUY_XP x8 = 32g exact
=> BUY[rhaast] price unknown
=> recognized action spend [32..35]
=> unallocated spend [0..3]
```

This replaces the misleading single residual from 0.14.1.


## 0.14.3 Economy action existence semantics

A non-zero upper bound in the economy ledger no longer automatically creates
`UNKNOWN_ECON_ACTION`.

```text
U[0..3]
```

means additional spend is possible but not required by the evidence. It stays
in the ledger only.

```text
U[1..17]
```

means every compatible explanation requires at least 1 gold of additional
spend, so `UNKNOWN_ECON_ACTION` is emitted.

This keeps ledger uncertainty separate from action existence.


## 0.14.4 Trusted Riot TFT game data + champion-cost ledger

Champion purchase costs are no longer inferred from the same match evidence.

Sync an explicit versioned catalog from Riot Data Dragon:

```powershell
tft-analyzer sync-game-data --version 16.16.1
```

Then normal inference automatically uses the active catalog:

```powershell
tft-analyzer infer-actions `
  .\data\matches\<match_id> `
  --timeline
```

The catalog stores Riot champion `id`, `name`, `tier`, source URL, exact
Data Dragon version, locale and SHA-256 of the downloaded source.

If duplicate active-set records share a normalized champion name, pricing is
accepted only when all candidates agree on `tier`. Conflicting tiers are
reported as ambiguous and remain unpriced.

A fully priced buy becomes an exact ledger component:

```text
BUY[rhaast]@3g
3=K[3]+U[0]
```

and combined exact actions can close larger windows:

```text
BUY_XP[x8] 32g + BUY[rhaast] 3g
35=K[35]+U[0]
```


## 0.14.5 Explicit game context + set-scoped pricing

For production analysis, the set/patch should be explicit whenever known:

```powershell
tft-analyzer infer-actions `
  .\data\matches\<match_id> `
  --set TFT17 `
  --patch 16.16 `
  --timeline
```

Resolution priority:

```text
CLI --set/--patch
> persisted match game_context.json
> config game.set/game.patch
> conservative roster-based auto inference
```

The resolved context is persisted in:

```text
<match_dir>/game_context.json
```

Champion cost lookup is then restricted to that set. A display-name collision
such as `Zoe` across TFT16/TFT17 no longer makes pricing ambiguous when the
match context is explicitly TFT17.

Priced BUY actions are validated against the complete economy window:

```text
cost_consistent  trusted price is compatible and the ledger fully closes
cost_possible    trusted price is compatible but other spend remains possible
cost_conflict    observed spend is smaller than the trusted buy cost
unpriced         no trusted set-scoped price
unobserved       gold delta unavailable
```

A `cost_conflict` lowers the BUY confidence to ambiguous but preserves the
candidate and its original pre-cost confidence in signals for diagnosis.


## 0.14.6 Economy feasibility / constraint violations

Trusted action requirements are never clamped to observed spend.

```text
observed spend = 1
TFT17 Zoe cost = 2
=> 1g ! K[2] deficit[1]
```

Infeasible windows have `feasible=false`, preserve the required action spend,
record the deficit, and intentionally have no `U[...]` interval.

The `buy?xN` timeline suffix now appears only for BUY components that still lack
an exact trusted price.


## 0.15.0 / Stage 4.1 — Sparse Decision Episodes

Stage 4.1 groups semantic-action windows into bounded decision episodes. It
explicitly does **not** reconstruct missing clicks between sparse screenshots.

```powershell
tft-analyzer build-episodes `
  .\data\matches\<match_id> `
  --timeline
```

The ordering contract is deliberately weak and auditable:

```text
window 100: {BUY, XP}      # internal order unknown
window 101: {REROLL}

=> {BUY, XP} -> {REROLL}
```

Only the order between non-overlapping source windows is retained. Actions
inside one source window are an unordered set.

Episodes are split conservatively by stage, idle gap and maximum episode span.
Stage 4.1 also avoids strategic over-interpretation: a reroll burst is not yet
called a `ROLLDOWN` or `SLOW_ROLL`. Those labels belong to later analyzers.

Output:

```text
decisions/
  decision-episode-builder-0.15.0.jsonl
  decision-episode-builder-0.15.0_summary.json
```

Each episode preserves boundary state, action groups, action/evidence IDs,
economy feasibility/uncertainty and sparse-sampling semantics for later coach,
ML and RL consumers.


## 0.16.0 Stage 4.2 — Economy & Tempo Findings

Run the first conservative post-game analyzer after building episodes:

```powershell
tft-analyzer analyze-episodes `
  .\data\matches\<match_id> `
  --timeline
```

0.16.0 deliberately does **not** grade TFT strategic decisions. Sparse screenshots
and the current state representation are not sufficient to claim that a player
"should have leveled", "rolled too much", or chose the wrong composition.

The analyzer emits three interpretations:

```text
descriptive      observed landmarks such as level+roll, XP investment,
                 roll activity, large spend, positioning-only episodes

data_quality     infeasible economy or spend that is necessarily unexplained

review_candidate high-value places to review later when board strength, HP,
                 streak and lobby/meta context are available
```

The output is a versioned `Finding` JSONL under `<match>/analysis/` with direct
DecisionEpisode and evidence provenance. No exact click order is reconstructed.


## 0.16.1 Finding semantics cleanup

Stage 4.2 now distinguishes **hard evidence contradictions** from the normal
uncertainty created by sparse screenshots.

```text
data_quality
  economy_infeasible

reconstruction_uncertainty
  unresolved_economy_spend
  bounded_economy_uncertainty

descriptive
  level_up
  level_and_roll
  xp_investment_without_level
  roll_activity
  roll_burst_candidate
  large_spend
  positioning_only

review_candidate
  large_spend_low_gold_review
```

A transition such as:

```text
observed spend = 16g
known semantic spend = 0g
```

is no longer reported as bad data. With sparse capture it simply means that
16g of activity was not reconstructed into named actions:

```text
unresolved_economy_spend
interpretation = reconstruction_uncertainty
severity = info
```

A true contradiction remains a hard QA signal:

```text
observed spend = 1g
trusted BUY Zoe = 2g
=> economy_infeasible
interpretation = data_quality
severity = major
```

The analysis summary now reports the lanes separately:

```text
hard_data_quality_episode_count
reconstruction_uncertainty_episode_count
review_candidate_episode_count
decision_grade_count
```

`data_quality_episode_count` is retained for compatibility, but from 0.16.1 it
means hard data-quality contradictions only.


## 0.17.0 Episode Player Context Features

Stage 4.3 attaches evidence-aligned player state to every accepted
`DecisionEpisode` without reconstructing hidden actions.

```powershell
tft-analyzer build-episode-context `
  .\data\matches\<match_id> `
  --timeline
```

The feature layer resolves the exact HUD/board/bench tracking artifacts used by
the source semantic-action run and joins episode boundaries by `evidence_id`.
The resulting feature contains before/after:

```text
stage, HP, gold, level
current/required/absolute XP
board count / level capacity / utilization
bench count / utilization
board scene validity / usability / stability
raw HUD tracked-field status/confidence/age
```

It also exports deltas and context-quality flags. Sparse economy uncertainty and
hard infeasibility are propagated as quality metadata, not converted into
player grades.

If one tracker boundary cannot be resolved, the already accepted Stage 4.1
boundary is preserved as an explicit `episode_boundary_fallback`; HP remains
unknown rather than being invented.


## 0.17.1 Context feature trust semantics

Exact evidence alignment and literal strategic trust are now separate.

Every episode context contains `feature_trust.before` and
`feature_trust.after` for HP, gold, level, absolute XP, board count, board
utilization and bench count.

Trust semantics:

```text
exact
lower_bound
carried
unusable
unknown
```

HUD features remain strategically usable when present. Board count/utilization
are strategically usable only for a strong, usable board snapshot. Otherwise
the conservative canonical board state is treated as a confirmed lower bound
or carried value rather than a literal exact unit count.

Thus:

```text
board_count=4
capacity=7
```

does not imply three genuinely empty strategic slots unless the boundary is
certified exact.

Scene-invalid board boundaries are unusable for literal strategy even when the
same `evidence_id` is aligned exactly.

The context contract also states:

```text
boundary_gold_delta_semantics =
  observed_state_delta_not_action_accounting

economy_source_for_action_spend =
  episode_economy
```

so natural income between sparse screenshots cannot be confused with action
costs.


## 0.18.0 Context-aware review analyzer

Stage 4.4 introduces the first analyzer that combines semantic
`DecisionEpisode` activity with trusted `EpisodePlayerContext` features.

Run:

```text
tft-analyzer analyze-context <match_dir> --timeline
```

The analyzer emits `review_candidate`, not `decision_grade`.

Initial review landmarks include:

```text
economy_commitment_under_pressure
large_spend_under_pressure
low_hp_roll_activity
low_hp_level_up
high_gold_under_pressure
near_elimination_activity
trusted_board_below_capacity
```

The default thresholds are deliberately conservative review thresholds, not
TFT meta rules:

```text
HP pressure         <= 35
critical HP         <= 20
near elimination    <= 10
economy commitment  >= 10g
large commitment    >= 20g
high remaining gold >= 30g
```

Important guards:

- an infeasible economy episode hard-blocks strategic review;
- HP/gold/level/XP are consumed only through feature trust;
- board/bench rules require `usable_for_strategy=true`;
- lower-bound/carried/unusable board values cannot trigger literal board
  conclusions;
- action spend comes only from `episode.economy`;
- boundary gold delta is never treated as action accounting;
- no `decision_grade` is emitted in 0.18.0.

A review candidate means only that the episode is worth inspecting in the
post-game report. It is not labeled as correct, incorrect, greedy, over-rolled,
under-spent or otherwise optimal/suboptimal until richer board/lobby/meta
context exists.


## 0.19.0 Match review cards

`build-review-report` collapses multiple technical `context-review-analyzer` findings from the same `DecisionEpisode` into one user-facing review card.

```text
tft-analyzer build-review-report <match_dir> --timeline
```

Outputs:

```text
<match>/reports/match-review-report-0.19.0.jsonl
<match>/reports/match-review-report-0.19.0_summary.json
<match>/reports/match-review-report-0.19.0.md
```

Card priority is one of `critical/high/medium/low`, but it measures **review importance only**. It is never a strategy grade or mistake probability. Data-quality blockers remain separate cards and are never merged into gameplay coaching.


## 0.20.0 Evidence-aware player roster

Stage 5.0 starts semantic army-state reconstruction without claiming more than
the sparse evidence proves.

Run:

```text
tft-analyzer build-roster-evidence <match_dir> --timeline
```

The layer consumes semantic `BUY_UNIT`, `SELL_UNIT` and
`UNKNOWN_ECON_ACTION` actions already covered by `DecisionEpisode`.

Confirmed BUY identities become cumulative base-copy acquisition evidence:

```text
rhaast >= 4
reksai >= 3
lissandra >= 2
```

These values are lower bounds, not a complete roster. Three acquired copies may
later become one 2-star unit; acquisition evidence therefore remains expressed
in base-copy equivalents.

A BUY affected by a hard cost conflict or insufficient semantic confidence is
not promoted into confirmed ownership. It remains candidate evidence:

```text
?zoe x1
```

Unresolved economy spend is preserved as uncertainty and is never converted
into invented champion acquisitions.

SELL handling is deliberately conservative. Current SELL inference does not
know champion identity or star level. One sold unit can represent 1, 3 or 9
base copies, so unknown sales weaken surviving ownership lower bounds rather
than pretending an exact decrement.

The layer does not yet infer:

```text
complete roster
board-vs-bench assignment
star level
traits
items
board strength
```

Those remain later Stage 5 steps.


## 0.20.1 Acquisition semantics cleanup

0.20.1 narrows the Stage 5.0 contract to facts actually supported by sparse
semantic evidence.

Confirmed BUY history is now exposed as:

```text
confirmed_acquired_copy_lower_bound
```

and summarized as:

```text
final_confirmed_acquisition_copy_lower_bounds
```

Example:

```text
rhaast acquired>=4
```

means only that at least four base-copy equivalents of Rhaast were
historically observed as confirmed acquisitions.

It does **not** mean that four copies are still currently owned.

Current ownership is explicitly:

```text
current_ownership_status = not_established
complete_sell_history_known = false
```

SELL evidence is retained as historical evidence but no longer decrements or
creates a derived "surviving copy lower bound". Sparse screenshots cannot prove
that every sale was observed, and sold-unit star level is not yet known.

The acquisition history therefore remains valid even after an observed sale:
a later sale does not erase the fact that a purchase happened.

Current presence/ownership must be established by a later board/bench identity
layer rather than inferred from absence of SELL events.


## 0.21.0 Slot identity observation dataset

Stage 5.1 exports calibrated board/bench crops for future champion identity
labeling and modeling without inferring identity yet.

Run:

```text
tft-analyzer export-slot-identity-dataset <match_dir> --timeline
```

Default selection:

```text
raw occupancy = occupied
occupancy confidence >= 0.55
scene_valid = true
board + bench
```

The generated dataset lives under:

```text
<match>/datasets/slot-identity-dataset-exporter-0.21.1/
```

and contains:

```text
manifest.jsonl
labels_template.csv
README.md
summary.json
images/board/*.png
images/bench/*.png
```

Each manifest row preserves:

```text
evidence/time/stage
board or bench slot
source/context/footprint geometry
raw occupancy
tracked occupancy + current-vs-carried provenance
scene validity
board gate / strong snapshot metadata
historical acquisition priors
label_status = unlabeled
champion_label = null
```

Acquisition priors from 0.20.1 are causal and non-exhaustive. Only the latest
roster snapshot whose DecisionEpisode has already ended may be attached to a
frame. Future BUY evidence is never leaked backward into earlier crops.

A prior such as:

```text
rhaast acquired>=3
```

is a search hint only. It is not a champion label and it does not establish
current ownership. A champion absent from the prior remains a valid visual
identity.

Optional export switches:

```text
--include-uncertain
--include-empty
--allow-scene-invalid
--board-only
--bench-only
--min-occupancy-confidence <value>
--force
```

Scene-invalid examples are excluded by default because they are unsafe identity
training data. Empty/uncertain crops are opt-in so the default dataset stays
focused on identity candidates rather than mostly-negative slots.

0.21.0 intentionally does not implement champion recognition, star detection,
items, traits or board-strength inference.


## 0.21.1 Identity sample quality tiers

0.21.1 keeps the 0.21.0 observation pool but separates occupancy confidence
for downstream champion-identity work.

Each exported crop now has:

```text
occupancy_evidence_tier:
  trusted
  supported
  raw_candidate

occupancy_evidence_reason

recommended_for_identity_labeling
recommended_for_identity_training
recommended_for_occupancy_review
```

Tier semantics:

```text
trusted
  raw occupied
  + tracked occupied from the same evidence frame
  OR accepted strong board snapshot with tracked occupied
  -> identity labeling = yes
  -> clean identity training = yes

supported
  raw occupied
  + tracked occupied carried from older evidence
  -> identity labeling = yes
  -> clean identity training = no by default

raw_candidate
  raw occupancy lacks tracker support,
  conflicts with tracked empty/unknown,
  is a non-occupied opt-in sample,
  or comes from scene-invalid evidence
  -> occupancy/hard-negative review
```

The exporter does not delete `raw_candidate` crops. They are useful for
occupancy QA and hard-negative mining.

The labeling template now has a first-class target contract:

```text
target_type:
  champion
  no_unit
  uncertain
  unusable
```

Examples:

```text
target_type=champion, champion_label=rhaast
target_type=no_unit, champion_label=
```

`no_unit` is the explicit label for false-positive occupancy examples.

The timeline uses:

```text
BRD / BNH
T / S / R
train / label / occQA
```

so board and bench samples are no longer both rendered as `B`.


## 0.21.2 Identity dataset curation

Stage 5.2 converts the 0.21.1 observation pool into temporal near-duplicate
visual groups and two practical review queues.

Run:

```text
tft-analyzer curate-slot-identity-dataset <match_dir> --timeline
```

Default curation:

```text
max temporal gap = 15s
64-bit dHash Hamming distance <= 6
split on stage change = true
```

Grouping is allowed only inside:

```text
match_id + location + slot_id + queue_type
```

where:

```text
identity_label = trusted + supported
occupancy_qa   = raw_candidate
```

Trusted/supported samples never group together with raw-candidate occupancy QA
examples.

Outputs:

```text
<match>/datasets/slot-identity-curator-0.21.2/
  visual_groups.jsonl
  identity_label_queue.csv
  occupancy_qa_queue.csv
  summary.json
  README.md
  representatives/
    identity_label/
    occupancy_qa/
```

`visual_group_id` is a curation unit only. It is not a champion track and does
not imply that two groups contain different champions.

The curator also reports cross-tabs:

```text
tier x location
tier x stage
recommendation x location
tracker source x location
strong snapshot x tier
```

The ML split contract is explicit:

```text
split_unit = match_id
random crop split = forbidden
random visual-group split across one match = forbidden
```

Acquisition priors remain resolver metadata and must not be used as visual
classifier inputs.


## 0.21.3 Identity labeling workflow

Stage 5.3 adds a validated manual-label round trip over curated visual groups.

Prepare a self-contained package:

```text
tft-analyzer prepare-identity-labeling <match_dir>
```

Output:

```text
<match>/labeling/slot-identity-label-package-0.21.3/
  labels.csv
  label_schema.json
  cvat_image_manifest.csv
  package.json
  README.md
  images/
    identity_label/
    occupancy_qa/
```

Only these `labels.csv` columns are intended for manual editing:

```text
target_type
champion_label
label_status
annotator
notes
```

Target types:

```text
champion
no_unit
uncertain
unusable
```

`champion` requires a champion label. Other target types require an empty
champion label.

The package contains a pinned-set champion schema from the active Data Dragon
catalog when available. Champion labels are normalized and validated against
that exact TFT set during import.

Import current labels:

```text
tft-analyzer import-identity-labels <match_dir>
```

Partial imports are supported by default, allowing annotation to proceed in
batches. Use:

```text
--require-complete
```

for a final pass that rejects any unlabeled visual group.

Canonical import outputs:

```text
<match>/labels/slot-identity-label-importer-0.21.3/
  labeled_visual_groups.jsonl
  visual_champion_training_manifest.csv
  occupancy_negative_manifest.csv
  summary.json
```

`labeled_visual_groups.jsonl` is canonical project truth. External annotation
tools such as CVAT are optional UI only.

Training eligibility remains conservative:

```text
champion
+ representative trusted for identity training
+ pinned-set catalog validation
-> visual champion training candidate
```

A `no_unit` label becomes an occupancy-negative candidate only when it came
from the `occupancy_qa` queue. `no_unit` inside the identity queue is preserved
as a QA conflict rather than silently converted into training data.

The summary reports per champion:

```text
visual groups
underlying member samples
training-eligible groups
match count
board/bench counts
```

The ML split unit remains `match_id`; acquisition priors are not visual-model
features.


## 0.21.4 Local identity labeler

Stage 5.4 adds a dependency-free local browser UI over the existing 0.21.3
label package.

No label package regeneration is required.

Run:

```text
tft-analyzer label-identities <match_dir>
```

The command starts a local server on:

```text
http://127.0.0.1:8765/
```

and opens the default browser.

The UI provides:

```text
large scaled crop
current queue / board-bench / stage / tier metadata
current labeling progress

champion buttons from the pinned TFT set catalog
champion search
No unit
Uncertain
Unusable

identity_label / occupancy_qa filter
board / bench filter
unlabeled / labeled / all filter

previous / next
clear label
repeat last label
notes
annotator
```

Every click is written atomically to the existing:

```text
slot-identity-label-package-0.21.3/labels.csv
```

The representative image is not physically moved or duplicated into a
champion-named directory. `visual_group_id` and the curated package remain
stable; the class assignment is canonical metadata.

Keyboard shortcuts:

```text
Left / Right = navigation
N            = no_unit
U            = uncertain
X            = unusable
/            = focus champion search
Enter        = choose the first filtered champion
```

After a label is saved while `Unlabeled only` is active, the UI automatically
advances to the next remaining crop.

The labeler accepts the already generated 0.21.3 package and uses the active
Data Dragon catalog for human-friendly current-set champion buttons such as
`Rek'Sai`, while saving the normalized canonical label (`reksai`).

After any partial labeling session, run:

```text
tft-analyzer import-identity-labels <match_dir>
```

to validate the labels and rebuild canonical labeled/training artifacts.


## 0.21.5 Proxy-safe local labeler tests

0.21.5 fixes the local HTTP integration tests for Windows/workstations with an
active system proxy, Hiddify or `HTTP(S)_PROXY` environment variables.

The labeler server itself is unchanged.

Tests that talk to their temporary `127.0.0.1:<port>` server now use a dedicated
urllib opener:

```text
ProxyHandler({})
```

so loopback requests are always direct and cannot be routed through a proxy.

This prevents false failures such as:

```text
ConnectionResetError: [WinError 10054]
HTTP Error 502: Bad Gateway
```

when the local labeler is healthy but the workstation proxy intercepts urllib
requests.


## 0.21.6 Undo last identity label

The local identity labeler now keeps an in-memory undo history for the current
labeling session.

Use either:

```text
↶ Undo last
Ctrl+Z
```

The previous editable state of the most recently changed visual group is
restored atomically in `labels.csv`, including:

```text
target_type
champion_label
label_status
annotator
notes
```

After undo, the UI returns to the reverted crop and temporarily switches the
status filter to `All` so the corrected sample is visible immediately.

Undo history is intentionally session-local. Restarting the labeler clears the
undo stack; already saved labels remain durable in `labels.csv`.


## 0.21.7 Human label audit & dataset policy

Stage 5.5 separates human semantic truth from upstream occupancy confidence.

Run after importing labels:

```text
tft-analyzer audit-identity-labels <match_dir>
```

Champion identity policy:

```text
primary
  = human-confirmed champion
  + pinned-set catalog validation
  + representative tier trusted

secondary
  = human-confirmed champion
  + pinned-set catalog validation
  + representative tier supported

recovered_candidate
  = human-confirmed champion
  + pinned-set catalog validation
  + representative tier raw_candidate
```

Human `no_unit` is exported as explicit occupancy QA/hard-negative evidence.
It is never used as champion-identity training data.

`uncertain` and `unusable` remain excluded from supervised champion training.

Outputs:

```text
<match>/audits/slot-identity-human-label-audit-0.21.7/
  visual_champion_primary_manifest.csv
  visual_champion_secondary_manifest.csv
  visual_champion_human_confirmed_manifest.csv
  occupancy_hard_negative_manifest.csv
  summary.json
  README.md
```

The audit reports:

```text
target x location
target x representative tier
target x tracker source
target x slot
champion x primary/secondary/recovered tier
champion x board/bench
occupancy false-positive hotspots
```

The classifier feature contract remains strict:

```text
pixels only
```

Occupancy tier, tracker source and acquisition priors are provenance/resolver
metadata and must not be classifier inputs.

Queue-level completeness is now supported:

```text
tft-analyzer import-identity-labels <match_dir> \
  --require-complete-queue identity_label
```

This validates a finished identity-labeling pass without requiring the separate
`occupancy_qa` queue to be complete.
