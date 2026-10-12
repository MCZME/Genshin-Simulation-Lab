"""黑缨枪内容包。"""

from genshin_sim.content.weapons.polearm.black_tassel.content import (
    create_black_tassel_identity_unit,
    create_black_tassel_passive_unit,
)
from genshin_sim.content.weapons.polearm.black_tassel.data import (
    BLACK_TASSEL_CONTENT_VERSION,
    BLACK_TASSEL_HANDLER_KEY,
    BLACK_TASSEL_PASSIVE_EFFECT_HANDLER_KEY,
)

__all__ = [
    "BLACK_TASSEL_CONTENT_VERSION",
    "BLACK_TASSEL_HANDLER_KEY",
    "BLACK_TASSEL_PASSIVE_EFFECT_HANDLER_KEY",
    "create_black_tassel_identity_unit",
    "create_black_tassel_passive_unit",
]
