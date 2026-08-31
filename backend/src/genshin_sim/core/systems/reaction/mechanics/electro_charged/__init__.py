"""普通感电的机制定义。"""

from genshin_sim.core.systems.reaction.mechanics.electro_charged.mechanic import (
    ELECTRO_CHARGED_BASE_MULTIPLIER,
    ELECTRO_CHARGED_DAMAGE_KIND_KEY,
    ELECTRO_CHARGED_DAMAGE_PROFILE_KEY,
    ELECTRO_CHARGED_GATE_DEFINITION_KEY,
    ELECTRO_CHARGED_REACTION_KEY,
    electro_charged_damage_profile,
    electro_charged_definition,
    electro_charged_gate_definitions,
)

__all__ = [
    "ELECTRO_CHARGED_BASE_MULTIPLIER",
    "ELECTRO_CHARGED_DAMAGE_KIND_KEY",
    "ELECTRO_CHARGED_DAMAGE_PROFILE_KEY",
    "ELECTRO_CHARGED_GATE_DEFINITION_KEY",
    "ELECTRO_CHARGED_REACTION_KEY",
    "electro_charged_definition",
    "electro_charged_damage_profile",
    "electro_charged_gate_definitions",
]
