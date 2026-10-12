"""神射手之誓内容包。"""

from genshin_sim.content.weapons.bow.sharpshooters_oath.content import (
    create_sharpshooters_oath_identity_unit,
    create_sharpshooters_oath_passive_unit,
)
from genshin_sim.content.weapons.bow.sharpshooters_oath.data import (
    SHARPSHOOTERS_OATH_CONTENT_VERSION,
    SHARPSHOOTERS_OATH_HANDLER_KEY,
    SHARPSHOOTERS_OATH_PASSIVE_EFFECT_HANDLER_KEY,
)

__all__ = [
    "SHARPSHOOTERS_OATH_CONTENT_VERSION",
    "SHARPSHOOTERS_OATH_HANDLER_KEY",
    "SHARPSHOOTERS_OATH_PASSIVE_EFFECT_HANDLER_KEY",
    "create_sharpshooters_oath_identity_unit",
    "create_sharpshooters_oath_passive_unit",
]
