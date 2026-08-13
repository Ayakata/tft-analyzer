from datetime import datetime, timezone

from tft_analyzer.core.enums import (
    ActionType,
    EventType,
    EvidenceKind,
    ObservationKind,
)
from tft_analyzer.core.models import (
    EvidenceRef,
    GameEvent,
    GameState,
    MatchManifest,
    Observation,
    PlayerState,
    SemanticAction,
    ShopState,
    TransitionSample,
)


def test_evidence_and_observation_keep_provenance() -> None:
    evidence = EvidenceRef(
        evidence_id="ev-1",
        match_id="m-1",
        timestamp_s=10.0,
        kind=EvidenceKind.ROI,
        uri="evidence/crops/shop_0.png",
    )

    obs = Observation(
        observation_id="obs-1",
        match_id="m-1",
        timestamp_s=10.0,
        kind=ObservationKind.SHOP,
        value={"slot": 0, "champion_id": "TFT_TEST_Unit"},
        confidence=0.98,
        evidence_ids=(evidence.evidence_id,),
        producer_version="shop-recognizer-0.1.0",
    )

    assert obs.evidence_ids == ("ev-1",)


def test_event_state_and_transition_contract() -> None:
    event = GameEvent(
        event_id="event-1",
        match_id="m-1",
        timestamp_s=11.0,
        event_type=EventType.REFRESH_SHOP,
        payload={"gold_cost": 2},
        confidence=0.99,
        producer_version="event-engine-0.1.0",
    )

    state = GameState(
        state_id="state-1",
        match_id="m-1",
        timestamp_s=11.0,
        player=PlayerState(hp=100, gold=48, level=4, xp=0),
        shop=ShopState(slots=("A", "B", "C", "D", "E")),
        parent_state_id=None,
        applied_event_ids=(event.event_id,),
        source_state_ids=("tracked-state-1",),
        reducer_version="state-reducer-0.1.0",
    )

    action = SemanticAction(
        action_id="action-1",
        action_type=ActionType.REFRESH_SHOP,
        legal=True,
    )

    transition = TransitionSample(
        match_id="m-1",
        state_id=state.state_id,
        action=action,
        next_state_id="state-2",
        timestamp_s=11.0,
        action_mask=("refresh_shop", "purchase_xp"),
    )

    assert transition.action.action_type == ActionType.REFRESH_SHOP


def test_manifest_roundtrip() -> None:
    manifest = MatchManifest(
        match_id="m-1",
        started_at=datetime.now(timezone.utc),
        patch="test",
        set_id="test-set",
    )
    restored = MatchManifest.model_validate_json(manifest.model_dump_json())
    assert restored == manifest
