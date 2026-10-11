"""讨龙英杰谭内容包。"""

from genshin_sim.content.weapons.catalyst.thrilling_tales_of_dragon_slayers.content import (
    create_thrilling_tales_identity_unit,
    create_thrilling_tales_passive_unit,
)
from genshin_sim.content.weapons.catalyst.thrilling_tales_of_dragon_slayers.data import (
    THRILLING_TALES_CONTENT_VERSION,
    THRILLING_TALES_HANDLER_KEY,
    THRILLING_TALES_PASSIVE_EFFECT_HANDLER_KEY,
)

__all__ = [
    "THRILLING_TALES_CONTENT_VERSION",
    "THRILLING_TALES_HANDLER_KEY",
    "THRILLING_TALES_PASSIVE_EFFECT_HANDLER_KEY",
    "create_thrilling_tales_identity_unit",
    "create_thrilling_tales_passive_unit",
]
