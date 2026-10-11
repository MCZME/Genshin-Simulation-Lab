"""翡玉法球内容包。"""

from genshin_sim.content.weapons.catalyst.emerald_orb.content import (
    create_emerald_orb_identity_unit,
    create_emerald_orb_passive_unit,
)
from genshin_sim.content.weapons.catalyst.emerald_orb.data import (
    EMERALD_ORB_CONTENT_VERSION,
    EMERALD_ORB_HANDLER_KEY,
    EMERALD_ORB_PASSIVE_EFFECT_HANDLER_KEY,
)

__all__ = [
    "EMERALD_ORB_CONTENT_VERSION",
    "EMERALD_ORB_HANDLER_KEY",
    "EMERALD_ORB_PASSIVE_EFFECT_HANDLER_KEY",
    "create_emerald_orb_identity_unit",
    "create_emerald_orb_passive_unit",
]
