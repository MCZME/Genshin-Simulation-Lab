"""普通扩散的生产 Definition、Profile、Gate 与派生伤害适配器。"""

from genshin_sim.core.systems.reaction.mechanics.swirl.mechanic import (
    SWIRL_REACTION_KEY,
    SwirlGeneratedImpactDamageInputAdapter,
    SwirlSelectionError,
    swirl_aura_application_profile,
    swirl_damage_profile,
    swirl_definition,
    swirl_gate_definitions,
)

__all__ = [
    "SWIRL_REACTION_KEY",
    "SwirlGeneratedImpactDamageInputAdapter",
    "SwirlSelectionError",
    "swirl_aura_application_profile",
    "swirl_damage_profile",
    "swirl_definition",
    "swirl_gate_definitions",
]
