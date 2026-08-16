from tft_analyzer.perception.players.localizer import PlayerRowLocalizer
from tft_analyzer.perception.players.models import PlayerRowCandidate


def row(index, highlight, name_match=0.0, no_name=0.0, combined=None):
    return PlayerRowCandidate(
        row_index=index,
        box=(0, index * 10, 100, index * 10 + 10),
        highlight_score=highlight,
        name_presence_score=1.0 - no_name,
        no_name_score=no_name,
        name_match_score=name_match,
        combined_self_score=(
            combined if combined is not None
            else max(highlight, name_match)
        ),
    )


def test_manual_override_wins():
    rows = [row(0, 0.1), row(1, 0.9)]

    selected = PlayerRowLocalizer.select_self_row(
        rows,
        manual_row_index=0,
    )

    assert selected.row_index == 0
    assert selected.method == "manual"


def test_name_match_preferred_when_available():
    rows = [
        row(0, 0.7, 0.2),
        row(1, 0.4, 0.91),
    ]

    selected = PlayerRowLocalizer.select_self_row(
        rows,
        player_name="player",
        min_name_match_score=0.60,
    )

    assert selected.row_index == 1
    assert selected.method == "player_name"


def test_highlight_requires_margin():
    rows = [
        row(0, 0.60),
        row(1, 0.59),
    ]

    selected = PlayerRowLocalizer.select_self_row(
        rows,
        min_highlight_score=0.24,
        min_highlight_margin=0.035,
    )

    assert selected.row_index is None


def test_no_name_cue_resolves_ambiguous_highlights():
    rows = [
        row(0, 0.60, no_name=0.15, combined=0.474),
        row(1, 0.59, no_name=0.95, combined=0.691),
    ]

    selected = PlayerRowLocalizer.select_self_row(
        rows,
        min_highlight_score=0.24,
        min_highlight_margin=0.035,
        min_combined_score=0.40,
        min_combined_margin=0.025,
    )

    assert selected.row_index == 1
    assert selected.method == "highlight_no_name"
