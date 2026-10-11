"""飞天大御剑内容包。"""

from genshin_sim.content.weapons.claymore.skyrider_greatsword.content import (
    create_skyrider_greatsword_identity_unit,
    create_skyrider_greatsword_passive_unit,
)
from genshin_sim.content.weapons.claymore.skyrider_greatsword.data import (
    SKYRIDER_GREATSWORD_CONTENT_VERSION,
    SKYRIDER_GREATSWORD_HANDLER_KEY,
    SKYRIDER_GREATSWORD_PASSIVE_EFFECT_HANDLER_KEY,
)

__all__ = [
    "SKYRIDER_GREATSWORD_CONTENT_VERSION",
    "SKYRIDER_GREATSWORD_HANDLER_KEY",
    "SKYRIDER_GREATSWORD_PASSIVE_EFFECT_HANDLER_KEY",
    "create_skyrider_greatsword_identity_unit",
    "create_skyrider_greatsword_passive_unit",
]
