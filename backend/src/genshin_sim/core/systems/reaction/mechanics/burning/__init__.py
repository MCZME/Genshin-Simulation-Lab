"""普通燃烧的机制定义。"""

from genshin_sim.core.systems.reaction.mechanics.burning.mechanic import (
    BURNING_DAMAGE_BASE_MULTIPLIER,
    BURNING_DAMAGE_KIND_KEY,
    BURNING_DAMAGE_PROFILE_KEY,
    BURNING_GATE_DEFINITION_KEY,
    BURNING_PYRO_APPLICATION_AMOUNT,
    BURNING_PYRO_AURA_APPLICATION_PROFILE_KEY,
    BURNING_REACTION_KEY,
    burning_damage_profile,
    burning_definition,
    burning_gate_definitions,
    burning_pyro_aura_application_profile,
)

__all__ = [
    "BURNING_DAMAGE_KIND_KEY",
    "BURNING_DAMAGE_BASE_MULTIPLIER",
    "BURNING_DAMAGE_PROFILE_KEY",
    "BURNING_GATE_DEFINITION_KEY",
    "BURNING_PYRO_APPLICATION_AMOUNT",
    "BURNING_PYRO_AURA_APPLICATION_PROFILE_KEY",
    "BURNING_REACTION_KEY",
    "burning_damage_profile",
    "burning_definition",
    "burning_gate_definitions",
    "burning_pyro_aura_application_profile",
]
