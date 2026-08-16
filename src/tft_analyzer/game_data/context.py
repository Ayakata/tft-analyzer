from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .catalog import (
    ChampionCostCatalog,
    infer_set_from_roster,
)
from .models import GameContext


def normalize_set_id(value: str) -> str:
    text = str(value).strip().upper()
    if not text.startswith("TFT"):
        if text.isdigit():
            text = f"TFT{text}"
        elif text.lower().startswith("set"):
            suffix = text[3:].strip()
            text = f"TFT{suffix}"
    return text


def normalize_patch(value: str) -> str:
    parts = str(value).strip().split(".")
    if len(parts) < 2:
        raise ValueError(
            f"Patch must look like MAJOR.MINOR, got {value!r}"
        )
    return f"{int(parts[0])}.{int(parts[1])}"


def patch_from_ddragon_version(version: str) -> str:
    return normalize_patch(version)


def validate_patch_matches_ddragon(
    patch: str,
    data_dragon_version: str,
) -> None:
    normalized_patch = normalize_patch(patch)
    ddragon_patch = patch_from_ddragon_version(
        data_dragon_version
    )
    if normalized_patch != ddragon_patch:
        raise ValueError(
            "Game patch does not match active Data Dragon catalog: "
            f"patch={normalized_patch}, "
            f"catalog={data_dragon_version}"
        )


def game_context_path(match_dir: Path | str) -> Path:
    return Path(match_dir) / "game_context.json"


def load_game_context(
    match_dir: Path | str,
) -> GameContext | None:
    path = game_context_path(match_dir)
    if not path.exists():
        return None
    return GameContext.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def save_game_context(
    match_dir: Path | str,
    context: GameContext,
) -> Path:
    path = game_context_path(match_dir)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        context.model_dump_json(indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)
    return path


def resolve_game_context(
    *,
    match_dir: Path | str,
    catalog: ChampionCostCatalog,
    observed_roster_names: list[str],
    explicit_set: str | None = None,
    explicit_patch: str | None = None,
    config_set: str | None = None,
    config_patch: str | None = None,
    allow_auto_inference: bool = True,
    force_context: bool = False,
) -> GameContext:
    existing = load_game_context(match_dir)

    if explicit_set is not None:
        set_id = normalize_set_id(explicit_set)
        source = "explicit_cli"

        if (
            existing is not None
            and existing.set_id != set_id
            and not force_context
        ):
            raise ValueError(
                "Existing game_context.json uses "
                f"{existing.set_id}, requested {set_id}. "
                "Pass --force-game-context to replace it."
            )

    elif existing is not None:
        # Existing match metadata has priority over global config/fallback.
        validate_patch_matches_ddragon(
            existing.patch,
            catalog.snapshot.version,
        )
        if (
            existing.catalog_source_sha256
            != catalog.snapshot.source_sha256
        ):
            raise ValueError(
                "Existing game context was produced with a different "
                "catalog SHA-256. Pass an explicit --set/--patch with "
                "--force-game-context to rebind this match."
            )
        return existing

    elif config_set is not None:
        set_id = normalize_set_id(config_set)
        source = "config"

    elif allow_auto_inference:
        (
            inferred_set,
            confidence,
            margin,
            candidates,
        ) = infer_set_from_roster(
            catalog,
            observed_roster_names,
        )
        if inferred_set is None:
            raise ValueError(
                "Could not infer TFT set confidently from roster evidence. "
                "Pass --set TFT17 (or another explicit set)."
            )
        set_id = inferred_set
        source = "auto_inferred"

    else:
        raise ValueError(
            "TFT set is not specified and auto inference is disabled. "
            "Pass --set TFT17."
        )

    patch_value = (
        explicit_patch
        or config_patch
        or (
            existing.patch
            if existing is not None
            else patch_from_ddragon_version(
                catalog.snapshot.version
            )
        )
    )
    patch = normalize_patch(patch_value)
    validate_patch_matches_ddragon(
        patch,
        catalog.snapshot.version,
    )

    scoped_count = catalog.scoped_champion_count(
        set_id
    )
    if scoped_count == 0:
        raise ValueError(
            f"Set {set_id} has no champions in catalog "
            f"{catalog.snapshot.version}"
        )

    confidence = None
    margin = None
    candidates = ()

    if source == "auto_inferred":
        (
            _,
            confidence,
            margin,
            candidates,
        ) = infer_set_from_roster(
            catalog,
            observed_roster_names,
        )

    context = GameContext(
        set_id=set_id,
        patch=patch,
        data_dragon_version=(
            catalog.snapshot.version
        ),
        resolution_source=source,
        catalog_provider=catalog.snapshot.provider,
        catalog_locale=catalog.snapshot.locale,
        catalog_source_sha256=(
            catalog.snapshot.source_sha256
        ),
        scoped_champion_count=scoped_count,
        observed_roster_name_count=len(
            {
                str(name).strip()
                for name in observed_roster_names
                if str(name).strip()
            }
        ),
        set_support_score=(
            candidates[0].score
            if candidates
            else None
        ),
        set_confidence=confidence,
        set_margin=margin,
        set_candidates=candidates,
        created_at_utc=(
            datetime.now(timezone.utc).isoformat()
        ),
    )

    save_game_context(match_dir, context)
    return context
