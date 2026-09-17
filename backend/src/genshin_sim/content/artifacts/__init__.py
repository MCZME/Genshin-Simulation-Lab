"""圣遗物套装实现。"""

from genshin_sim.content.artifacts.disenchantment_in_deep_shadow import (
    DISENCHANTMENT_IN_DEEP_SHADOW_ASSET_KEY,
    DISENCHANTMENT_IN_DEEP_SHADOW_CONTENT_VERSION,
    DISENCHANTMENT_IN_DEEP_SHADOW_HANDLER_KEY,
    create_disenchantment_in_deep_shadow_content_unit,
)
from genshin_sim.content.artifacts.maiden_beloved import (
    MAIDEN_BELOVED_ASSET_KEY,
    MAIDEN_BELOVED_CONTENT_VERSION,
    MAIDEN_BELOVED_HANDLER_KEY,
    create_maiden_beloved_content_unit,
)

__all__ = [
    "MAIDEN_BELOVED_ASSET_KEY",
    "MAIDEN_BELOVED_CONTENT_VERSION",
    "MAIDEN_BELOVED_HANDLER_KEY",
    "DISENCHANTMENT_IN_DEEP_SHADOW_ASSET_KEY",
    "DISENCHANTMENT_IN_DEEP_SHADOW_CONTENT_VERSION",
    "DISENCHANTMENT_IN_DEEP_SHADOW_HANDLER_KEY",
    "create_maiden_beloved_content_unit",
    "create_disenchantment_in_deep_shadow_content_unit",
]
