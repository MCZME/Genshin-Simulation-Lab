"""月感电与雷暴云的稳定 key 和资料基线常量。"""

from genshin_sim.core.elements import AuraAmount

LUNAR_ELECTRO_CHARGED_REACTION_KEY = "reaction.lunar_electro_charged"
LUNAR_ELECTRO_CHARGED_HANDLER_KEY = "reaction_handler.lunar_electro_charged"

LUNAR_HYDRO_ON_ELECTRO = "lunar_incoming_hydro_on_electro"
LUNAR_ELECTRO_ON_HYDRO = "lunar_incoming_electro_on_hydro"

LUNAR_ELECTRO_CHARGED_HYDRO_ON_ELECTRO_PROFILE_KEY = (
    "reaction_profile.lunar_electro_charged.incoming_hydro_on_electro"
)
LUNAR_ELECTRO_CHARGED_ELECTRO_ON_HYDRO_PROFILE_KEY = (
    "reaction_profile.lunar_electro_charged.incoming_electro_on_hydro"
)
LUNAR_ELECTRO_CHARGED_ATTACK_PROFILE_KEY = (
    "reaction_profile.lunar_electro_charged.storm_cloud_attack"
)

LUNAR_ELECTRO_CHARGED_DAMAGE_PROFILE_KEY = "damage_profile.reaction.lunar_electro_charged"
LUNAR_ELECTRO_CHARGED_DAMAGE_KIND_KEY = "reaction_damage.lunar_electro_charged"
LUNAR_ELECTRO_CHARGED_GATE_DEFINITION_KEY = "reaction_gate.lunar_electro_charged.damage"
LUNAR_ELECTRO_CHARGED_CAPABILITY_KEY = "reaction_capability:lunar_electro_charged"

LUNAR_STORM_CLOUD_STATE_KEY = "reaction_state.lunar_storm_cloud"
LUNAR_STORM_CLOUD_SPATIAL_PROFILE_KEY = "reaction_spatial_profile.lunar_storm_cloud"
LUNAR_STORM_CLOUD_TEAM_SCOPE = "player_team"

# 资料基线：雷暴云存在 6 秒，首次攻击约 0.25~0.3 秒，后续按周期脉冲；
# 精确移动、索敌范围和云间排斥半径仍待人工确认。
LUNAR_STORM_CLOUD_LIFETIME_FRAMES = 360
LUNAR_STORM_CLOUD_FIRST_ATTACK_INTERVAL_FRAMES = 15
LUNAR_STORM_CLOUD_ATTACK_INTERVAL_FRAMES = 15
LUNAR_STORM_CLOUD_PROXIMITY_RADIUS = 5.0
LUNAR_STORM_CLOUD_ATTACK_RADIUS = 5.0
LUNAR_STORM_CLOUD_ATTACK_CONSUMPTION_AMOUNT = AuraAmount("2/5")

# 基线采用角色月感电反应倍率 3.0；反应月感电的独立倍率仍待可信来源确认。
LUNAR_ELECTRO_CHARGED_REACTION_MULTIPLIER = 3.0
