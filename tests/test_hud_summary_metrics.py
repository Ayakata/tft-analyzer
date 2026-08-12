def test_presence_parse_acceptance_denominators_are_distinct():
    frames = 20
    present = 12
    parsed = 12
    accepted = 11

    assert present / frames == 0.6
    assert parsed / present == 1.0
    assert accepted / present == 11 / 12
    assert accepted <= parsed <= present <= frames
