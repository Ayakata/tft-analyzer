from types import SimpleNamespace

from tft_analyzer.app import cli


def test_perceive_players_cli_does_not_require_shop_identity_path(
    monkeypatch,
    tmp_path,
    capsys,
):
    match_dir = tmp_path / "match"
    match_dir.mkdir()
    summary = {
        "producer_version": "players-test",
        "processed_frames": 1,
        "panel_present": 1,
        "panel_presence_rate": 1.0,
        "self_row_selected": 1,
        "self_row_selection_rate_when_panel_present": 1.0,
        "hp_parsed": 1,
        "hp_parse_rate_when_self_selected": 1.0,
        "hp_accepted": 1,
        "hp_accept_rate_when_self_selected": 1.0,
        "selection_method_counts": {"highlight": 1},
        "selected_row_counts": {"0": 1},
        "primary_candidate_used": 1,
        "fallback_candidate_used": 0,
        "primary_candidate_rate": 1.0,
        "ambiguous_self_rows": 0,
        "no_name_fallback_selected": 0,
        "max_hp_observation_gap_s": 0.0,
        "observations_path": "players.jsonl",
        "attempts_path": "players_attempts.jsonl",
        "summary_path": "players_summary.json",
    }

    monkeypatch.setattr(cli, "load_yaml", lambda _: {})
    monkeypatch.setattr(
        cli,
        "_build_player_recognizer",
        lambda _args, _cfg: object(),
    )
    monkeypatch.setattr(
        cli,
        "process_match_players",
        lambda *_args, **_kwargs: summary,
    )

    result = cli.cmd_perceive_players(
        SimpleNamespace(
            config="unused.yaml",
            match_dir=str(match_dir),
            stride=1,
            limit=1,
            player_name=None,
        )
    )

    assert result == 0
    output = capsys.readouterr().out
    assert "[OK] Attempts:     players_attempts.jsonl" in output
    assert "[OK] Summary:      players_summary.json" in output
    assert "Identity" not in output
