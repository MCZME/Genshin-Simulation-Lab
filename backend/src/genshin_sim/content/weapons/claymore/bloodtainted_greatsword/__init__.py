"""沐浴龙血的剑内容包。"""

from genshin_sim.content.weapons.claymore.bloodtainted_greatsword.content import (
    create_bloodtainted_greatsword_identity_unit,
    create_bloodtainted_greatsword_passive_unit,
)
from genshin_sim.content.weapons.claymore.bloodtainted_greatsword.data import (
    BLOODTAINTED_GREATSWORD_AFFECTED_ELEMENTS,
    BLOODTAINTED_GREATSWORD_AUDIT_TAG,
    BLOODTAINTED_GREATSWORD_BONUS_COMPONENT_INDEX,
    BLOODTAINTED_GREATSWORD_CONTENT_VERSION,
    BLOODTAINTED_GREATSWORD_HANDLER_KEY,
    BLOODTAINTED_GREATSWORD_PASSIVE_EFFECT_HANDLER_KEY,
)

__all__ = [
    "BLOODTAINTED_GREATSWORD_AFFECTED_ELEMENTS",
    "BLOODTAINTED_GREATSWORD_AUDIT_TAG",
    "BLOODTAINTED_GREATSWORD_BONUS_COMPONENT_INDEX",
    "BLOODTAINTED_GREATSWORD_CONTENT_VERSION",
    "BLOODTAINTED_GREATSWORD_HANDLER_KEY",
    "BLOODTAINTED_GREATSWORD_PASSIVE_EFFECT_HANDLER_KEY",
    "create_bloodtainted_greatsword_identity_unit",
    "create_bloodtainted_greatsword_passive_unit",
]
