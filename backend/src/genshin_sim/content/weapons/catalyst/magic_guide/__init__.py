"""魔导绪论内容包。"""

from genshin_sim.content.weapons.catalyst.magic_guide.content import (
    create_magic_guide_identity_unit,
    create_magic_guide_passive_unit,
)
from genshin_sim.content.weapons.catalyst.magic_guide.data import (
    MAGIC_GUIDE_AFFECTED_ELEMENTS,
    MAGIC_GUIDE_AUDIT_TAG,
    MAGIC_GUIDE_BONUS_COMPONENT_INDEX,
    MAGIC_GUIDE_CONTENT_VERSION,
    MAGIC_GUIDE_HANDLER_KEY,
    MAGIC_GUIDE_PASSIVE_EFFECT_HANDLER_KEY,
)

__all__ = [
    "MAGIC_GUIDE_AFFECTED_ELEMENTS",
    "MAGIC_GUIDE_AUDIT_TAG",
    "MAGIC_GUIDE_BONUS_COMPONENT_INDEX",
    "MAGIC_GUIDE_CONTENT_VERSION",
    "MAGIC_GUIDE_HANDLER_KEY",
    "MAGIC_GUIDE_PASSIVE_EFFECT_HANDLER_KEY",
    "create_magic_guide_identity_unit",
    "create_magic_guide_passive_unit",
]
