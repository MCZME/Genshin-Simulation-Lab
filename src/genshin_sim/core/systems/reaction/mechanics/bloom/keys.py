"""绽放机制簇的稳定 key。"""

BLOOM_REACTION_KEY = "reaction.bloom"
BLOOM_EXPLOSION_REACTION_KEY = "reaction.bloom_explosion"
HYPERBLOOM_REACTION_KEY = "reaction.hyperbloom"
BURGEON_REACTION_KEY = "reaction.burgeon"

BLOOM_HANDLER_KEY = "reaction_handler.bloom"
HYPERBLOOM_HANDLER_KEY = "reaction_handler.hyperbloom"
BURGEON_HANDLER_KEY = "reaction_handler.burgeon"

HYDRO_ON_DENDRO = "incoming_hydro_on_dendro"
HYDRO_ON_QUICKEN = "incoming_hydro_on_quicken"
DENDRO_ON_HYDRO = "incoming_dendro_on_hydro"

BLOOM_HYDRO_ON_DENDRO_PROFILE_KEY = "reaction_profile.bloom.incoming_hydro_on_dendro"
BLOOM_HYDRO_ON_QUICKEN_PROFILE_KEY = "reaction_profile.bloom.incoming_hydro_on_quicken"
BLOOM_DENDRO_ON_HYDRO_PROFILE_KEY = "reaction_profile.bloom.incoming_dendro_on_hydro"
BLOOM_EXPLOSION_PROFILE_KEY = "reaction_profile.bloom_explosion.core_termination"
HYPERBLOOM_PROFILE_KEY = "reaction_profile.hyperbloom.incoming_electro_on_core"
BURGEON_PROFILE_KEY = "reaction_profile.burgeon.incoming_pyro_on_core"

SPRAWLING_SHOT_STATE_KEY = "reaction_state.sprawling_shot"
SPRAWLING_SHOT_SPATIAL_PROFILE_KEY = "reaction_spatial_profile.sprawling_shot"

HYPERBLOOM_DAMAGE_PROFILE_KEY = "damage_profile.reaction.hyperbloom"
BURGEON_DAMAGE_PROFILE_KEY = "damage_profile.reaction.burgeon"
BLOOM_FAMILY_GATE_DEFINITION_KEY = "reaction_gate.bloom_family.damage"
BLOOM_EXPLOSION_DAMAGE_KIND_KEY = "reaction_damage.bloom_explosion"
HYPERBLOOM_DAMAGE_KIND_KEY = "reaction_damage.hyperbloom"
BURGEON_DAMAGE_KIND_KEY = "reaction_damage.burgeon"

BLOOM_DAMAGE_TARGET_POLICY_KEY = "reaction_target.bloom_damage"
HYPERBLOOM_LOCK_TARGET_POLICY_KEY = "reaction_target.hyperbloom_lock"
