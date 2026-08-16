# Architecture v0.1

## Stable contracts

- `EvidenceRef`
- `Observation`
- `GameEvent`
- `GameState`
- `SemanticAction`
- `DecisionEpisode`
- `Finding`
- `TransitionSample`
- `MatchManifest`

Prefer additive schema evolution. Breaking changes require a new schema version and rebuild/migration tooling.

## Layer rules

### Capture
Produces immutable evidence only.

### Perception
Consumes evidence and emits observations with confidence and provenance.

### Tracking
Combines observations over time, emits semantic events and reduces them into canonical `GameState`.

### Decisions
Groups low-level semantic events into strategic episodes, e.g. many refresh/buy/sell events into one `ROLLDOWN`.

### Analysis
Consumes canonical states and decisions. No pixel access.

### ML
Consumes encoded canonical states/actions/trajectories. No capture dependency.

### RL
Consumes the same semantic states/actions as all other subsystems. Simulator support is optional behind transition/environment interfaces.

### Realtime
Optional read-only consumer of current canonical state plus analyzer/model outputs. It is never required by recording, replay, post-game analysis, ML training or RL datasets.

## Capture backend boundary

Stage 1.1 defines WGC as the default HWND backend and MSS as a diagnostic
fallback. `MatchSession` consumes only the backend contract.

## Layout / ROI boundary (Stage 2.0)

Perception modules must not hard-code pixel rectangles. They request named ROIs
from a versioned `LayoutProfile` / `ROIRegistry`. Layout profiles use normalized
coordinates and can vary independently by aspect ratio, UI scale or future TFT UI
revision.


## HUD perception boundary

Stage 2.1 introduces an OCR adapter boundary. HUD recognizers consume ROI crops
through the `OCREngine` protocol and emit canonical `Observation` objects.
RapidOCR is the first backend, but tracking and downstream analysis do not
depend on RapidOCR itself.


## Presence confidence semantics

As of 0.4.3, HUD presence confidence is conjunctive: the weakest required
presence criterion controls the score. This keeps diagnostic confidence
consistent with the hard presence decision and prevents `ABSENT(1.000)`.


## Temporal fusion boundary

Stage 2.2 introduces `TrackedHUDState` between perception and semantic event
extraction. A tracked state is derived and rebuildable. It may carry recent
values across missing observations, but every carried value preserves the exact
source observation/evidence and its age.

Tracking rejects domain-impossible regressions but does not yet decide why a
valid state change happened. That semantic responsibility remains in the event
detector.


## Canonical tracked values

As of 0.5.1, temporal tracking stores only semantic game values. Perception metadata remains in source observations and provenance, but is excluded from equality and transition logic.


## Primitive event boundary

Stage 2.3 is intentionally causal-neutral. It converts confirmed semantic state
differences into primitive events without explaining the cause.

For example `gold 50 -> 43` becomes `GOLD_CHANGED(delta=-7)`, not
`BUY_UNIT`, `REFRESH_SHOP`, or `PURCHASE_XP`. Those explanations require
additional synchronized evidence and belong to later inference layers.

Event timestamps identify the first observation of the new value; transition
windows preserve temporal uncertainty between the last old observation and the
first new observation.


## Validation is not evidence rewriting

Stage 2.4 introduces `EventValidation` as an independent derived contract.
Primitive `GameEvent` objects remain immutable.

Validation separates transition trust from target-state trust. This is
important because a transition can be suspicious due to a weak previous value
while the new observed target is reliable.

The canonical reducer consumes the validation recommendation and records every
apply/skip/recovery decision. Suspicious intermediate values therefore remain
auditable in the primitive event stream without automatically entering
`GameState`.


## Parent-linked canonical state lineage

As of 0.7.1, `GameState` no longer embeds cumulative event/state provenance.
Each state references its parent and only the events/tracked states directly
responsible for the current transition.

Field confidence is also independent of semantic transition creation:
confirmation of an unchanged value updates field metadata while the canonical
state sequence remains semantic-only.


## Independent perception streams

Stage 3.0 formalizes that one match may have multiple versioned Observation
producers. Fixed HUD OCR and dynamic player-list perception are rebuilt
independently and merged only at temporal tracking.

This avoids coupling mature OCR components to experimental CV modules.

Player HP is the first field to use the full vertical extension pattern:

`pixels -> Observation -> TrackedHUDState -> GameEvent -> EventValidation ->
GameState`.


## Player HP stabilization boundary

Stage 3.0.1 keeps row identity, HP OCR geometry and temporal plausibility as separate responsibilities. The perception producer prefers calibrated HP geometry and emits raw confidence/provenance; the tracker then handles stateful confirmation rules such as large jumps and possible healing. No downstream event or GameState contract is changed by this patch.
\n\n## Shop perception boundary\n\nShop snapshot perception is introduced as an independent producer before it is\nallowed to affect canonical state. The first version records slot occupancy,\nOCR name tokens and portrait hashes. Temporal shop tracking and causal action\ninference are intentionally deferred until the raw snapshot stream is validated\non a complete match.\n

## Shop identity resolution

Shop OCR text is evidence, not identity. Stage 3.1.1 introduces an explicit
resolver boundary: OCR token -> lexicon candidate -> optional match-wide exact
portrait-hash consensus -> resolved semantic shop identity. Downstream shop
tracking must consume only resolved identities.


## Shop enters the canonical state pipeline (0.10.0)

The common tracked timeline now merges three independent perception streams:

```text
fixed HUD OCR
player HP
shop snapshots
      ↓
TrackedHUDState
```

Shop changes are represented as primitive `SHOP_CHANGED` facts. The event layer
does not infer why a slot changed. This preserves the existing architectural
boundary between perception/state reconstruction and later decision analysis.


## Sparse decision-episode boundary (Stage 4.1)

`DecisionEpisode` is an evidence-bounded trajectory segment, not a recovered
click sequence. With sparse screenshots, actions inferred from one transition
window are unordered. Only ordering between non-overlapping source windows is
retained (`window_partial_order`). Strategic labels such as `ROLLDOWN` are not
assigned by the episode builder unless later analyzers can justify them.
