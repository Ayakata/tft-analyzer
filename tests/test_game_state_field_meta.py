from tft_analyzer.core.models import GameState, StateFieldMeta


def test_game_state_field_metadata_roundtrip():
    state = GameState(
        state_id="s1",
        match_id="m1",
        timestamp_s=10.0,
        field_meta={
            "gold": StateFieldMeta(
                confidence=0.99,
                last_observed_at_s=9.0,
                age_s=1.0,
                source_observation_id="o1",
                source_evidence_id="e1",
                source_tracked_state_id="ts1",
            )
        },
        parent_state_id="parent",
        applied_event_ids=("ev1",),
        source_state_ids=("ts1",),
        reducer_version="test",
    )

    restored = GameState.model_validate_json(state.model_dump_json())

    assert restored == state
    assert restored.field_meta["gold"].confidence == 0.99
    assert restored.parent_state_id == "parent"
