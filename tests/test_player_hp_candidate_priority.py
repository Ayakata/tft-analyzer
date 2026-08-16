from tft_analyzer.perception.players.models import HPAttempt
from tft_analyzer.perception.players.recognizer import (
    PlayerListRecognizer,
    PlayerListRecognizerSettings,
)


def attempt(candidate, hp, conf):
    return HPAttempt(
        row_index=0,
        candidate_name=candidate,
        candidate_box=(0, 0, 10, 10),
        variant="test",
        raw_text=str(hp) if hp is not None else "",
        ocr_score=conf,
        hp=hp,
        parser_confidence=1.0 if hp is not None else 0.0,
        confidence=conf,
    )


def make_recognizer():
    recognizer = object.__new__(PlayerListRecognizer)
    recognizer.settings = PlayerListRecognizerSettings()
    return recognizer


def test_primary_candidate_beats_higher_confidence_fallback():
    recognizer = make_recognizer()

    best = recognizer._best_hp_attempt(
        [
            attempt("hp_candidate_0", 100, 0.67),
            attempt("hp_candidate_2", 6, 0.85),
        ]
    )

    assert best.hp == 100
    assert best.candidate_name == "hp_candidate_0"


def test_fallback_uses_positional_prior_when_primary_weak():
    recognizer = make_recognizer()

    best = recognizer._best_hp_attempt(
        [
            attempt("hp_candidate_0", 100, 0.45),
            attempt("hp_candidate_1", 93, 0.90),
            attempt("hp_candidate_2", 6, 0.95),
        ]
    )

    assert best.hp == 93
    assert best.candidate_name == "hp_candidate_1"
