from __future__ import annotations

import re
from collections.abc import Callable

from .models import ParsedHUDValue


_DASHES_RE = re.compile(r"[‐‑‒–—−:]")
_SLASHES_RE = re.compile(r"[\\|¦]")
_WS_RE = re.compile(r"\s+")


def _clean(text: str) -> str:
    text = str(text or "").strip()
    text = _DASHES_RE.sub("-", text)
    text = _SLASHES_RE.sub("/", text)
    text = _WS_RE.sub(" ", text)
    return text


def _numeric_confusions(text: str) -> str:
    # These substitutions are deliberately limited to numeric HUD fields.
    table = str.maketrans({
        "O": "0",
        "o": "0",
        "I": "1",
        "l": "1",
        "|": "1",
        "S": "5",
    })
    return text.translate(table)


def parse_stage(text: str) -> ParsedHUDValue | None:
    cleaned = _numeric_confusions(_clean(text))

    match = re.search(r"(?<!\d)([1-9])\s*-\s*([1-9])(?!\d)", cleaned)
    parser_conf = 1.0

    if not match:
        digits = re.findall(r"\d", cleaned)
        if len(digits) == 2:
            stage, round_ = int(digits[0]), int(digits[1])
            parser_conf = 0.72
        else:
            return None
    else:
        stage, round_ = int(match.group(1)), int(match.group(2))

    if not (1 <= stage <= 9 and 1 <= round_ <= 9):
        return None

    return ParsedHUDValue(
        value={"stage": stage, "round": round_},
        normalized_text=f"{stage}-{round_}",
        parser_confidence=parser_conf,
    )


def parse_gold(text: str) -> ParsedHUDValue | None:
    cleaned = _clean(text)

    # Prefer digits that OCR actually emitted. Only apply letter->digit
    # substitutions when no real numeric token exists; otherwise words such as
    # "gold" would become "g01d" and create a false candidate.
    groups = re.findall(r"\d{1,3}", cleaned)
    used_confusion_fallback = False

    if not groups:
        numeric = _numeric_confusions(cleaned)
        groups = re.findall(r"\d{1,3}", numeric)
        used_confusion_fallback = True

    if not groups:
        return None

    token = max(groups, key=len)
    gold = int(token)

    if not (0 <= gold <= 999):
        return None

    if cleaned.strip() == token:
        parser_conf = 1.0
    elif used_confusion_fallback:
        parser_conf = 0.80
    else:
        parser_conf = 0.88

    return ParsedHUDValue(
        value={"gold": gold},
        normalized_text=str(gold),
        parser_confidence=parser_conf,
    )


def parse_level(text: str) -> ParsedHUDValue | None:
    cleaned = _numeric_confusions(_clean(text))
    groups = re.findall(r"\d{1,2}", cleaned)
    if not groups:
        return None

    # "Lvl. 5" / "Lv 5" / plain "5" all collapse to the final number.
    level = int(groups[-1])
    if not (1 <= level <= 10):
        return None

    has_label = bool(re.search(r"(?i)lv|level", cleaned))
    parser_conf = 1.0 if has_label or cleaned.strip().isdigit() else 0.90

    return ParsedHUDValue(
        value={"level": level},
        normalized_text=str(level),
        parser_confidence=parser_conf,
    )


def parse_xp(text: str) -> ParsedHUDValue | None:
    cleaned = _numeric_confusions(_clean(text))

    match = re.search(r"(\d{1,3})\s*/\s*(\d{1,3})", cleaned)
    parser_conf = 1.0

    if match:
        current, required = int(match.group(1)), int(match.group(2))
    else:
        groups = re.findall(r"\d{1,3}", cleaned)
        if len(groups) != 2:
            return None
        current, required = int(groups[0]), int(groups[1])
        parser_conf = 0.76

    if not (0 <= current <= 999 and 1 <= required <= 999):
        return None

    # In normal TFT level progression the visible XP does not exceed the
    # requirement; allow equality for a transient frame around level-up.
    if current > required:
        return None

    return ParsedHUDValue(
        value={"current": current, "required": required},
        normalized_text=f"{current}/{required}",
        parser_confidence=parser_conf,
    )


PARSER_BY_FIELD: dict[str, Callable[[str], ParsedHUDValue | None]] = {
    "stage": parse_stage,
    "gold": parse_gold,
    "level": parse_level,
    "xp": parse_xp,
}
