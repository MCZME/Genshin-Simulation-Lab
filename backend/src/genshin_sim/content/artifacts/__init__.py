"""圣遗物套装实现。"""

from genshin_sim.content.artifacts.disenchantment_in_deep_shadow import (
    DISENCHANTMENT_IN_DEEP_SHADOW_2P_HANDLER_KEY,
    DISENCHANTMENT_IN_DEEP_SHADOW_4P_HANDLER_KEY,
    DISENCHANTMENT_IN_DEEP_SHADOW_CONTENT_VERSION,
    create_disenchantment_in_deep_shadow_four_piece_unit,
    create_disenchantment_in_deep_shadow_two_piece_unit,
)
from genshin_sim.content.artifacts.maiden_beloved import (
    MAIDEN_BELOVED_2P_HANDLER_KEY,
    MAIDEN_BELOVED_4P_HANDLER_KEY,
    MAIDEN_BELOVED_CONTENT_VERSION,
    create_maiden_beloved_four_piece_unit,
    create_maiden_beloved_two_piece_unit,
)

__all__ = [
    "MAIDEN_BELOVED_2P_HANDLER_KEY",
    "MAIDEN_BELOVED_4P_HANDLER_KEY",
    "MAIDEN_BELOVED_CONTENT_VERSION",
    "DISENCHANTMENT_IN_DEEP_SHADOW_2P_HANDLER_KEY",
    "DISENCHANTMENT_IN_DEEP_SHADOW_4P_HANDLER_KEY",
    "DISENCHANTMENT_IN_DEEP_SHADOW_CONTENT_VERSION",
    "create_maiden_beloved_four_piece_unit",
    "create_maiden_beloved_two_piece_unit",
    "create_disenchantment_in_deep_shadow_four_piece_unit",
    "create_disenchantment_in_deep_shadow_two_piece_unit",
]
