from tft_analyzer.features.episode_context.builder import (
    build_context_feature_trust,
)
from tft_analyzer.features.episode_context.models import (
    EpisodeContextQuality,
    EpisodePlayerContext,
    EpisodePlayerStateDelta,
    EpisodePlayerStateFeature,
)
from tft_analyzer.features.episode_context.timeline import (
    format_episode_context_timeline,
)


def test_context_timeline_surfaces_hp_economy_and_board_trust(tmp_path):
    before = EpisodePlayerStateFeature(
        timestamp_s=0.0,
        evidence_id="e0",
        stage="4-2",
        hp=35,
        gold=70,
        level=6,
        xp_absolute=42,
        board_count=6,
        board_capacity=6,
        board_utilization=1.0,
        bench_count=4,
        bench_utilization=4 / 9,
        board_scene_valid=True,
        board_usable=True,
        board_strong_snapshot=True,
        board_capacity_status="full_cap",
    )
    after = EpisodePlayerStateFeature(
        timestamp_s=10.0,
        evidence_id="e1",
        stage="4-2",
        hp=28,
        gold=28,
        level=7,
        xp_absolute=74,
        board_count=7,
        board_capacity=7,
        board_utilization=1.0,
        bench_count=4,
        bench_utilization=4 / 9,
        board_scene_valid=True,
        board_usable=True,
        board_strong_snapshot=True,
        board_capacity_status="full_cap",
    )

    value = EpisodePlayerContext(
        context_id="c1",
        decision_id="d1",
        match_id="m",
        stage_start="4-2",
        stage_end="4-2",
        before=before,
        after=after,
        delta=EpisodePlayerStateDelta(
            hp=-7,
            gold=-42,
            level=1,
            xp_absolute=32,
            board_count=1,
            bench_count=0,
        ),
        quality=EpisodeContextQuality(
            before_exact_alignment=True,
            after_exact_alignment=True,
            hp_known_before=True,
            hp_known_after=True,
            board_known_before=True,
            board_known_after=True,
            bench_known_before=True,
            bench_known_after=True,
            board_utilization_known_before=True,
            board_utilization_known_after=True,
            scene_valid_before=True,
            scene_valid_after=True,
            economy_feasible=True,
            reconstruction_uncertainty=True,
        ),
        feature_trust=build_context_feature_trust(
            before,
            after,
        ),
        source_episode_producer_version=(
            "decision-episode-builder-0.15.0"
        ),
        producer_version="episode-context-builder-0.17.1",
    )

    path = tmp_path / "contexts.jsonl"
    path.write_text(
        value.model_dump_json() + "\n",
        encoding="utf-8",
    )

    text = format_episode_context_timeline(path)

    assert "35->28" in text
    assert "70->28" in text
    assert "6/6->7/7" in text
    assert "E/E" in text
    assert "Btrust" in text
    assert " U " in text
    assert "dHP-7" in text
    assert "not action accounting" in text
