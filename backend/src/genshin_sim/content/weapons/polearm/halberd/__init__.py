"""钺矛内容包。"""

from genshin_sim.content.weapons.polearm.halberd.content import (
    create_halberd_identity_unit,
    create_halberd_passive_unit,
)
from genshin_sim.content.weapons.polearm.halberd.data import (
    HALBERD_CONTENT_VERSION,
    HALBERD_HANDLER_KEY,
    HALBERD_PASSIVE_EFFECT_HANDLER_KEY,
)

__all__ = [
    "HALBERD_CONTENT_VERSION",
    "HALBERD_HANDLER_KEY",
    "HALBERD_PASSIVE_EFFECT_HANDLER_KEY",
    "create_halberd_identity_unit",
    "create_halberd_passive_unit",
]
