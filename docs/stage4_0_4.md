# Stage 4.0.4 — Trusted TFT Game Data + Champion Cost Ledger

## Source contract

The game-data layer is explicit and versioned. The first provider is Riot Data
Dragon.

Sync:

```powershell
tft-analyzer sync-game-data --version 16.16.1
```

Output:

```text
data/game_data/
  riot_ddragon/
    active.json
    16.16.1/
      en_US/
        tft-champions.catalog.json
```

The catalog snapshot stores:

```text
provider
version
locale
source_url
source_sha256
fetched_at_utc
source_field_for_cost = tier
champions[]
```

No network access occurs during `infer-actions`; inference consumes the exact
local catalog and records its version/hash in the summary.

For offline or proxied environments:

```powershell
tft-analyzer sync-game-data `
  --version 16.16.1 `
  --from-file .\tft-champion.json
```

## Ambiguity policy

Riot TFT champion data can contain records for multiple active sets.

Lookup is normalized by champion display name. If all matching records expose
the same positive `tier`, the cost resolves by consensus.

```text
Zoe -> tiers {1,1} -> cost 1
```

If matching records disagree:

```text
Briar -> tiers {1,4}
```

the result is `ambiguous` and the analyzer does not price the buy.

No set is guessed from an ID prefix.

## Ledger integration

A resolved BUY component has:

```text
champions
unit_costs
spend_min
spend_max
pricing_provider
pricing_version
```

For a fully resolved buy:

```text
spend_min == spend_max
exact_spend = true
```

For a partially/missing/ambiguous buy, resolved champion costs still contribute
to `spend_min`, while `spend_max` remains open.

Reroll upper bounds are computed only after mandatory XP and priced BUY minima
are allocated, preventing the same gold from being allocated twice.

## Acceptance target on canonical match

The currently visible BUY windows suggest several exact-cost checks:

```text
BUY[lissandra,lissandra]
BUY[reksai]
BUY[rhaast]
BUY[zoe]
BUY[reksai,reksai]
BUY[rhaast,briar]
```

After syncing the correct Data Dragon patch, inspect:

```text
Game data: ... buy_priced=X/Y
```

and expect exact BUY windows to collapse from `K[0..N]+U[0..N]` toward
`K[N]+U[0]`.
