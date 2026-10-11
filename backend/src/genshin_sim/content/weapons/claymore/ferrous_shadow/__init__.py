"""铁影阔剑内容包。"""

from genshin_sim.content.weapons.claymore.ferrous_shadow.content import (
    create_ferrous_shadow_identity_unit,
    create_ferrous_shadow_passive_unit,
)
from genshin_sim.content.weapons.claymore.ferrous_shadow.data import (
    FERROUS_SHADOW_CONTENT_VERSION,
    FERROUS_SHADOW_HANDLER_KEY,
    FERROUS_SHADOW_PASSIVE_EFFECT_HANDLER_KEY,
)

__all__ = [
    "FERROUS_SHADOW_CONTENT_VERSION",
    "FERROUS_SHADOW_HANDLER_KEY",
    "FERROUS_SHADOW_PASSIVE_EFFECT_HANDLER_KEY",
    "create_ferrous_shadow_identity_unit",
    "create_ferrous_shadow_passive_unit",
]
