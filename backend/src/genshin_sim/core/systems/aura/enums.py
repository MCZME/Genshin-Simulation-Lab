from __future__ import annotations

from enum import IntEnum, StrEnum


class AuraStrength(IntEnum):
    WEAK = 1
    MEDIUM = 2
    STRONG = 3
    SUPER_STRONG = 4


class AuraLossPolicy(StrEnum):
    STANDARD_20_PERCENT = "standard_20_percent"
    LOSSLESS = "lossless"


class AuraDecayProfilePolicy(StrEnum):
    """元素施加如何确定自然衰减档案。"""

    STANDARD_STRENGTH = "standard_strength"
    REGULAR_FROM_RAW_AMOUNT = "regular_from_raw_amount"


class AuraApplicationOutcome(StrEnum):
    CREATED = "created"
    AMOUNT_INCREASED = "amount_increased"
    DECAY_PROFILE_UPGRADED = "decay_profile_upgraded"
    AMOUNT_AND_PROFILE_UPDATED = "amount_and_profile_updated"
    DERIVED_REPLACED = "derived_replaced"
    UNCHANGED = "unchanged"


class AuraDecayMode(StrEnum):
    STANDARD = "standard"
    STATE_LINKED = "state_linked"
    REACTION_MANAGED = "reaction_managed"
