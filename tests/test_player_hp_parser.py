from tft_analyzer.perception.players.parsers import parse_player_hp


def test_parse_clean_hp():
    assert parse_player_hp("87") == (87, 1.0)


def test_parse_common_ocr_substitution():
    assert parse_player_hp("IOO") == (100, 1.0)


def test_parse_mixed_text_is_lower_confidence():
    hp, confidence = parse_player_hp("HP 73")
    assert hp == 73
    assert confidence == 0.80


def test_parse_rejects_out_of_range():
    assert parse_player_hp("999", max_hp=250) == (None, 0.0)
