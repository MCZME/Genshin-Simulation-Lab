"""白湖冬羽内容包。"""

from genshin_sim.content.weapons.sword.whitelake_frostfeather.content import (
    create_whitelake_frostfeather_identity_unit,
    create_whitelake_frostfeather_passive_unit,
)
from genshin_sim.content.weapons.sword.whitelake_frostfeather.data import (
    WHITELAKE_FROSTFEATHER_CONTENT_VERSION,
    WHITELAKE_FROSTFEATHER_HANDLER_KEY,
    WHITELAKE_FROSTFEATHER_PASSIVE_EFFECT_HANDLER_KEY,
)

__all__ = [
    "WHITELAKE_FROSTFEATHER_CONTENT_VERSION",
    "WHITELAKE_FROSTFEATHER_HANDLER_KEY",
    "WHITELAKE_FROSTFEATHER_PASSIVE_EFFECT_HANDLER_KEY",
    "create_whitelake_frostfeather_identity_unit",
    "create_whitelake_frostfeather_passive_unit",
]
