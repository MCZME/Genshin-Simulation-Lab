"""吃虎鱼刀内容包。"""

from genshin_sim.content.weapons.sword.fillet_blade.content import (
    create_fillet_blade_identity_unit,
    create_fillet_blade_passive_unit,
)
from genshin_sim.content.weapons.sword.fillet_blade.data import (
    FILLET_BLADE_CONTENT_VERSION,
    FILLET_BLADE_HANDLER_KEY,
    FILLET_BLADE_PASSIVE_EFFECT_HANDLER_KEY,
)

__all__ = [
    "FILLET_BLADE_CONTENT_VERSION",
    "FILLET_BLADE_HANDLER_KEY",
    "FILLET_BLADE_PASSIVE_EFFECT_HANDLER_KEY",
    "create_fillet_blade_identity_unit",
    "create_fillet_blade_passive_unit",
]
