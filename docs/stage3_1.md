# Stage 3.1 - Shop snapshot perception MVP (0.9.0)

## Scope

Stage 3.1 starts shop perception as an independent observation stream. It does
**not** yet feed shop snapshots into temporal tracking or infer purchases/rolls.

The first acceptance target is visual correctness on real frames:

```text
shop_region
    |
    +--> five fixed card slots
            |
            +--> occupied / empty
            +--> portrait visual hash
            +--> champion-name OCR
```

## Why OCR names first

TFT shop cards render champion names as clear text. For the current MVP this is
a lower-risk identity source than introducing a new image classifier before the
geometry and coverage are measured.

The OCR output is normalized to a stable token:

```text
Pantheon      -> pantheon
Miss Fortune  -> missfortune
K'Sante       -> ksante
```

This is not yet a canonical Riot champion ID. Set-specific roster resolution is
a later layer.

## Occupancy

Each slot uses the existing portrait ROI. Empty slots are visually flat/dark;
occupied portraits have substantially greater contrast, edge density and color
variation.

`slot_occupancy_score` combines those signals. The default occupied threshold is
`0.30`.

## Visual hash

Occupied portrait crops receive an 8x8 dHash. The hash is retained as
perception provenance/fallback evidence, but is not yet used as semantic shop
identity.

## Name crop

The champion name crop is relative to each already-calibrated shop card:

```yaml
name_x0: 0.03
name_x1: 0.72
name_y0: 0.70
name_y1: 0.91
```

At 1920x1080 this isolates the lower-left champion-name bar while avoiding cost
and trait text.

## Observation policy

A `SHOP` observation is emitted only when:

1. the shop region is present;
2. all five slot occupancies are resolved;
3. every occupied slot has a name with sufficient confidence;
4. aggregate snapshot confidence exceeds the configured threshold.

This deliberately favors precision over coverage for the first full-match run.

## Debug

Run one clearly visible shop frame first:

```powershell
tft-analyzer shop-debug <frame.png>
```

Outputs:

```text
data/shop_debug/<frame>_<profile>/
├── overlay.png
├── shop_region.png
├── result.json
├── cards/
├── portraits/
└── names/
```

The console prints each slot's occupancy, normalized OCR name, confidence and
visual hash.

## Full match

After one-frame calibration:

```powershell
tft-analyzer perceive-shop .\data\matches\<match_id>
```

Summary reports:

```text
shop presence rate
complete snapshot rate
occupied-slot detections
name parse rate
mean name confidence
slot occupancy counts
unique normalized names
observed snapshot changes
max observation gap
```

## Deliberate boundary

`shop-rapidocr-0.9.0.jsonl` is **not added to tracker inputs yet**.

First we validate shop geometry and identity stability. Only then will the next
patch add:

```text
SHOP Observation
    -> tracked ShopState
    -> SHOP_CHANGED
    -> canonical GameState.shop
```

Higher-level `BUY_UNIT` and `REFRESH_SHOP` inference remains later still because
a changed shop snapshot alone does not prove the cause.
