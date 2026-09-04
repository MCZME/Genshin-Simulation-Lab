"""绽放系列的静态伤害和实体 Profile。"""

from dataclasses import dataclass

from genshin_sim.core.elements import Element
from genshin_sim.core.systems.reaction.mechanics.bloom.keys import (
    BLOOM_EXPLOSION_DAMAGE_KIND_KEY,
    BLOOM_FAMILY_GATE_DEFINITION_KEY,
    BURGEON_DAMAGE_KIND_KEY,
    BURGEON_DAMAGE_PROFILE_KEY,
    HYPERBLOOM_DAMAGE_KIND_KEY,
    HYPERBLOOM_DAMAGE_PROFILE_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.dendro_core import (
    DENDRO_CORE_TERMINATION_DAMAGE_PROFILE_KEY,
)


@dataclass(frozen=True, slots=True)
class BloomTerminationDamageProfile:
    profile_key: str
    damage_profile_key: str
    damage_kind_key: str
    monster_multiplier: float
    character_multiplier: float
    radius: float
    gate_definition_key: str = BLOOM_FAMILY_GATE_DEFINITION_KEY
    damage_element: Element = Element.DENDRO


BLOOM_EXPLOSION_DAMAGE_PROFILE = BloomTerminationDamageProfile(
    "reaction_profile.bloom_explosion.core_termination",
    DENDRO_CORE_TERMINATION_DAMAGE_PROFILE_KEY,
    BLOOM_EXPLOSION_DAMAGE_KIND_KEY,
    2.0,
    0.1,
    5.0,
)
HYPERBLOOM_DAMAGE_PROFILE = BloomTerminationDamageProfile(
    "reaction_profile.hyperbloom.incoming_electro_on_core",
    HYPERBLOOM_DAMAGE_PROFILE_KEY,
    HYPERBLOOM_DAMAGE_KIND_KEY,
    3.0,
    0.15,
    1.0,
)
BURGEON_DAMAGE_PROFILE = BloomTerminationDamageProfile(
    "reaction_profile.burgeon.incoming_pyro_on_core",
    BURGEON_DAMAGE_PROFILE_KEY,
    BURGEON_DAMAGE_KIND_KEY,
    3.0,
    0.15,
    5.0,
)
