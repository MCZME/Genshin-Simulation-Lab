"""异世界行记内容包。"""

from genshin_sim.content.weapons.catalyst.otherworldly_story.content import (
    create_otherworldly_story_identity_unit,
    create_otherworldly_story_passive_unit,
)
from genshin_sim.content.weapons.catalyst.otherworldly_story.data import (
    OTHERWORLDLY_STORY_CONTENT_VERSION,
    OTHERWORLDLY_STORY_HANDLER_KEY,
    OTHERWORLDLY_STORY_PASSIVE_EFFECT_HANDLER_KEY,
)

__all__ = [
    "OTHERWORLDLY_STORY_CONTENT_VERSION",
    "OTHERWORLDLY_STORY_HANDLER_KEY",
    "OTHERWORLDLY_STORY_PASSIVE_EFFECT_HANDLER_KEY",
    "create_otherworldly_story_identity_unit",
    "create_otherworldly_story_passive_unit",
]
