"""星超导稳定 key。"""

STELLAR_CONDUCT_REACTION_KEY = "reaction.stellar_conduct"
# 反应键承担反应身份；伤害标签只作为 DamageProfile 的主攻击标签。
# 直伤星超导按伤害元素拆两个标签；角色侧接线落地前暂无生产消费端。
STELLAR_CONDUCT_CRYO_DAMAGE_TAG = "星超导冰"
STELLAR_CONDUCT_ELECTRO_DAMAGE_TAG = "星超导雷"
STELLAR_CONDUCT_HANDLER_KEY = "reaction_handler.stellar_conduct"
STELLAR_CONDUCT_CAPABILITY_KEY = "reaction_capability:stellar_conduct"
STELLAR_CONDUCT_FIELD_STATE_KEY = "reaction_state.polestar_field"
STELLAR_CONDUCT_COUNTER_STATE_KEY = "reaction_state.stellar_conduct_counter"
STELLAR_CONDUCT_TEAM_SCOPE = "player_team"
STELLAR_CONDUCT_FIELD_SPATIAL_PROFILE_KEY = "reaction_spatial_profile.polestar_field"
STELLAR_CONDUCT_INCOMING_CRYO_ON_ELECTRO = "stellar_incoming_cryo_on_electro"
STELLAR_CONDUCT_INCOMING_ELECTRO_ON_CRYO = "stellar_incoming_electro_on_cryo"
STELLAR_CONDUCT_CRYO_ON_ELECTRO_PROFILE_KEY = (
    "reaction_profile.stellar_conduct.incoming_cryo_on_electro"
)
STELLAR_CONDUCT_ELECTRO_ON_CRYO_PROFILE_KEY = (
    "reaction_profile.stellar_conduct.incoming_electro_on_cryo"
)
STELLAR_CONDUCT_FIELD_RADIUS = 12.0
