"""月感电与雷暴云的稳定 key 和资料基线常量。"""

from genshin_sim.core.elements import AuraAmount

LUNAR_ELECTRO_CHARGED_REACTION_KEY = "reaction.lunar_electro_charged"
# 反应键承担反应身份；伤害标签只作为 DamageProfile 的主攻击标签。
LUNAR_ELECTRO_CHARGED_DAMAGE_TAG = "月感电"
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

# 资料基线：反应月感电的反应系数 3.0，与角色月感电（直伤）倍率同值。
#
# 口径：本系数**不折入分配权重**。反应复合伤害先按本系数逐组分结算，再按
# ``LUNAR_COMPOSITE_WEIGHTS``（最高 0.60、第二 0.30、其余 0.05）聚合，因此最高
# 组分的实际系数是 3.0 × 0.60 = 1.8。资料另有一套等价口径：把最高权重折进反应
# 倍率，写成「反应倍率 1.8」并配「1 : 1/2 : 1/12」分配。两套口径逐组分等价
# （0.60 : 0.30 : 0.05 == 1 : 1/2 : 1/12），换口径时不得只改一边，否则会重复计入 0.60。
#
# 出处：米游社《元素反应(高等元素论)》(article/25901063)、米游社《月曜反应》
# (article/77019346)、BWIKI 元素反应页；详见
# docs/契约/元素反应/反应/月感电反应契约.md §5。
LUNAR_ELECTRO_CHARGED_REACTION_MULTIPLIER = 3.0
