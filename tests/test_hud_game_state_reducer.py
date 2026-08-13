from tft_analyzer.core.enums import (
    EventQuality,
    EventType,
    ReductionAction,
)
from tft_analyzer.core.models import (
    EventValidation,
    GameEvent,
    TrackedField,
    TrackedHUDState,
)
from tft_analyzer.reducers.hud.reducer import (
    HUDGameStateReducer,
    HUDGameStateReducerSettings,
)


def validation(
    event_id,
    *,
    field="gold",
    quality=EventQuality.TRUSTED,
    apply=True,
    from_conf=1.0,
    to_conf=1.0,
):
    return EventValidation(
        validation_id=f"v-{event_id}",
        match_id="m1",
        event_id=event_id,
        quality=quality,
        reasons=("test",),
        field=field,
        event_timestamp_s=10.0,
        transition_window_s=5.0,
        from_confidence=from_conf,
        to_confidence=to_conf,
        apply_to_state=apply,
        validator_version="test",
    )


def gold_event(eid, before, after):
    return GameEvent(
        event_id=eid,
        match_id="m1",
        timestamp_s=10.0,
        event_type=EventType.GOLD_CHANGED,
        payload={
            "field": "gold",
            "from": {"gold": before},
            "to": {"gold": after},
            "delta": after - before,
        },
        confidence=0.9,
        producer_version="test",
    )


def test_bootstrap_initializes_first_observed_values():
    reducer = HUDGameStateReducer(
        HUDGameStateReducerSettings(),
        match_id="m1",
    )

    tracked = TrackedHUDState(
        state_id="s1",
        match_id="m1",
        timestamp_s=1.0,
        stage=TrackedField(
            value={"stage": 1, "round": 1},
            confidence=0.99,
            source_observation_id="o-stage",
            source_evidence_id="e-stage",
            source_timestamp_s=1.0,
            age_s=0.0,
            status="observed",
        ),
        tracker_version="test",
    )

    decisions = reducer.initialize_from_tracked_state(tracked)

    assert len(decisions) == 1
    assert decisions[0].action == ReductionAction.INITIALIZED

    state = reducer.snapshot(
        timestamp_s=1.0,
        source_token="s1",
        parent_state_id=None,
        applied_event_ids=(),
        source_state_ids=("s1",),
    )
    assert state.stage == 1
    assert state.round == 1


def test_low_target_event_is_skipped():
    reducer = HUDGameStateReducer(
        HUDGameStateReducerSettings(),
        match_id="m1",
    )
    reducer.gold = 41
    from tft_analyzer.core.models import StateFieldMeta
    reducer.field_meta["gold"] = StateFieldMeta(
        confidence=1.0,
        last_observed_at_s=1.0,
    )

    ev = gold_event("g1", 41, 17)
    val = validation(
        "g1",
        quality=EventQuality.SUSPICIOUS,
        apply=False,
        to_conf=0.48,
    )

    decision = reducer.apply_event(ev, val)

    assert decision.action == ReductionAction.SKIPPED_VALIDATION
    assert reducer.gold == 41


def test_strong_target_recovers_across_skipped_suspicious_baseline():
    reducer = HUDGameStateReducer(
        HUDGameStateReducerSettings(),
        match_id="m1",
    )
    reducer.gold = 41
    from tft_analyzer.core.models import StateFieldMeta
    reducer.field_meta["gold"] = StateFieldMeta(
        confidence=1.0,
        last_observed_at_s=1.0,
    )

    ev = gold_event("g2", 1, 52)
    val = validation(
        "g2",
        quality=EventQuality.SUSPICIOUS,
        apply=True,
        from_conf=0.59,
        to_conf=0.99,
    )

    decision = reducer.apply_event(ev, val)

    assert decision.action == ReductionAction.APPLIED_WITH_MISMATCH
    assert decision.reason == "trusted_target_recovery_from_source_mismatch"
    assert reducer.gold == 52

    state = reducer.snapshot(
        timestamp_s=10.0,
        source_token="s2",
        parent_state_id="parent",
        applied_event_ids=("g2",),
        source_state_ids=("s2",),
    )
    assert state.player.gold == 52
    assert state.confidence == 0.99


def test_xp_required_is_preserved_in_game_state():
    reducer = HUDGameStateReducer(
        HUDGameStateReducerSettings(),
        match_id="m1",
    )
    reducer.xp = 54
    reducer.xp_required = 60
    from tft_analyzer.core.models import StateFieldMeta
    reducer.field_meta["xp"] = StateFieldMeta(
        confidence=0.98,
        last_observed_at_s=1.0,
    )

    ev = GameEvent(
        event_id="xp1",
        match_id="m1",
        timestamp_s=10.0,
        event_type=EventType.XP_CHANGED,
        payload={
            "field": "xp",
            "from": {"current": 54, "required": 60},
            "to": {"current": 2, "required": 68},
        },
        confidence=0.97,
        producer_version="test",
    )
    val = validation(
        "xp1",
        field="xp",
        to_conf=0.97,
    )

    reducer.apply_event(ev, val)
    state = reducer.snapshot(
        timestamp_s=10.0,
        source_token="xp",
        parent_state_id=None,
        applied_event_ids=("xp1",),
        source_state_ids=("sx",),
    )

    assert state.player.xp == 2
    assert state.player.xp_required == 68



def test_repeated_same_value_refreshes_confidence_without_semantic_change():
    reducer = HUDGameStateReducer(
        HUDGameStateReducerSettings(),
        match_id="m1",
    )
    reducer.gold = 10
    reducer.field_meta["gold"] = __import__(
        "tft_analyzer.core.models",
        fromlist=["StateFieldMeta"],
    ).StateFieldMeta(
        confidence=0.70,
        last_observed_at_s=1.0,
        source_observation_id="old",
        source_evidence_id="e-old",
        source_tracked_state_id="s-old",
    )

    tracked = TrackedHUDState(
        state_id="s-new",
        match_id="m1",
        timestamp_s=10.0,
        gold=TrackedField(
            value={"gold": 10},
            confidence=0.99,
            source_observation_id="new",
            source_evidence_id="e-new",
            source_timestamp_s=10.0,
            age_s=0.0,
            status="observed",
        ),
        tracker_version="test",
    )

    decisions = reducer.refresh_from_tracked_state(tracked)

    assert len(decisions) == 1
    assert decisions[0].action == ReductionAction.METADATA_REFRESHED
    assert reducer.gold == 10
    assert reducer.field_meta["gold"].confidence == 0.99
    assert reducer.field_meta["gold"].source_observation_id == "new"


def test_different_tracked_value_does_not_refresh_canonical_metadata():
    reducer = HUDGameStateReducer(
        HUDGameStateReducerSettings(),
        match_id="m1",
    )
    reducer.gold = 41

    from tft_analyzer.core.models import StateFieldMeta

    reducer.field_meta["gold"] = StateFieldMeta(
        confidence=1.0,
        last_observed_at_s=909.0,
        source_observation_id="gold-41",
        source_evidence_id="e41",
        source_tracked_state_id="s41",
    )

    tracked = TrackedHUDState(
        state_id="s17",
        match_id="m1",
        timestamp_s=913.6,
        gold=TrackedField(
            value={"gold": 17},
            confidence=0.48,
            source_observation_id="gold-17",
            source_evidence_id="e17",
            source_timestamp_s=913.6,
            age_s=0.0,
            status="observed",
        ),
        tracker_version="test",
    )

    decisions = reducer.refresh_from_tracked_state(tracked)

    assert decisions == []
    assert reducer.gold == 41
    assert reducer.field_meta["gold"].confidence == 1.0
    assert reducer.field_meta["gold"].source_observation_id == "gold-41"


def test_snapshot_has_bounded_direct_provenance_and_parent():
    reducer = HUDGameStateReducer(
        HUDGameStateReducerSettings(),
        match_id="m1",
    )
    reducer.gold = 10

    from tft_analyzer.core.models import StateFieldMeta

    reducer.field_meta["gold"] = StateFieldMeta(
        confidence=0.99,
        last_observed_at_s=10.0,
    )

    state = reducer.snapshot(
        timestamp_s=10.0,
        source_token="s2",
        parent_state_id="state-previous",
        applied_event_ids=("e-current",),
        source_state_ids=("tracked-old", "tracked-new"),
    )

    assert state.parent_state_id == "state-previous"
    assert state.applied_event_ids == ("e-current",)
    assert state.source_state_ids == ("tracked-old", "tracked-new")
    assert not hasattr(state, "source_event_ids")


def test_snapshot_age_uses_last_confirmation_time():
    reducer = HUDGameStateReducer(
        HUDGameStateReducerSettings(),
        match_id="m1",
    )
    reducer.gold = 10

    from tft_analyzer.core.models import StateFieldMeta

    reducer.field_meta["gold"] = StateFieldMeta(
        confidence=0.99,
        last_observed_at_s=7.5,
    )

    state = reducer.snapshot(
        timestamp_s=10.0,
        source_token="age",
        parent_state_id=None,
        applied_event_ids=(),
        source_state_ids=(),
    )

    assert state.field_meta["gold"].age_s == 2.5
