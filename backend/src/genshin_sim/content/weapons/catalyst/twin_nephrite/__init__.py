"""甲级宝珏内容包。"""

from genshin_sim.content.weapons.catalyst.twin_nephrite.content import (
    create_twin_nephrite_identity_unit,
    create_twin_nephrite_passive_unit,
)
from genshin_sim.content.weapons.catalyst.twin_nephrite.data import (
    TWIN_NEPHRITE_CONTENT_VERSION,
    TWIN_NEPHRITE_HANDLER_KEY,
    TWIN_NEPHRITE_PASSIVE_EFFECT_HANDLER_KEY,
)

__all__ = [
    "TWIN_NEPHRITE_CONTENT_VERSION",
    "TWIN_NEPHRITE_HANDLER_KEY",
    "TWIN_NEPHRITE_PASSIVE_EFFECT_HANDLER_KEY",
    "create_twin_nephrite_identity_unit",
    "create_twin_nephrite_passive_unit",
]
