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
