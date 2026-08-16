# Stage 3.5.2 — HUD level semantic contract fix

Real 0.13.1 output showed:

```text
HUD gate: aligned=271 level_known=0
```

HUD discovery/alignment was correct. The bug was semantic extraction.

Canonical tracked HUD level:

```json
{"level": {"value": {"level": 8}}}
```

0.13.2 normalizes `{"level": 8} -> 8`, while retaining scalar support for
compatibility. No geometry or occupancy parameters change.

Acceptance:
- `aligned=271`
- `level_known > 0`
- timeline displays L3/L4/.../L8 rather than L?
- the 1642.609 planning frame can activate `full_level_snapshot`.
