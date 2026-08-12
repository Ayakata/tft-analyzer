from tft_analyzer.perception.ocr.rapidocr_engine import RapidOCREngine


def test_rapidocr_adapter_is_lazy():
    engine = RapidOCREngine()
    assert engine.name == "rapidocr"
    assert engine._engine is None
