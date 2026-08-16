# Stage 3.1.1 - Shop Identity Stabilization (0.9.1)

The 0.9.0 full-match run proved that shop geometry, occupancy and raw OCR are
usable, but also exposed a semantic identity error:

```text
same portrait hash -> "orn" x15, "ornn" x1
```

OCR confidence answers "did OCR read this string confidently?". It does not
answer "is this a valid champion identity?".

0.9.1 separates those concepts.

## Resolution pipeline

```text
raw OCR
  -> normalized OCR token
  -> exact/fuzzy lexicon resolution
  -> match-wide exact portrait-hash consensus
  -> canonical resolved_name
```

Semantic observations contain both evidence and resolved identity:

```text
raw_text
ocr_token
ocr_confidence
resolved_name
identity_method
identity_confidence
visual_hash
hash_consensus_support
hash_consensus_ratio
```

`normalized_name` remains as a compatibility alias for `resolved_name`; it is
no longer allowed to contain an arbitrary OCR token.

## Lexicon

The bootstrap lexicon lives at:

```text
game_data/shop_identity_lexicon_v1.txt
```

It contains canonical normalized identities observed in the current recorded
match environment. It is deliberately external and replaceable; a later Riot
metadata stage should generate a set-specific lexicon automatically.

Unknown OCR tokens resolve to `None`, never to a new semantic champion.

## Fuzzy resolution

A token must have:

- sufficient similarity to one lexicon entry;
- sufficient margin over the second candidate;
- a small edit distance.

Short truncations are treated more strictly. `orn -> ornn` is accepted because
it is a one-character prefix truncation with a unique candidate.

## Two-pass hash consensus

Post-game processing is naturally two-pass:

1. Process all frames and collect OCR/hash evidence.
2. Build exact-dHash consensus only from lexicon-resolved, sufficiently
   confident OCR seeds.
3. Rebuild complete observations using the consensus.

Hash consensus may recover an identity when the current frame's OCR fails, but
only after at least two supporting frames and a configured winner ratio.

The raw OCR output is never overwritten; the resolution method is explicit.

## Output artifacts

```text
observations/shop-rapidocr-0.9.1.jsonl
observations/shop-rapidocr-0.9.1_attempts.jsonl
observations/shop-rapidocr-0.9.1_identity.json
observations/shop-rapidocr-0.9.1_summary.json
```

The identity JSON contains the effective lexicon, hash consensus table and
fuzzy corrections for audit/reproducibility.

## Acceptance

Re-run only shop perception:

```powershell
tft-analyzer perceive-shop `
  .\data\matches\20260812T164303Z_4c85a55ea6
```

Important checks:

```text
fuzzy_corrections contains orn->ornn
unique resolved names no longer contains orn
identity_method_counts are sensible
hash consensus is used conservatively
semantic snapshot changes do not increase because of OCR spelling variants
```

Shop is still not connected to tracking/canonical GameState in this patch.
