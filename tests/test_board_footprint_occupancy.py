from pathlib import Path
import numpy as np
from PIL import Image
from tft_analyzer.perception.board import BoardBenchRecognizer,BoardBenchRecognizerSettings
from tft_analyzer.perception.board.features import occupancy_features
from tft_analyzer.perception.layout import ROIRegistry

def registry(tmp_path):
    p=tmp_path/'layout.yaml'; p.write_text('schema_version: 1\nprofile_id: test\naspect_ratio: 1.7777777778\naspect_ratio_tolerance: 0.03\nreference_width: 1920\nreference_height: 1080\nrois:\n  board_region: {x: 0.2, y: 0.2, w: 0.6, h: 0.5}\n  bench_region: {x: 0.2, y: 0.72, w: 0.6, h: 0.15}\n',encoding='utf-8'); return ROIRegistry.from_yaml(p)

def test_bench_samples_footprint_not_context(tmp_path):
    r=BoardBenchRecognizer(registry=registry(tmp_path),settings=BoardBenchRecognizerSettings(min_board_presence_score=0,min_bench_presence_score=0)); im=Image.new('RGB',(1920,1080),(45,55,60)); res=r.recognize(im,match_id='m',timestamp_s=1,evidence_id='e'); s=res.bench_slots[0]
    assert s.footprint_box==r.bench_footprint_box(s.center,1920,1080); assert s.box==r.bench_context_box(s.center,1920,1080); assert s.box[1] < s.footprint_box[1]

def test_hex_mask_excludes_corners(tmp_path):
    r=BoardBenchRecognizer(registry=registry(tmp_path),settings=BoardBenchRecognizerSettings()); center=(960,600); box=r.board_footprint_box(2,center,1920,1080); mask=r.board_footprint_mask(2,center,box,1920,1080); a=np.asarray(mask); assert a[0,0]==0; assert a[a.shape[0]//2,a.shape[1]//2]==255

def test_masked_features_ignore_noisy_corners():
    a=np.full((80,120,3),30,dtype=np.uint8); a[:20,:20]=255; a[-20:,-20:]=255; m=np.zeros((80,120),dtype=np.uint8); m[20:60,25:95]=255
    masked=occupancy_features(Image.fromarray(a),mask=m); full=occupancy_features(Image.fromarray(a)); assert masked.contrast < full.contrast; assert masked.bright_fraction < full.bright_fraction
