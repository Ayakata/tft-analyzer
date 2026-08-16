# Stage 4.0.6 — Economy Feasibility / Constraint Violations

The economy ledger now separates recognized-action requirements from the spend
budget observed in the HUD.

For feasible windows:

```text
5=K[2..4]+U[1..3]
```

For an impossible constraint system:

```text
observed spend = 1
required BUY Zoe = 2
1g ! K[2] deficit[1]
```

No unallocated interval is produced when there is no valid decomposition.
Fields added to each ledger window:

```text
required_action_spend_min/max
compatible_action_spend_min/max
feasible
spend_deficit_min/max
```

`action_spend_min/max` remain as compatibility aliases for the required-action
interval and are no longer observation-clamped.
