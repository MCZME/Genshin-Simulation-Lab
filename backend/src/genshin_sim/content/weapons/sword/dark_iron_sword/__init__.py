"""暗铁剑内容包。"""

from genshin_sim.content.weapons.sword.dark_iron_sword.content import (
    create_dark_iron_sword_identity_unit,
    create_dark_iron_sword_passive_unit,
)
from genshin_sim.content.weapons.sword.dark_iron_sword.data import (
    DARK_IRON_SWORD_CONTENT_VERSION,
    DARK_IRON_SWORD_HANDLER_KEY,
    DARK_IRON_SWORD_PASSIVE_EFFECT_HANDLER_KEY,
)

__all__ = [
    "DARK_IRON_SWORD_CONTENT_VERSION",
    "DARK_IRON_SWORD_HANDLER_KEY",
    "DARK_IRON_SWORD_PASSIVE_EFFECT_HANDLER_KEY",
    "create_dark_iron_sword_identity_unit",
    "create_dark_iron_sword_passive_unit",
]
