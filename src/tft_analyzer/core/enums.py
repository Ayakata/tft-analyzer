from enum import StrEnum


class GamePhase(StrEnum):
    UNKNOWN = "unknown"
    PLANNING = "planning"
    COMBAT = "combat"
    CAROUSEL = "carousel"
    AUGMENT = "augment"
    PVE = "pve"
    POST_GAME = "post_game"


class EvidenceKind(StrEnum):
    FRAME = "frame"
    ROI = "roi"
    VIDEO_SEGMENT = "video_segment"
    EXTERNAL_API = "external_api"


class ObservationKind(StrEnum):
    SCENE = "scene"
    STAGE = "stage"
    ROUND = "round"
    GOLD = "gold"
    HP = "hp"
    LEVEL = "level"
    XP = "xp"
    SHOP = "shop"
    BOARD = "board"
    BENCH = "bench"
    INVENTORY = "inventory"
    AUGMENTS = "augments"
    TRAITS = "traits"
    OPPONENT = "opponent"


class EventType(StrEnum):
    MATCH_START = "match_start"
    MATCH_END = "match_end"
    ROUND_START = "round_start"
    ROUND_END = "round_end"

    GOLD_CHANGED = "gold_changed"
    HP_CHANGED = "hp_changed"
    LEVEL_CHANGED = "level_changed"
    XP_CHANGED = "xp_changed"
    SHOP_CHANGED = "shop_changed"

    BUY_UNIT = "buy_unit"
    SELL_UNIT = "sell_unit"
    REFRESH_SHOP = "refresh_shop"
    PURCHASE_XP = "purchase_xp"
    EQUIP_ITEM = "equip_item"
    MOVE_UNIT = "move_unit"
    CHOOSE_AUGMENT = "choose_augment"
    UNIT_UPGRADED = "unit_upgraded"

    UNKNOWN = "unknown"


class ActionType(StrEnum):
    BUY_UNIT = "buy_unit"
    SELL_UNIT = "sell_unit"
    REFRESH_SHOP = "refresh_shop"
    PURCHASE_XP = "purchase_xp"
    EQUIP_ITEM = "equip_item"
    MOVE_UNIT = "move_unit"
    BENCH_TO_BOARD = "bench_to_board"
    BOARD_TO_BENCH = "board_to_bench"
    UNKNOWN_ECON_ACTION = "unknown_econ_action"
    CHOOSE_AUGMENT = "choose_augment"

    HOLD_ECONOMY = "hold_economy"
    LEVEL_TO = "level_to"
    ROLL_TO_GOLD = "roll_to_gold"
    ROLL_UNTIL_UPGRADE = "roll_until_upgrade"
    TRANSITION_TO = "transition_to"
    STABILIZE = "stabilize"


class DecisionType(StrEnum):
    LEVEL_UP = "level_up"
    ROLLDOWN = "rolldown"
    SLOW_ROLL = "slow_roll"
    ECONOMY_HOLD = "economy_hold"
    ITEM_SLAM = "item_slam"
    AUGMENT_CHOICE = "augment_choice"
    COMPOSITION_TRANSITION = "composition_transition"
    UNIT_UPGRADE = "unit_upgrade"
    POSITIONING_CHANGE = "positioning_change"
    OTHER = "other"



class EventQuality(StrEnum):
    TRUSTED = "trusted"
    TIMING_UNCERTAIN = "timing_uncertain"
    SUSPICIOUS = "suspicious"


class ReductionAction(StrEnum):
    INITIALIZED = "initialized"
    APPLIED = "applied"
    APPLIED_WITH_MISMATCH = "applied_with_mismatch"
    SKIPPED_VALIDATION = "skipped_validation"
    IGNORED_NO_CHANGE = "ignored_no_change"
    METADATA_REFRESHED = "metadata_refreshed"
