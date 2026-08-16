from tft_analyzer.tracking.board.background import (
    classify_foreground,
    fit_background_models,
    foreground_score,
)


def sample(score, contrast, edge):
    return {
        "score": score,
        "features": {
            "contrast": contrast,
            "edge_density": edge,
            "saturation": 0.10,
            "bright_fraction": 0.01,
            "center_edge_delta": 0.0,
            "center_saturation_delta": 0.0,
        },
    }


def test_background_model_is_position_specific():
    samples = {
        "0": [sample(0.10 + i * .005, 8 + i * .1, .002) for i in range(30)],
        "1": [sample(0.20 + i * .005, 24 + i * .1, .010) for i in range(30)],
    }
    models = fit_background_models(samples, source_quantile=.22, min_candidates=6)
    assert models["0"].feature_medians["contrast"] < models["1"].feature_medians["contrast"]
    assert models["0"].position == "0"
    assert models["1"].position == "1"


def test_foreground_deviation_scores_above_background():
    background = [sample(.15 + i*.003, 10 + i*.1, .004) for i in range(30)]
    model = fit_background_models({"0": background}, min_candidates=8)["0"]
    bg = foreground_score(sample(.16, 10.2, .004), model)
    fg = foreground_score(sample(.75, 48.0, .18), model)
    assert bg < .34
    assert fg > .58
    assert classify_foreground(bg)[0] == "empty"
    assert classify_foreground(fg)[0] == "occupied"
