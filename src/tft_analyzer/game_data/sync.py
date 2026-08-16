from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from urllib.request import Request, urlopen

from .catalog import normalize_champion_name
from .models import (
    ChampionCatalogEntry,
    ChampionCatalogSnapshot,
)


RIOT_DDRAGON_VERSIONS_URL = (
    "https://ddragon.leagueoflegends.com/api/versions.json"
)


def riot_tft_champion_url(
    version: str,
    locale: str,
) -> str:
    return (
        "https://ddragon.leagueoflegends.com/cdn/"
        f"{version}/data/{locale}/tft-champion.json"
    )


def _fetch_bytes(
    url: str,
    *,
    timeout_seconds: float,
) -> bytes:
    request = Request(
        url,
        headers={
            "User-Agent": "tft-analyzer/0.14.4",
            "Accept": "application/json",
        },
    )
    with urlopen(
        request,
        timeout=float(timeout_seconds),
    ) as response:
        return response.read()


def resolve_latest_riot_ddragon_version(
    *,
    timeout_seconds: float = 30.0,
) -> str:
    payload = json.loads(
        _fetch_bytes(
            RIOT_DDRAGON_VERSIONS_URL,
            timeout_seconds=timeout_seconds,
        )
    )
    if not isinstance(payload, list) or not payload:
        raise ValueError(
            "Riot Data Dragon versions response is empty or invalid"
        )
    return str(payload[0])


def build_champion_catalog_snapshot(
    raw_bytes: bytes,
    *,
    version: str,
    locale: str,
    source_url: str,
    fetched_at_utc: str | None = None,
) -> ChampionCatalogSnapshot:
    payload = json.loads(raw_bytes)
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError(
            "Expected Riot TFT champion JSON with a top-level 'data' object"
        )

    entries = []
    for key, raw in data.items():
        if not isinstance(raw, dict):
            continue

        champion_id = str(
            raw.get("id") or key or ""
        ).strip()
        name = str(raw.get("name") or "").strip()

        if not champion_id or not name:
            continue

        tier_raw = raw.get("tier")
        try:
            tier = int(tier_raw) if tier_raw is not None else None
        except (TypeError, ValueError):
            tier = None

        image = raw.get("image")
        image_full = None
        if isinstance(image, dict):
            value = image.get("full")
            if value:
                image_full = str(value)

        entries.append(
            ChampionCatalogEntry(
                champion_id=champion_id,
                name=name,
                normalized_name=normalize_champion_name(name),
                tier=tier,
                image_full=image_full,
            )
        )

    entries.sort(
        key=lambda item: (
            item.normalized_name,
            item.champion_id,
        )
    )

    return ChampionCatalogSnapshot(
        provider="riot_ddragon",
        version=str(version),
        locale=str(locale),
        source_url=str(source_url),
        source_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        fetched_at_utc=(
            fetched_at_utc
            or datetime.now(timezone.utc).isoformat()
        ),
        source_field_for_cost="tier",
        champions=tuple(entries),
    )


def active_catalog_pointer_path(
    root_dir: Path | str,
) -> Path:
    return (
        Path(root_dir)
        / "riot_ddragon"
        / "active.json"
    )


def find_active_catalog_path(
    root_dir: Path | str,
) -> Path | None:
    pointer = active_catalog_pointer_path(root_dir)
    if not pointer.exists():
        return None

    payload = json.loads(
        pointer.read_text(encoding="utf-8")
    )
    relative = payload.get("catalog_path")
    if not relative:
        return None

    path = Path(root_dir) / str(relative)
    return path if path.exists() else None


def sync_riot_ddragon_catalog(
    root_dir: Path | str,
    *,
    version: str = "latest",
    locale: str = "en_US",
    timeout_seconds: float = 30.0,
    source_file: Path | str | None = None,
    force: bool = False,
) -> dict[str, object]:
    root_dir = Path(root_dir)

    resolved_version = str(version)
    if resolved_version == "latest":
        resolved_version = resolve_latest_riot_ddragon_version(
            timeout_seconds=timeout_seconds
        )

    source_url = riot_tft_champion_url(
        resolved_version,
        locale,
    )

    if source_file is not None:
        source_path = Path(source_file)
        raw_bytes = source_path.read_bytes()
        source_url_for_snapshot = (
            f"file://{source_path.resolve().as_posix()}"
        )
    else:
        raw_bytes = _fetch_bytes(
            source_url,
            timeout_seconds=timeout_seconds,
        )
        source_url_for_snapshot = source_url

    snapshot = build_champion_catalog_snapshot(
        raw_bytes,
        version=resolved_version,
        locale=locale,
        source_url=source_url_for_snapshot,
    )

    out_dir = (
        root_dir
        / "riot_ddragon"
        / resolved_version
        / locale
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    catalog_path = (
        out_dir
        / "tft-champions.catalog.json"
    )

    if catalog_path.exists() and not force:
        existing = ChampionCatalogSnapshot.model_validate_json(
            catalog_path.read_text(encoding="utf-8")
        )
        if existing.source_sha256 != snapshot.source_sha256:
            raise FileExistsError(
                f"{catalog_path} already exists with different source hash; "
                "pass --force to replace it"
            )
    else:
        tmp = catalog_path.with_suffix(
            catalog_path.suffix + ".tmp"
        )
        tmp.write_text(
            snapshot.model_dump_json(
                indent=2,
            ),
            encoding="utf-8",
        )
        tmp.replace(catalog_path)

    provider_root = root_dir / "riot_ddragon"
    provider_root.mkdir(parents=True, exist_ok=True)

    relative_catalog = catalog_path.relative_to(
        root_dir
    ).as_posix()

    pointer_payload = {
        "schema_version": 1,
        "provider": "riot_ddragon",
        "version": resolved_version,
        "locale": locale,
        "catalog_path": relative_catalog,
        "source_sha256": snapshot.source_sha256,
        "activated_at_utc": (
            datetime.now(timezone.utc).isoformat()
        ),
    }

    pointer = active_catalog_pointer_path(
        root_dir
    )
    tmp_pointer = pointer.with_suffix(
        pointer.suffix + ".tmp"
    )
    tmp_pointer.write_text(
        json.dumps(
            pointer_payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    tmp_pointer.replace(pointer)

    tiers = sorted(
        {
            int(entry.tier)
            for entry in snapshot.champions
            if entry.tier is not None
        }
    )

    return {
        "provider": "riot_ddragon",
        "requested_version": version,
        "version": resolved_version,
        "locale": locale,
        "source_url": source_url_for_snapshot,
        "source_sha256": snapshot.source_sha256,
        "champion_count": len(snapshot.champions),
        "tiers": tiers,
        "catalog_path": str(catalog_path),
        "active_pointer_path": str(pointer),
    }
