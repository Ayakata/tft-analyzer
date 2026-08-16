from tft_analyzer.features.roster_evidence.models import (
    EpisodeRosterEvidence,
    RosterChampionEvidence,
    RosterEpisodeDelta,
    RosterEvidenceSnapshot,
)
from tft_analyzer.features.roster_evidence.timeline import (
    format_roster_evidence_timeline,
)


def snapshot(
    *,
    rhaast=0,
    zoe_candidate=0,
):
    champions = []
    if rhaast:
        champions.append(
            RosterChampionEvidence(
                champion="rhaast",
                confirmed_acquired_copy_lower_bound=rhaast,
            )
        )
    if zoe_candidate:
        champions.append(
            RosterChampionEvidence(
                champion="zoe",
                candidate_acquired_copy_count=zoe_candidate,
            )
        )

    return RosterEvidenceSnapshot(
        champions=tuple(champions),
        confirmed_identity_buy_copy_count=rhaast,
        candidate_identity_buy_copy_count=zoe_candidate,
        confirmed_buy_identity_coverage=(
            rhaast / (rhaast + zoe_candidate)
            if rhaast + zoe_candidate
            else 1.0
        ),
    )


def test_timeline_distinguishes_confirmed_candidate_and_current_unknown(tmp_path):
    item = EpisodeRosterEvidence(
        roster_context_id="r1",
        match_id="m",
        decision_id="d1",
        stage_start="4-2",
        stage_end="4-2",
        start_timestamp_s=10.0,
        end_timestamp_s=20.0,
        before=snapshot(),
        delta=RosterEpisodeDelta(
            confirmed_buys={"rhaast": 2},
            candidate_buys={"zoe": 1},
            unresolved_economy_action_count=1,
            unresolved_economy_spend_min=2,
            unresolved_economy_spend_max=5,
        ),
        after=snapshot(
            rhaast=2,
            zoe_candidate=1,
        ),
        source_episode_producer_version="decision-episode-builder-0.15.0",
        source_action_producer_version="semantic-action-fusion-0.14.6",
        producer_version="roster-evidence-builder-0.20.1",
    )

    path = tmp_path / "roster.jsonl"
    path.write_text(
        item.model_dump_json() + "\n",
        encoding="utf-8",
    )

    text = format_roster_evidence_timeline(path)

    assert "rhaastx2" in text
    assert "?zoex1" in text
    assert "U1[2..5]" in text
    assert "rhaast acquired>=2" in text
    assert "historical base-copy acquisition lower bound" in text
    assert "current ownership is not established" in text
