"""西风剑内容包（窄导出）。"""

from genshin_sim.content.weapons.sword.favonius_sword.content import (
    create_favonius_sword_content_unit,
)
from genshin_sim.content.weapons.sword.favonius_sword.data import (
    FAVONIUS_SWORD_HANDLER_KEY,
    FAVONIUS_SWORD_PASSIVE_EFFECT_HANDLER_KEY,
    FAVONIUS_SWORD_WINDFALL_IMPACT_KEY,
)

__all__ = [
    "FAVONIUS_SWORD_HANDLER_KEY",
    "FAVONIUS_SWORD_PASSIVE_EFFECT_HANDLER_KEY",
    "FAVONIUS_SWORD_WINDFALL_IMPACT_KEY",
    "create_favonius_sword_content_unit",
]
