import json
from pathlib import Path
from PIL import Image
from tft_analyzer.perception.board import BoardBenchRecognizer,BoardBenchRecognizerSettings,process_match_board_bench
from tft_analyzer.perception.layout import ROIRegistry

def registry(tmp_path):
    p=tmp_path/'layout.yaml'; p.write_text('schema_version: 1\nprofile_id: test\naspect_ratio: 1.7777777778\naspect_ratio_tolerance: 0.03\nreference_width: 1920\nreference_height: 1080\nrois:\n  board_region: {x: 0.2, y: 0.2, w: 0.6, h: 0.5}\n  bench_region: {x: 0.2, y: 0.72, w: 0.6, h: 0.15}\n',encoding='utf-8'); return ROIRegistry.from_yaml(p)

def test_attempts_persist_features(monkeypatch,tmp_path):
    match=tmp_path/'match'; fd=match/'evidence'/'frames'; fd.mkdir(parents=True); Image.new('RGB',(1920,1080),(70,90,100)).save(fd/'frame.png')
    ev=type('E',(),{'uri':'evidence/frames/frame.png','match_id':'m','timestamp_s':1.0,'evidence_id':'e'})(); rec=type('R',(),{'sequence':0,'evidence':ev})()
    import tft_analyzer.perception.board.pipeline as pipeline
    monkeypatch.setattr(pipeline,'iter_evidence_records',lambda _:iter([rec]))
    r=BoardBenchRecognizer(registry=registry(tmp_path),settings=BoardBenchRecognizerSettings(min_board_presence_score=0,min_bench_presence_score=0)); summary=process_match_board_bench(match,r)
    assert summary['producer_version']=='board-bench-occupancy-0.12.0'; assert summary['sampling_mode']=='footprint'
    item=json.loads(Path(summary['attempts_path']).read_text(encoding='utf-8').splitlines()[0]); assert 'features' in item['board_cells'][0]; assert 'edge_density' in item['bench_slots'][0]['features']; assert 'board_cell_feature_stats' in summary
