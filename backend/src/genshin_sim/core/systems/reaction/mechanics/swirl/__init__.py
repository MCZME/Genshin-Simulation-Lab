"""普通扩散的生产 Definition、Profile、Gate 与派生伤害适配器。"""

from genshin_sim.core.systems.reaction.mechanics.swirl.mechanic import (
    SWIRL_CRYO_DAMAGE_TAG,
    SWIRL_DAMAGE_TAGS,
    SWIRL_ELECTRO_DAMAGE_TAG,
    SWIRL_HYDRO_DAMAGE_TAG,
    SWIRL_PYRO_DAMAGE_TAG,
    SWIRL_REACTION_KEY,
    SwirlGeneratedImpactDamageInputAdapter,
    SwirlSelectionError,
    swirl_aura_application_profile,
    swirl_damage_profiles,
    swirl_damage_tag_for_element,
    swirl_definition,
    swirl_gate_definitions,
)

__all__ = [
    "SWIRL_CRYO_DAMAGE_TAG",
    "SWIRL_DAMAGE_TAGS",
    "SWIRL_ELECTRO_DAMAGE_TAG",
    "SWIRL_HYDRO_DAMAGE_TAG",
    "SWIRL_PYRO_DAMAGE_TAG",
    "SWIRL_REACTION_KEY",
    "SwirlGeneratedImpactDamageInputAdapter",
    "SwirlSelectionError",
    "swirl_aura_application_profile",
    "swirl_damage_profiles",
    "swirl_damage_tag_for_element",
    "swirl_definition",
    "swirl_gate_definitions",
]
