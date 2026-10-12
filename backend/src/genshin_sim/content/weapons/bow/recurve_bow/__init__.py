"""反曲弓内容包。"""

from genshin_sim.content.weapons.bow.recurve_bow.content import (
    create_recurve_bow_identity_unit,
    create_recurve_bow_passive_unit,
)
from genshin_sim.content.weapons.bow.recurve_bow.data import (
    RECURVE_BOW_CONTENT_VERSION,
    RECURVE_BOW_HANDLER_KEY,
    RECURVE_BOW_PASSIVE_EFFECT_HANDLER_KEY,
)

__all__ = [
    "RECURVE_BOW_CONTENT_VERSION",
    "RECURVE_BOW_HANDLER_KEY",
    "RECURVE_BOW_PASSIVE_EFFECT_HANDLER_KEY",
    "create_recurve_bow_identity_unit",
    "create_recurve_bow_passive_unit",
]
