from tft_analyzer.app.cli import _optional_bool


def test_optional_bool_preserves_none():
    assert _optional_bool(None) is None
    assert _optional_bool(True) is True
    assert _optional_bool(False) is False
