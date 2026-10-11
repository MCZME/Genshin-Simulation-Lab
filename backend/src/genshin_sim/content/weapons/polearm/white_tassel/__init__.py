"""白缨枪内容包。"""

from genshin_sim.content.weapons.polearm.white_tassel.content import (
    create_white_tassel_identity_unit,
    create_white_tassel_passive_unit,
)
from genshin_sim.content.weapons.polearm.white_tassel.data import (
    WHITE_TASSEL_CONTENT_VERSION,
    WHITE_TASSEL_HANDLER_KEY,
    WHITE_TASSEL_PASSIVE_EFFECT_HANDLER_KEY,
)

__all__ = [
    "WHITE_TASSEL_CONTENT_VERSION",
    "WHITE_TASSEL_HANDLER_KEY",
    "WHITE_TASSEL_PASSIVE_EFFECT_HANDLER_KEY",
    "create_white_tassel_identity_unit",
    "create_white_tassel_passive_unit",
]
