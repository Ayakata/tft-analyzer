from tft_analyzer.perception.shop.parsers import normalize_shop_name


def test_normalize_simple_name():
    assert normalize_shop_name("Pantheon") == ("pantheon", 1.0)


def test_normalize_spaces_and_apostrophe():
    assert normalize_shop_name("K'Sante") == ("ksante", 1.0)
    assert normalize_shop_name("Miss Fortune") == ("missfortune", 1.0)


def test_reject_numeric_noise():
    assert normalize_shop_name("123") == (None, 0.0)
