from __future__ import annotations
from collections import defaultdict
import hashlib
from tft_analyzer.core.models.analysis import Finding
from tft_analyzer.features.episode_context.models import EpisodePlayerContext
from .models import MatchReviewCard, MatchReviewReportSettings

def _card_id(match_id, decision_id, producer_version):
    raw=f"{match_id}|{decision_id}|{producer_version}"
    return "review-card-"+hashlib.sha1(raw.encode()).hexdigest()[:12]

def _dedupe(values):
    out=[]
    for v in values:
        if v and v not in out: out.append(v)
    return tuple(out)

def _first_metric(findings,key):
    for f in findings:
        if f.metrics.get(key) is not None: return f.metrics.get(key)
    return None

def _trusted_state(c):
    b,a=c.before,c.after; tb,ta=c.feature_trust.before,c.feature_trust.after
    def tr(v,t): return v if t.usable_for_strategy else None
    return {
      'hp_before':tr(b.hp,tb.hp),'hp_after':tr(a.hp,ta.hp),
      'gold_before':tr(b.gold,tb.gold),'gold_after':tr(a.gold,ta.gold),
      'level_before':tr(b.level,tb.level),'level_after':tr(a.level,ta.level),
      'xp_absolute_before':tr(b.xp_absolute,tb.xp_absolute),'xp_absolute_after':tr(a.xp_absolute,ta.xp_absolute),
      'board_before': b.board_count if tb.board_count.usable_for_strategy else None,
      'board_after': a.board_count if ta.board_count.usable_for_strategy else None,
      'board_capacity_before': b.board_capacity if tb.board_count.usable_for_strategy else None,
      'board_capacity_after': a.board_capacity if ta.board_count.usable_for_strategy else None,
      'board_before_semantics':tb.board_count.semantics,'board_after_semantics':ta.board_count.semantics,
    }

def _priority(findings):
    codes={f.finding_code for f in findings}
    if 'context_review_blocked_infeasible' in codes: return 'high','hard_reconstruction_conflict_blocks_strategy_review'
    if 'near_elimination_activity' in codes: return 'critical','activity_observed_inside_near_elimination_hp_threshold'
    major=sum(f.interpretation=='review_candidate' and f.severity in {'major','critical'} for f in findings)
    if major>=1: return 'high','one_or_more_major_context_review_signals'
    if 'large_spend_under_pressure' in codes or len(findings)>=2: return 'medium','multiple_or_large_pressure_review_signals'
    return 'low','single_context_review_signal'

def _title(codes):
    if 'context_review_blocked_infeasible' in codes: return 'Review blocked by economy reconstruction conflict'
    if 'near_elimination_activity' in codes: return 'Near-elimination decision window'
    if 'low_hp_level_up' in codes and 'low_hp_roll_activity' in codes: return 'Critical-HP level-and-roll window'
    if 'high_gold_under_pressure' in codes and 'low_hp_roll_activity' in codes: return 'Critical-HP roll window with substantial gold remaining'
    if 'large_spend_under_pressure' in codes and 'low_hp_roll_activity' in codes: return 'Large spend and roll under HP pressure'
    if 'trusted_board_below_capacity' in codes: return 'Trusted board-capacity review window'
    return 'Context-aware review window'

_FACT={
'economy_commitment_under_pressure':'Economy commitment occurred while HP was inside the pressure threshold.',
'large_spend_under_pressure':'A large observed economy commitment occurred under HP pressure.',
'low_hp_roll_activity':'Shop refresh activity was observed under HP pressure.',
'low_hp_level_up':'The trusted boundary level increased under HP pressure.',
'high_gold_under_pressure':'Substantial trusted gold remained while HP was inside the critical threshold.',
'near_elimination_activity':'Semantic activity was observed inside the near-elimination HP threshold.',
'trusted_board_below_capacity':'A trusted exact board boundary was below the current level capacity.',
'context_review_blocked_infeasible':'Economy constraints are internally inconsistent, so strategic review is suppressed.',
}

def _facts(findings,state,activity):
    facts=[_FACT[f.finding_code] for f in findings if f.finding_code in _FACT]
    hp=activity.get('pressure_hp'); spend=activity.get('observed_spend'); rmin=activity.get('reroll_count_min'); rmax=activity.get('reroll_count_max')
    if hp is not None: facts.append(f'Pressure HP: {hp}.')
    if spend is not None: facts.append(f'Observed action spend: {spend}g.')
    if rmin: facts.append(f"Refresh count is bounded at {rmin}..{'?' if rmax is None else rmax}.")
    lb,la=state.get('level_before'),state.get('level_after')
    if lb is not None and la is not None and lb!=la: facts.append(f'Trusted level changed {lb}->{la}.')
    ga=state.get('gold_after')
    if ga is not None: facts.append(f'Trusted post-episode gold: {ga}.')
    ba,cap=state.get('board_after'),state.get('board_capacity_after')
    if ba is not None and cap is not None: facts.append(f'Trusted post-episode board: {ba}/{cap}.')
    return _dedupe(facts)

def _why(findings,card_type):
    if card_type=='data_quality': return ('The evidence is contradictory enough that strategic interpretation would be unsafe.','Review the upstream shop/gold/action reconstruction before using this episode for coaching.')
    codes={f.finding_code for f in findings}; out=[]
    if codes & {'large_spend_under_pressure','economy_commitment_under_pressure'}: out.append('Resources were committed while HP pressure was already meaningful.')
    if 'low_hp_roll_activity' in codes: out.append('The episode contains roll activity whose stopping point becomes strategically important at low HP.')
    if 'low_hp_level_up' in codes: out.append('The episode combines survival pressure with a tempo investment into level.')
    if 'high_gold_under_pressure' in codes: out.append('A substantial gold reserve remains while survival pressure is high.')
    if 'near_elimination_activity' in codes: out.append('Actions occurred very close to elimination, making the window high-value for post-game review.')
    if 'trusted_board_below_capacity' in codes: out.append('The board-capacity observation is one of the rare boundaries trusted literally by the perception stack.')
    return _dedupe(out)

def _summary(findings,card_type,priority):
    if card_type=='data_quality': return 'Strategic review is intentionally blocked because the episode contains an infeasible economy reconstruction.'
    codes={f.finding_code for f in findings}; parts=[]
    if 'low_hp_level_up' in codes: parts.append('level-up')
    if 'low_hp_roll_activity' in codes: parts.append('roll activity')
    if codes & {'large_spend_under_pressure','economy_commitment_under_pressure'}: parts.append('economy commitment')
    if 'high_gold_under_pressure' in codes: parts.append('substantial remaining gold')
    if 'near_elimination_activity' in codes: parts.append('near-elimination activity')
    if 'trusted_board_below_capacity' in codes: parts.append('trusted board-capacity gap')
    return f"{priority.capitalize()}-priority review window containing {', '.join(parts) if parts else 'context-aware activity'}. Priority measures review value, not decision quality."

def build_match_review_cards(findings, contexts, settings):
    byctx={c.decision_id:c for c in contexts}; grouped=defaultdict(list)
    for f in findings:
        if f.decision_id and f.interpretation in {'review_candidate','data_quality'}: grouped[f.decision_id].append(f)
    cards=[]
    for did,fs in grouped.items():
        c=byctx.get(did)
        if c is None: continue
        dq=any(f.interpretation=='data_quality' for f in fs); card_type='data_quality' if dq else 'gameplay_review'
        if dq and not settings.include_data_quality_cards: continue
        priority,reason=_priority(fs); codes={f.finding_code for f in fs}; state=_trusted_state(c)
        activity={k:_first_metric(fs,k) for k in ['pressure_hp','observed_spend','reroll_count_min','reroll_count_max','action_count','economy_infeasible','reconstruction_uncertainty']}
        limits=_dedupe(x for f in fs for x in f.limitations)
        if card_type=='gameplay_review': limits=_dedupe(list(limits)+['Review priority is not a decision score or mistake probability.','Board strength, unit identities/upgrades, items, traits, opponent boards, streak and patch-specific policy are not yet modeled.'])
        evid=_dedupe(x for f in fs for x in f.evidence_ids)
        start=min(f.start_timestamp_s or 0.0 for f in fs); end=max((f.end_timestamp_s if f.end_timestamp_s is not None else start) for f in fs)
        cards.append(MatchReviewCard(card_id=_card_id(c.match_id,did,settings.producer_version),match_id=c.match_id,decision_id=did,card_type=card_type,priority=priority,priority_reason=reason,stage=c.stage_end or c.stage_start,start_timestamp_s=start,end_timestamp_s=end,title=_title(codes),summary=_summary(fs,card_type,priority),state=state,activity=activity,observed_facts=_facts(fs,state,activity),why_review=_why(fs,card_type),limitations=limits,source_finding_ids=tuple(f.finding_id for f in fs),source_finding_codes=tuple(f.finding_code for f in fs if f.finding_code),evidence_ids=evid,producer_version=settings.producer_version))
    cards.sort(key=lambda c:c.start_timestamp_s)
    return cards
