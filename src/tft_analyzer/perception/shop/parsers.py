from __future__ import annotations

import re


_ALLOWED_RE = re.compile(r"^[A-Za-z][A-Za-z .'-]{1,30}$")


def normalize_shop_name(text: str) -> tuple[str | None, float]:
    """Normalize a champion name as displayed on a TFT shop card.

    This stage deliberately does not map to a Riot champion ID yet. It only
    creates a stable OCR token such as ``missfortune`` or ``ksante``.
    """
    raw = str(text or "").strip()
    raw = re.sub(r"\s+", " ", raw)

    if not raw:
        return None, 0.0

    # Clean leading/trailing OCR punctuation while preserving meaningful
    # apostrophes, dots and spaces inside names.
    cleaned = raw.strip(" _-:;|[](){}")
    normalized = re.sub(r"[^A-Za-z]", "", cleaned).lower()

    if len(normalized) < 2 or len(normalized) > 24:
        return None, 0.0

    if _ALLOWED_RE.match(cleaned):
        return normalized, 1.0

    # OCR may include one stray symbol. If the alphabetic core is still
    # plausible, retain it with reduced parser confidence.
    alpha_ratio = sum(ch.isalpha() for ch in cleaned) / max(len(cleaned), 1)
    if alpha_ratio >= 0.65:
        return normalized, 0.78

    return None, 0.0
