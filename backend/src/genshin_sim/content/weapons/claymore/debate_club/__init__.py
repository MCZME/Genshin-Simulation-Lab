"""以理服人内容包。"""

from genshin_sim.content.weapons.claymore.debate_club.content import (
    create_debate_club_identity_unit,
    create_debate_club_passive_unit,
)
from genshin_sim.content.weapons.claymore.debate_club.data import (
    DEBATE_CLUB_CONTENT_VERSION,
    DEBATE_CLUB_HANDLER_KEY,
    DEBATE_CLUB_PASSIVE_EFFECT_HANDLER_KEY,
)

__all__ = [
    "DEBATE_CLUB_CONTENT_VERSION",
    "DEBATE_CLUB_HANDLER_KEY",
    "DEBATE_CLUB_PASSIVE_EFFECT_HANDLER_KEY",
    "create_debate_club_identity_unit",
    "create_debate_club_passive_unit",
]
