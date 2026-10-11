"""苍古自由之誓内容包。"""

from genshin_sim.content.weapons.sword.freedom_sworn.content import (
    create_freedom_sworn_identity_unit,
    create_freedom_sworn_passive_unit,
)
from genshin_sim.content.weapons.sword.freedom_sworn.data import (
    FREEDOM_SWORN_CONTENT_VERSION,
    FREEDOM_SWORN_HANDLER_KEY,
    FREEDOM_SWORN_PASSIVE_EFFECT_HANDLER_KEY,
)

__all__ = [
    "FREEDOM_SWORN_CONTENT_VERSION",
    "FREEDOM_SWORN_HANDLER_KEY",
    "FREEDOM_SWORN_PASSIVE_EFFECT_HANDLER_KEY",
    "create_freedom_sworn_identity_unit",
    "create_freedom_sworn_passive_unit",
]
