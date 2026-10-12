"""白铁大剑内容包。"""

from genshin_sim.content.weapons.claymore.white_iron_greatsword.content import (
    create_white_iron_greatsword_identity_unit,
    create_white_iron_greatsword_passive_unit,
)
from genshin_sim.content.weapons.claymore.white_iron_greatsword.data import (
    WHITE_IRON_GREATSWORD_CONTENT_VERSION,
    WHITE_IRON_GREATSWORD_HANDLER_KEY,
    WHITE_IRON_GREATSWORD_PASSIVE_EFFECT_HANDLER_KEY,
)

__all__ = [
    "WHITE_IRON_GREATSWORD_CONTENT_VERSION",
    "WHITE_IRON_GREATSWORD_HANDLER_KEY",
    "WHITE_IRON_GREATSWORD_PASSIVE_EFFECT_HANDLER_KEY",
    "create_white_iron_greatsword_identity_unit",
    "create_white_iron_greatsword_passive_unit",
]
