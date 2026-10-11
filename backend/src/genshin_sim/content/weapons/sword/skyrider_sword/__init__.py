"""飞天御剑内容包。"""

from genshin_sim.content.weapons.sword.skyrider_sword.content import (
    create_skyrider_sword_identity_unit,
    create_skyrider_sword_passive_unit,
)
from genshin_sim.content.weapons.sword.skyrider_sword.data import (
    SKYRIDER_SWORD_CONTENT_VERSION,
    SKYRIDER_SWORD_HANDLER_KEY,
    SKYRIDER_SWORD_PASSIVE_EFFECT_HANDLER_KEY,
)

__all__ = [
    "SKYRIDER_SWORD_CONTENT_VERSION",
    "SKYRIDER_SWORD_HANDLER_KEY",
    "SKYRIDER_SWORD_PASSIVE_EFFECT_HANDLER_KEY",
    "create_skyrider_sword_identity_unit",
    "create_skyrider_sword_passive_unit",
]
