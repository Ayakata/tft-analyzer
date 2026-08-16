from pathlib import Path
from PIL import Image
from tft_analyzer.core.enums import ObservationKind
from tft_analyzer.perception.board import BoardBenchRecognizer, BoardBenchRecognizerSettings
from tft_analyzer.perception.layout import ROIRegistry

def test_recognizer_emits_board_and_bench_observations(tmp_path):
    layout=tmp_path/'layout.yaml'
    layout.write_text("schema_version: 1\nprofile_id: test\naspect_ratio: 1.7777777778\naspect_ratio_tolerance: 0.03\nreference_width: 1920\nreference_height: 1080\nrois:\n  board_region: {x: 0.2, y: 0.2, w: 0.6, h: 0.5}\n  bench_region: {x: 0.2, y: 0.72, w: 0.6, h: 0.15}\n")
    image=Image.new('RGB',(1920,1080),(80,100,120))
    r=BoardBenchRecognizer(registry=ROIRegistry.from_yaml(layout),settings=BoardBenchRecognizerSettings(min_board_presence_score=0.0,min_bench_presence_score=0.0))
    result=r.recognize(image,match_id='m',timestamp_s=1,evidence_id='e')
    assert len(result.board_cells)==28
    assert len(result.bench_slots)==9
    assert {o.kind for o in result.observations}=={ObservationKind.BOARD,ObservationKind.BENCH}
