from __future__ import annotations
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from PIL import Image
from tft_analyzer.storage import iter_evidence_records, write_observations_atomic
from .recognizer import BoardBenchRecognizer

AGGREGATE_PRODUCER_VERSION='board-bench-occupancy-0.12.0'
def _signature(items,key): return tuple(getattr(x,key) for x in items)
def _features(f): return {k:float(getattr(f,k)) for k in f.__dataclass_fields__}
def _stats(vals):
    if not vals: return {'mean':0.0,'q10':0.0,'q50':0.0,'q90':0.0}
    v=sorted(map(float,vals))
    def q(p):
        if len(v)==1:return v[0]
        x=p*(len(v)-1); lo=int(x); hi=min(lo+1,len(v)-1); a=x-lo
        return v[lo]*(1-a)+v[hi]*a
    return {'mean':sum(v)/len(v),'q10':q(.1),'q50':q(.5),'q90':q(.9)}
def process_match_board_bench(match_dir:Path|str,recognizer:BoardBenchRecognizer,*,stride:int=1,limit:int|None=None)->dict[str,object]:
    match_dir=Path(match_dir); stride=max(1,int(stride)); board_obs=[]; bench_obs=[]; attempts=[]; processed=0; board_present=0; bench_present=0
    board_status=Counter(); bench_status=Counter(); board_occ_counts=[]; bench_occ_counts=[]; board_unc_counts=[]; bench_unc_counts=[]
    cell_status=defaultdict(Counter); slot_status=defaultdict(Counter); cell_scores=defaultdict(list); slot_scores=defaultdict(list)
    cell_features=defaultdict(lambda:defaultdict(list)); slot_features=defaultdict(lambda:defaultdict(list))
    board_changes=0; bench_changes=0; prev_board=None; prev_bench=None; board_times=[]; bench_times=[]
    for i,record in enumerate(iter_evidence_records(match_dir)):
        if i%stride: continue
        if limit is not None and processed>=limit: break
        image_path=match_dir/record.evidence.uri
        if not image_path.exists():
            attempts.append({'sequence':record.sequence,'timestamp_s':record.evidence.timestamp_s,'evidence_id':record.evidence.evidence_id,'error':f'missing_image:{image_path}'}); processed+=1; continue
        with Image.open(image_path) as src:image=src.convert('RGB')
        result=recognizer.recognize(image,match_id=record.evidence.match_id,timestamp_s=record.evidence.timestamp_s,evidence_id=record.evidence.evidence_id); processed+=1
        board_present+=int(result.board_present); bench_present+=int(result.bench_present)
        for c in result.board_cells:
            k=f'{c.row},{c.col}'; board_status[c.status]+=1; cell_status[k][c.status]+=1; cell_scores[k].append(c.score)
            for fn,fv in _features(c.features).items(): cell_features[k][fn].append(fv)
        for c in result.bench_slots:
            k=str(c.slot_index); bench_status[c.status]+=1; slot_status[k][c.status]+=1; slot_scores[k].append(c.score)
            for fn,fv in _features(c.features).items(): slot_features[k][fn].append(fv)
        if result.board_cells:
            board_occ_counts.append(result.board_occupied_count); board_unc_counts.append(result.board_uncertain_count); sig=_signature(result.board_cells,'status'); board_changes+=int(prev_board is not None and sig!=prev_board); prev_board=sig
        if result.bench_slots:
            bench_occ_counts.append(result.bench_occupied_count); bench_unc_counts.append(result.bench_uncertain_count); sig=_signature(result.bench_slots,'status'); bench_changes+=int(prev_bench is not None and sig!=prev_bench); prev_bench=sig
        for obs in result.observations:
            if obs.kind.value=='board': board_obs.append(obs); board_times.append(float(obs.timestamp_s))
            elif obs.kind.value=='bench': bench_obs.append(obs); bench_times.append(float(obs.timestamp_s))
        attempts.append({'sequence':record.sequence,'timestamp_s':record.evidence.timestamp_s,'evidence_id':record.evidence.evidence_id,'sampling_mode':'footprint',
          'board_present':result.board_present,'board_presence_score':result.board_presence_score,'board_occupied_count':result.board_occupied_count,'board_uncertain_count':result.board_uncertain_count,
          'bench_present':result.bench_present,'bench_presence_score':result.bench_presence_score,'bench_occupied_count':result.bench_occupied_count,'bench_uncertain_count':result.bench_uncertain_count,
          'board_cells':[{'row':c.row,'col':c.col,'status':c.status,'score':c.score,'confidence':c.confidence,'footprint_box':c.footprint_box,'context_box':c.context_box,'features':_features(c.features)} for c in result.board_cells],
          'bench_slots':[{'slot_index':c.slot_index,'status':c.status,'score':c.score,'confidence':c.confidence,'footprint_box':c.footprint_box,'context_box':c.context_box,'features':_features(c.features)} for c in result.bench_slots]})
    od=match_dir/'observations'; od.mkdir(parents=True,exist_ok=True)
    bp=od/f'{recognizer.settings.board_producer_version}.jsonl'; xp=od/f'{recognizer.settings.bench_producer_version}.jsonl'; ap=od/f'{AGGREGATE_PRODUCER_VERSION}_attempts.jsonl'; sp=od/f'{AGGREGATE_PRODUCER_VERSION}_summary.json'
    bc=write_observations_atomic(bp,board_obs); xc=write_observations_atomic(xp,bench_obs)
    tmp=ap.with_suffix(ap.suffix+'.tmp')
    with tmp.open('w',encoding='utf-8',newline='\n') as f:
        for a in attempts:f.write(json.dumps(a,ensure_ascii=False)+'\n')
    tmp.replace(ap)
    def maxgap(v):return max((b-a for a,b in zip(v,v[1:])),default=0.0)
    bt=sum(board_status.values()); xt=sum(bench_status.values())
    summary={'schema_version':2,'producer_version':AGGREGATE_PRODUCER_VERSION,'sampling_mode':'footprint','processed_frames':processed,'board_observation_count':bc,'bench_observation_count':xc,
      'board_present':board_present,'board_presence_rate':board_present/processed if processed else 0.0,'bench_present':bench_present,'bench_presence_rate':bench_present/processed if processed else 0.0,
      'board_status_counts':dict(board_status),'bench_status_counts':dict(bench_status),'board_uncertain_rate':board_status['uncertain']/bt if bt else 0.0,'bench_uncertain_rate':bench_status['uncertain']/xt if xt else 0.0,
      'mean_board_occupied_count':mean(board_occ_counts) if board_occ_counts else 0.0,'mean_board_uncertain_count':mean(board_unc_counts) if board_unc_counts else 0.0,'mean_bench_occupied_count':mean(bench_occ_counts) if bench_occ_counts else 0.0,'mean_bench_uncertain_count':mean(bench_unc_counts) if bench_unc_counts else 0.0,
      'board_snapshot_changes':board_changes,'bench_snapshot_changes':bench_changes,'board_cell_status_counts':{k:dict(v) for k,v in cell_status.items()},'bench_slot_status_counts':{k:dict(v) for k,v in slot_status.items()},
      'board_cell_score_stats':{k:_stats(v) for k,v in cell_scores.items()},'bench_slot_score_stats':{k:_stats(v) for k,v in slot_scores.items()},
      'board_cell_feature_stats':{k:{fn:_stats(vals) for fn,vals in fs.items()} for k,fs in cell_features.items()},'bench_slot_feature_stats':{k:{fn:_stats(vals) for fn,vals in fs.items()} for k,fs in slot_features.items()},
      'max_board_observation_gap_s':maxgap(board_times),'max_bench_observation_gap_s':maxgap(bench_times),'board_observations_path':str(bp),'bench_observations_path':str(xp),'attempts_path':str(ap),'summary_path':str(sp)}
    sp.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8'); return summary
