from tft_analyzer.perception.hud.parsers import (
    parse_gold,
    parse_level,
    parse_stage,
    parse_xp,
)


def test_parse_stage_normal_and_confusions():
    assert parse_stage("3-3").value == {"stage": 3, "round": 3}
    assert parse_stage("3:4").normalized_text == "3-4"
    assert parse_stage("34").value == {"stage": 3, "round": 4}


def test_parse_gold():
    assert parse_gold("38").value == {"gold": 38}
    assert parse_gold("O").value == {"gold": 0}
    assert parse_gold("gold 51").value == {"gold": 51}


def test_parse_level():
    assert parse_level("Lvl. 5").value == {"level": 5}
    assert parse_level("Lv 10").value == {"level": 10}
    assert parse_level("11") is None


def test_parse_xp():
    assert parse_xp("12/20").value == {"current": 12, "required": 20}
    assert parse_xp("0|10").value == {"current": 0, "required": 10}
    assert parse_xp("12 20").value == {"current": 12, "required": 20}
    assert parse_xp("21/20") is None
