"""饰铁之花内容包。"""

from genshin_sim.content.weapons.claymore.mailed_flower.content import (
    create_mailed_flower_identity_unit,
    create_mailed_flower_passive_unit,
)
from genshin_sim.content.weapons.claymore.mailed_flower.data import (
    MAILED_FLOWER_CONTENT_VERSION,
    MAILED_FLOWER_HANDLER_KEY,
    MAILED_FLOWER_PASSIVE_EFFECT_HANDLER_KEY,
)

__all__ = [
    "MAILED_FLOWER_CONTENT_VERSION",
    "MAILED_FLOWER_HANDLER_KEY",
    "MAILED_FLOWER_PASSIVE_EFFECT_HANDLER_KEY",
    "create_mailed_flower_identity_unit",
    "create_mailed_flower_passive_unit",
]
