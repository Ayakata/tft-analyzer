from tft_analyzer.actions.fusion import FusionSnapshot
from tft_analyzer.actions.pipeline import (
    _build_xp_requirement_map,
    _enrich_absolute_xp,
)


def snap(level, current, required, eid):
    return FusionSnapshot(
        match_id="m",
        timestamp_s=float(level),
        evidence_id=eid,
        stage="3-2",
        stage_status="carried",
        gold=10,
        gold_status="carried",
        level=level,
        level_status="carried",
        xp_current=current,
        xp_required=required,
        xp_status="carried",
        xp_absolute=None,
        shop_slots=(),
        shop_status="unknown",
        board_count=0,
        board_cells=frozenset(),
        board_usable=False,
        scene_valid=True,
        bench_count=0,
        bench_slots=frozenset(),
    )


def test_requirement_map_uses_mode_per_level():
    snapshots = [
        snap(4, 0, 10, "a"),
        snap(4, 2, 10, "b"),
        snap(4, 4, 12, "noise"),
        snap(5, 0, 20, "c"),
        snap(5, 4, 20, "d"),
    ]
    assert _build_xp_requirement_map(snapshots) == {
        4: 10,
        5: 20,
    }


def test_absolute_xp_is_continuous_across_level_up():
    snapshots = [
        snap(4, 8, 10, "a"),
        snap(5, 2, 20, "b"),
    ]

    enriched, reqs, base = _enrich_absolute_xp(snapshots)

    assert base == 4
    assert reqs[4] == 10
    assert enriched[0].xp_absolute == 8
    assert enriched[1].xp_absolute == 12
    assert enriched[1].xp_absolute - enriched[0].xp_absolute == 4


def test_absolute_xp_is_none_when_requirement_gap_exists():
    snapshots = [
        snap(4, 8, 10, "a"),
        snap(6, 2, 36, "b"),
    ]

    enriched, reqs, base = _enrich_absolute_xp(snapshots)

    assert base == 4
    assert 5 not in reqs
    assert enriched[0].xp_absolute == 8
    assert enriched[1].xp_absolute is None
