from tft_analyzer import __version__
from tft_analyzer.core.models import GameState, MatchManifest


def main() -> None:
    print(f"TFT Analyzer {__version__}")
    print("Stage 0 domain contracts loaded.")
    print(f"GameState schema version: {GameState.model_fields['schema_version'].default}")
    print(f"MatchManifest schema version: {MatchManifest.model_fields['schema_version'].default}")


if __name__ == "__main__":
    main()
