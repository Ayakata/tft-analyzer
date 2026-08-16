from tft_analyzer.core.models.analysis import Finding
from tft_analyzer.features.episode_context.models import (
    EpisodeBoundaryTrust, EpisodeContextFeatureTrust, EpisodeContextQuality,
    EpisodeFeatureTrust, EpisodePlayerContext, EpisodePlayerStateDelta,
    EpisodePlayerStateFeature,
)
from tft_analyzer.reports import MatchReviewReportSettings, build_match_review_cards
from tft_analyzer.reports.review.render import render_review_markdown


def ft(usable=True, semantics='exact'):
    return EpisodeFeatureTrust(known=True, semantics=semantics, usable_for_strategy=usable, reason='test', source='test')


def bt(board_usable=False, board_sem='lower_bound'):
    e=ft(); b=ft(board_usable, board_sem)
    return EpisodeBoundaryTrust(hp=e,gold=e,level=e,xp_absolute=e,board_count=b,board_utilization=b,bench_count=ft(False,'lower_bound'))


def context(decision_id='d1', stage='5-2', hp=17, gb=33, ga=20, lb=7, la=8, board_after=7, board_usable=False, board_sem='lower_bound'):
    before=EpisodePlayerStateFeature(timestamp_s=0,evidence_id='e0',stage=stage,hp=hp,gold=gb,level=lb,xp_absolute=128,board_count=7,board_capacity=lb,board_utilization=1.0,bench_count=7)
    after=EpisodePlayerStateFeature(timestamp_s=10,evidence_id='e1',stage=stage,hp=hp,gold=ga,level=la,xp_absolute=136,board_count=board_after,board_capacity=la,board_utilization=board_after/la,bench_count=7)
    return EpisodePlayerContext(context_id='c-'+decision_id,decision_id=decision_id,match_id='m',stage_start=stage,stage_end=stage,before=before,after=after,delta=EpisodePlayerStateDelta(hp=0,gold=ga-gb,level=la-lb,xp_absolute=8,board_count=0,bench_count=0),quality=EpisodeContextQuality(economy_feasible=True),feature_trust=EpisodeContextFeatureTrust(before=bt(),after=bt(board_usable,board_sem)),source_episode_producer_version='decision-episode-builder-0.15.0',producer_version='episode-context-builder-0.17.1')


def finding(code, *, decision_id='d1', severity='major', interpretation='review_candidate', hp=17, spend=13, ga=20, lb=7, la=8, rmin=1, rmax=2):
    return Finding(finding_id='f-'+code,match_id='m',decision_id=decision_id,finding_code=code,producer_version='context-review-analyzer-0.18.0',category='review.context',title=code,interpretation=interpretation,stage='5-2',start_timestamp_s=0,end_timestamp_s=10,severity=severity,confidence=.9,metrics={'pressure_hp':hp,'observed_spend':spend,'gold_after':ga,'level_before':lb,'level_after':la,'reroll_count_min':rmin,'reroll_count_max':rmax,'action_count':2,'economy_infeasible':interpretation=='data_quality'},limitations=('No board strength yet.',),evidence_ids=('e0','e1'))


def test_three_findings_collapse_to_one_high_priority_card():
    findings=[finding('economy_commitment_under_pressure',severity='minor'),finding('low_hp_roll_activity'),finding('low_hp_level_up')]
    cards=build_match_review_cards(findings,[context()],MatchReviewReportSettings())
    assert len(cards)==1
    card=cards[0]
    assert card.card_type=='gameplay_review'
    assert card.priority=='high'
    assert card.title=='Critical-HP level-and-roll window'
    assert set(card.source_finding_codes)=={'economy_commitment_under_pressure','low_hp_roll_activity','low_hp_level_up'}
    assert card.decision_grade is None
    assert card.state['gold_before']==33 and card.state['gold_after']==20


def test_near_elimination_becomes_critical_review_priority_not_grade():
    findings=[finding('high_gold_under_pressure',decision_id='d2',hp=6,spend=0,ga=62,lb=8,la=8,rmin=0,rmax=0),finding('near_elimination_activity',decision_id='d2',hp=6,spend=0,ga=62,lb=8,la=8,rmin=0,rmax=0)]
    cards=build_match_review_cards(findings,[context('d2','6-1',6,42,62,8,8,8,True,'exact')],MatchReviewReportSettings())
    assert len(cards)==1 and cards[0].priority=='critical'
    assert cards[0].decision_grade is None
    assert cards[0].state['board_after']==8


def test_data_quality_block_stays_separate_card():
    f=finding('context_review_blocked_infeasible',interpretation='data_quality',hp=93,spend=1,ga=10,lb=5,la=5,rmin=0,rmax=0)
    cards=build_match_review_cards([f],[context(hp=93,gb=11,ga=10,lb=5,la=5)],MatchReviewReportSettings())
    assert len(cards)==1
    assert cards[0].card_type=='data_quality'
    assert cards[0].priority=='high'
    assert 'blocked' in cards[0].summary.lower()


def test_untrusted_board_not_promoted_to_card_state_fact():
    cards=build_match_review_cards([finding('low_hp_roll_activity')],[context(board_after=4,board_usable=False,board_sem='lower_bound')],MatchReviewReportSettings())
    assert cards[0].state['board_after'] is None
    assert not any('board:' in x.lower() for x in cards[0].observed_facts)


def test_markdown_uses_review_not_grade_language():
    cards=build_match_review_cards([finding('low_hp_roll_activity')],[context()],MatchReviewReportSettings())
    md=render_review_markdown(cards,match_id='m',game_context={'set_id':'TFT17','patch':'16.16'},producer_version='match-review-report-0.19.0')
    assert '# TFT Match Review' in md
    assert 'not a decision grade' in md
    assert '[REVIEW / HIGH]' in md


def test_canonical_shape_11_findings_collapse_to_five_cards():
    findings = [
        finding('context_review_blocked_infeasible', decision_id='qa', interpretation='data_quality', hp=93, spend=1, ga=10, lb=5, la=5, rmin=0, rmax=0),
        finding('large_spend_under_pressure', decision_id='d46', severity='minor', hp=35, spend=29, ga=35, lb=7, la=7, rmin=2, rmax=12),
        finding('low_hp_roll_activity', decision_id='d46', severity='minor', hp=35, spend=29, ga=35, lb=7, la=7, rmin=2, rmax=12),
        finding('economy_commitment_under_pressure', decision_id='d52', severity='minor'),
        finding('low_hp_roll_activity', decision_id='d52'),
        finding('low_hp_level_up', decision_id='d52'),
        finding('economy_commitment_under_pressure', decision_id='d56', severity='minor', hp=17, spend=10, ga=32, lb=8, la=8, rmin=1, rmax=5),
        finding('low_hp_roll_activity', decision_id='d56', hp=17, spend=10, ga=32, lb=8, la=8, rmin=1, rmax=5),
        finding('high_gold_under_pressure', decision_id='d56', hp=17, spend=10, ga=32, lb=8, la=8, rmin=1, rmax=5),
        finding('high_gold_under_pressure', decision_id='d61', hp=6, spend=0, ga=62, lb=8, la=8, rmin=0, rmax=0),
        finding('near_elimination_activity', decision_id='d61', hp=6, spend=0, ga=62, lb=8, la=8, rmin=0, rmax=0),
    ]
    contexts = [
        context('qa', '2-6', 93, 11, 10, 5, 5),
        context('d46', '4-6', 35, 64, 35, 7, 7),
        context('d52', '5-2', 17, 33, 20, 7, 8),
        context('d56', '5-6', 17, 42, 32, 8, 8),
        context('d61', '6-1', 6, 42, 62, 8, 8, 8, True, 'exact'),
    ]
    cards = build_match_review_cards(findings, contexts, MatchReviewReportSettings())
    assert len(cards) == 5
    assert sum(c.card_type == 'gameplay_review' for c in cards) == 4
    assert sum(c.card_type == 'data_quality' for c in cards) == 1
    by_id = {c.decision_id: c for c in cards}
    assert by_id['d46'].priority == 'medium'
    assert by_id['d52'].priority == 'high'
    assert by_id['d56'].priority == 'high'
    assert by_id['d61'].priority == 'critical'


def test_review_report_pipeline_writes_jsonl_summary_and_markdown(tmp_path):
    import json
    from pathlib import Path
    from tft_analyzer.reports import build_match_review_report

    match = tmp_path / 'match'
    analysis = match / 'analysis'
    features = match / 'features'
    analysis.mkdir(parents=True)
    features.mkdir()

    ctx = context()
    contexts_path = features / 'episode-context-builder-0.17.1.jsonl'
    contexts_path.write_text(ctx.model_dump_json() + '\n', encoding='utf-8')
    context_summary_path = features / 'episode-context-builder-0.17.1_summary.json'
    context_summary_path.write_text(json.dumps({
        'producer_version': 'episode-context-builder-0.17.1',
        'trust_semantics_version': 1,
        'contexts_path': str(contexts_path),
        'game_context': {'set_id': 'TFT17', 'patch': '16.16'},
    }), encoding='utf-8')

    fs = [
        finding('economy_commitment_under_pressure', severity='minor'),
        finding('low_hp_roll_activity'),
        finding('low_hp_level_up'),
    ]
    findings_path = analysis / 'context-review-analyzer-0.18.0.jsonl'
    findings_path.write_text(''.join(f.model_dump_json() + '\n' for f in fs), encoding='utf-8')
    review_summary_path = analysis / 'context-review-analyzer-0.18.0_summary.json'
    review_summary_path.write_text(json.dumps({
        'producer_version': 'context-review-analyzer-0.18.0',
        'decision_grade_count': 0,
        'findings_path': str(findings_path),
        'input_context_summary_path': str(context_summary_path),
        'game_context': {'set_id': 'TFT17', 'patch': '16.16'},
    }), encoding='utf-8')

    summary = build_match_review_report(
        match,
        MatchReviewReportSettings(),
        context_review_summary_path=review_summary_path,
    )
    assert summary['card_count'] == 1
    assert summary['gameplay_review_card_count'] == 1
    assert summary['data_quality_card_count'] == 0
    assert summary['decision_grade_count'] == 0
    assert Path(summary['cards_path']).is_file()
    assert Path(summary['summary_path']).is_file()
    md = Path(summary['markdown_path']).read_text(encoding='utf-8')
    assert '[REVIEW / HIGH]' in md
    assert 'TFT17' in md
