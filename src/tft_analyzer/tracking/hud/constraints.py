from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ConstraintResult:
    valid: bool
    suspicious: bool
    reason: str


def stage_code(value: dict[str, Any]) -> int:
    return int(value["stage"]) * 10 + int(value["round"])


def check_stage(
    previous: dict[str, Any] | None,
    observed: dict[str, Any],
    *,
    reject_regression: bool,
    max_jump_without_confirmation: int,
) -> ConstraintResult:
    if previous is None:
        return ConstraintResult(True, False, "initial")

    prev_code = stage_code(previous)
    obs_code = stage_code(observed)

    if obs_code == prev_code:
        return ConstraintResult(True, False, "same_stage")

    if obs_code < prev_code and reject_regression:
        return ConstraintResult(False, False, "stage_regression")

    jump = obs_code - prev_code
    if jump > max_jump_without_confirmation:
        return ConstraintResult(True, True, "large_stage_jump")

    return ConstraintResult(True, False, "stage_forward")


def check_level(
    previous: dict[str, Any] | None,
    observed: dict[str, Any],
    *,
    reject_regression: bool,
    max_jump_without_confirmation: int,
) -> ConstraintResult:
    if previous is None:
        return ConstraintResult(True, False, "initial")

    prev = int(previous["level"])
    obs = int(observed["level"])

    if obs == prev:
        return ConstraintResult(True, False, "same_level")

    if obs < prev and reject_regression:
        return ConstraintResult(False, False, "level_regression")

    if obs - prev > max_jump_without_confirmation:
        return ConstraintResult(True, True, "large_level_jump")

    return ConstraintResult(True, False, "level_forward")


def check_gold(
    previous: dict[str, Any] | None,
    observed: dict[str, Any],
) -> ConstraintResult:
    gold = int(observed["gold"])
    if not 0 <= gold <= 999:
        return ConstraintResult(False, False, "gold_out_of_range")

    if previous is not None and int(previous["gold"]) == gold:
        return ConstraintResult(True, False, "same_gold")

    # Gold is intentionally not smoothed aggressively: real roll-downs,
    # purchases and income can change it rapidly. Event validation belongs to
    # the next stage.
    return ConstraintResult(True, False, "gold_changed")


def check_xp(
    previous: dict[str, Any] | None,
    observed: dict[str, Any],
    *,
    reject_regression_same_requirement: bool,
) -> ConstraintResult:
    current = int(observed["current"])
    required = int(observed["required"])

    if current < 0 or required <= 0 or current > required:
        return ConstraintResult(False, False, "xp_out_of_range")

    if previous is None:
        return ConstraintResult(True, False, "initial")

    prev_current = int(previous["current"])
    prev_required = int(previous["required"])

    if current == prev_current and required == prev_required:
        return ConstraintResult(True, False, "same_xp")

    if required == prev_required:
        if current < prev_current and reject_regression_same_requirement:
            return ConstraintResult(False, False, "xp_regression_same_level")
        return ConstraintResult(True, False, "xp_forward")

    # Requirement changes are a strong sign of a level transition. In that
    # case a smaller current XP is legitimate and should not be treated as a
    # regression.
    return ConstraintResult(True, False, "xp_requirement_changed")



def check_hp(
    previous: dict[str, Any] | None,
    observed: dict[str, Any],
    *,
    max_jump_without_confirmation: int = 25,
) -> ConstraintResult:
    hp = int(observed["hp"])

    # TFT mechanics can legitimately heal player HP, so do not enforce
    # monotonic decrease. We only confirm unusually large jumps.
    if not 0 <= hp <= 250:
        return ConstraintResult(False, False, "hp_out_of_range")

    if previous is None:
        return ConstraintResult(True, False, "hp_initial")

    previous_hp = int(previous["hp"])

    if previous_hp == hp:
        return ConstraintResult(True, False, "same_hp")

    # HP healing exists, but it is rare enough that one-frame increases should
    # not immediately rewrite state. A real heal will persist and confirm.
    if hp > previous_hp:
        return ConstraintResult(
            True,
            True,
            "hp_increase_requires_confirmation",
        )

    # A two-digit value collapsing to one digit is a common crop/OCR failure
    # (48 -> 4, 71 -> 1). High-confidence single digits are still allowed,
    # but only after temporal confirmation.
    if previous_hp >= 10 and hp < 10:
        return ConstraintResult(
            True,
            True,
            "hp_single_digit_requires_confirmation",
        )

    if abs(hp - previous_hp) > int(max_jump_without_confirmation):
        return ConstraintResult(
            True,
            True,
            "hp_large_jump_requires_confirmation",
        )

    return ConstraintResult(True, False, "hp_changed")



def check_shop(
    previous: dict[str, Any] | None,
    observed: dict[str, Any],
) -> ConstraintResult:
    slots = observed.get("slots")

    if not isinstance(slots, (list, tuple)) or len(slots) != 5:
        return ConstraintResult(False, False, "shop_invalid_slot_count")

    for value in slots:
        if value is not None and (
            not isinstance(value, str) or not value.strip()
        ):
            return ConstraintResult(False, False, "shop_invalid_identity")

    if previous is None:
        return ConstraintResult(True, False, "shop_initial")

    if list(previous.get("slots", [])) == list(slots):
        return ConstraintResult(True, False, "same_shop")

    # Cause inference is deliberately absent here. A changed five-slot
    # snapshot is a primitive fact only.
    return ConstraintResult(True, False, "shop_changed")
