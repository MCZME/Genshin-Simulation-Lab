"""信使内容包。"""

from genshin_sim.content.weapons.bow.messenger.content import (
    create_messenger_identity_unit,
    create_messenger_passive_unit,
)
from genshin_sim.content.weapons.bow.messenger.data import (
    MESSENGER_CONTENT_VERSION,
    MESSENGER_HANDLER_KEY,
    MESSENGER_PASSIVE_EFFECT_HANDLER_KEY,
)

__all__ = [
    "MESSENGER_CONTENT_VERSION",
    "MESSENGER_HANDLER_KEY",
    "MESSENGER_PASSIVE_EFFECT_HANDLER_KEY",
    "create_messenger_identity_unit",
    "create_messenger_passive_unit",
]
