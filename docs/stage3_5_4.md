# Stage 3.5.4 — Match-local arena scene guard

Visual QA of the nine 0.13.2 `full-cap` snapshots found seven usable board
scenes and two false positives:

```text
720.703  L5  Choose your God wisely
721.750  L5  Choose your God wisely
```

Both special screens happened to produce exactly five occupied candidates and
therefore satisfied the level-cap invariant.

The failure is not occupancy, level tracking or temporal tracking. It is scene
validity.

## Guard

0.13.4 fits four static arena anchors from the same match:

```text
top_left
top_right
left_wall
right_wall
```

The board centre and lower shop/choice UI are deliberately excluded.

Each anchor is resized to a compact RGB descriptor. A two-pass median template
is fitted:

1. median reference from all match frames;
2. score every frame against that reference;
3. retain the most arena-like 60%;
4. rebuild the final median reference.

A frame is valid by default when:

```text
median anchor distance <= 0.12
at least 3/4 anchors <= 0.15
```

The threshold operates against a **match-local template**, not a global arena
image.

## Gate order

```text
scene valid
  AND HUD/planning gate
  AND level capacity invariant
  AND full-cap / visual evidence
       ↓
canonical board
```

`scene_invalid` has priority over `full_level_snapshot`.

## Expected QA acceptance

The two God-choice frames should disappear from `full-cap` and appear in
`scene-invalid`.

The lower `Choose One` overlay at 1675.6 should remain a valid full-cap board
snapshot because the arena anchors remain visible.
