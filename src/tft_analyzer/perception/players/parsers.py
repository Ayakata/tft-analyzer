from __future__ import annotations

import re


_HP_TOKEN_RE = re.compile(r"(?<!\d)(\d{1,3})(?!\d)")


def parse_player_hp(
    text: str,
    *,
    max_hp: int = 250,
) -> tuple[int | None, float]:
    """
    Parse one plausible player-health token from a tight OCR window.

    The search windows are deliberately narrow, so one numeric token is
    expected. Multiple tokens are treated conservatively: the last plausible
    token is preferred because health is usually rendered toward the right side
    of a scoreboard row.
    """
    cleaned = str(text or "").strip()

    # Common OCR substitutions when the crop contains only digits.
    normalized = (
        cleaned.replace("O", "0")
        .replace("o", "0")
        .replace("I", "1")
        .replace("l", "1")
        .replace("|", "1")
    )

    values = []
    for match in _HP_TOKEN_RE.finditer(normalized):
        value = int(match.group(1))
        if 0 <= value <= int(max_hp):
            values.append(value)

    if not values:
        return None, 0.0

    # A clean all-digit crop is strongest; extraction from mixed text is still
    # usable but deliberately lower-confidence.
    compact = re.sub(r"\s+", "", normalized)
    parser_confidence = 1.0 if compact.isdigit() else 0.80
    return values[-1], parser_confidence
