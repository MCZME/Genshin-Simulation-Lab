"""星超导（Stellar-Conduct）反应。"""

from genshin_sim.core.systems.reaction.states import (
    STELLAR_CONDUCT_COUNTER_WINDOW_FRAMES,
    STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES,
    PolestarFieldState,
    StellarConductAttachmentRecord,
    StellarConductCounterState,
)

from .keys import (
    STELLAR_CONDUCT_CAPABILITY_KEY,
    STELLAR_CONDUCT_COUNTER_STATE_KEY,
    STELLAR_CONDUCT_CRYO_DAMAGE_TAG,
    STELLAR_CONDUCT_ELECTRO_DAMAGE_TAG,
    STELLAR_CONDUCT_HANDLER_KEY,
    STELLAR_CONDUCT_REACTION_KEY,
    STELLAR_CONDUCT_TEAM_SCOPE,
)
from .mechanic import (
    stellar_conduct_definition,
    stellar_conduct_direct_multiplier,
    stellar_conduct_elemental_bonus,
)

__all__ = (
    "STELLAR_CONDUCT_CAPABILITY_KEY",
    "STELLAR_CONDUCT_COUNTER_STATE_KEY",
    "STELLAR_CONDUCT_CRYO_DAMAGE_TAG",
    "STELLAR_CONDUCT_ELECTRO_DAMAGE_TAG",
    "STELLAR_CONDUCT_HANDLER_KEY",
    "STELLAR_CONDUCT_REACTION_KEY",
    "STELLAR_CONDUCT_TEAM_SCOPE",
    "stellar_conduct_definition",
    "stellar_conduct_direct_multiplier",
    "stellar_conduct_elemental_bonus",
    "STELLAR_CONDUCT_COUNTER_WINDOW_FRAMES",
    "STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES",
    "PolestarFieldState",
    "StellarConductAttachmentRecord",
    "StellarConductCounterState",
)
