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
