"""冷刃内容包。"""

from genshin_sim.content.weapons.sword.cool_steel.content import (
    create_cool_steel_identity_unit,
    create_cool_steel_passive_unit,
)
from genshin_sim.content.weapons.sword.cool_steel.data import (
    COOL_STEEL_AFFECTED_ELEMENTS,
    COOL_STEEL_AUDIT_TAG,
    COOL_STEEL_BONUS_COMPONENT_INDEX,
    COOL_STEEL_CONTENT_VERSION,
    COOL_STEEL_HANDLER_KEY,
    COOL_STEEL_PASSIVE_EFFECT_HANDLER_KEY,
)

__all__ = [
    "COOL_STEEL_AFFECTED_ELEMENTS",
    "COOL_STEEL_AUDIT_TAG",
    "COOL_STEEL_BONUS_COMPONENT_INDEX",
    "COOL_STEEL_CONTENT_VERSION",
    "COOL_STEEL_HANDLER_KEY",
    "COOL_STEEL_PASSIVE_EFFECT_HANDLER_KEY",
    "create_cool_steel_identity_unit",
    "create_cool_steel_passive_unit",
]
