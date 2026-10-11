"""以理服人内容包。"""

from genshin_sim.content.weapons.claymore.bloodtainted_greatsword.content import (
    create_bloodtainted_greatsword_identity_unit,
    create_bloodtainted_greatsword_passive_unit,
)
from genshin_sim.content.weapons.claymore.bloodtainted_greatsword.data import (
    BLOODTAINTED_CONTENT_VERSION,
    BLOODTAINTED_HANDLER_KEY,
    BLOODTAINTED_PASSIVE_EFFECT_HANDLER_KEY,
)

__all__ = [
    "BLOODTAINTED_CONTENT_VERSION",
    "BLOODTAINTED_HANDLER_KEY",
    "BLOODTAINTED_PASSIVE_EFFECT_HANDLER_KEY",
    "create_bloodtainted_greatsword_identity_unit",
    "create_bloodtainted_greatsword_passive_unit",
]
