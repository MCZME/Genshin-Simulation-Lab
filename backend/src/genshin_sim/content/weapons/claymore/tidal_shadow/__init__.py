"""浪影阔剑内容包。"""

from genshin_sim.content.weapons.claymore.tidal_shadow.content import (
    create_tidal_shadow_identity_unit,
    create_tidal_shadow_passive_unit,
)
from genshin_sim.content.weapons.claymore.tidal_shadow.data import (
    TIDAL_SHADOW_CONTENT_VERSION,
    TIDAL_SHADOW_HANDLER_KEY,
    TIDAL_SHADOW_PASSIVE_EFFECT_HANDLER_KEY,
)

__all__ = [
    "TIDAL_SHADOW_CONTENT_VERSION",
    "TIDAL_SHADOW_HANDLER_KEY",
    "TIDAL_SHADOW_PASSIVE_EFFECT_HANDLER_KEY",
    "create_tidal_shadow_identity_unit",
    "create_tidal_shadow_passive_unit",
]
