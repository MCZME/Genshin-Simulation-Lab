"""星扩散稳定 key 与机制常量。"""

STELLAR_SWIRL_REACTION_KEY = "reaction.stellar_swirl"
STELLAR_SWIRL_HANDLER_KEY = "reaction_handler.stellar_swirl"
STELLAR_SWIRL_CAPABILITY_KEY = "reaction_capability:stellar_swirl"
STELLAR_SWIRL_VORTEX_STATE_KEY = "reaction_state.stellar_swirl_vortex"
STELLAR_SWIRL_VORTEX_SCOPE = "battle"
# 跳跃能力 Buff 挂载的位置级队伍作用域 id；与星超导队伍作用域、装配期
# ``PLAYER_TEAM_SCOPE`` 一致，不从空间实体 id 推导。
STELLAR_SWIRL_TEAM_SCOPE = "player_team"
STELLAR_SWIRL_VORTEX_SPATIAL_PROFILE_KEY = "reaction_spatial_profile.stellar_swirl_vortex"
STELLAR_SWIRL_INCOMING_ANEMO_ON_CRYO = "stellar_incoming_anemo_on_cryo"
# 反向方向（风元素自附着敌人被冰攻击触发）依赖 AuraKind 扩展 ANEMO，本期预留不注册。
STELLAR_SWIRL_INCOMING_CRYO_ON_ANEMO = "stellar_incoming_cryo_on_anemo"
STELLAR_SWIRL_ANEMO_ON_CRYO_PROFILE_KEY = "reaction_profile.stellar_swirl.incoming_anemo_on_cryo"

# 星扩散·风：单体即时风伤害；基础系数与去重窗口为当前实现基线，待来源化冻结。
STELLAR_SWIRL_WIND_BASE_MULTIPLIER = 0.75
STELLAR_SWIRL_WIND_DAMAGE_TAG_KEY = "reaction.stellar_swirl.wind"
STELLAR_SWIRL_WIND_DAMAGE_PROFILE_KEY = "reaction_profile.stellar_swirl.wind"
STELLAR_SWIRL_WIND_DAMAGE_KIND_KEY = "reaction_damage.stellar_swirl_wind"
STELLAR_SWIRL_WIND_GATE_DEFINITION_KEY = "reaction_gate.stellar_swirl.wind"
STELLAR_SWIRL_WIND_GATE_WINDOW_FRAMES = 30
# 星扩散·冰：风旋爆炸冰伤害；两档圆柱 AOE 参数为资料数值，高度暂不参与空间查询。
STELLAR_SWIRL_ICE_DAMAGE_TAG_KEY = "reaction.stellar_swirl.ice"
STELLAR_SWIRL_ICE_DAMAGE_PROFILE_KEY = "reaction_profile.stellar_swirl.ice"
STELLAR_SWIRL_ICE_DAMAGE_KIND_KEY = "reaction_damage.stellar_swirl_ice"
STELLAR_SWIRL_ICE_BASE_MULTIPLIER_LOW = 2.0
STELLAR_SWIRL_ICE_BASE_MULTIPLIER_HIGH = 3.0
STELLAR_SWIRL_EXPLOSION_RADIUS_SMALL = 6.0
STELLAR_SWIRL_EXPLOSION_RADIUS_LARGE = 8.0
# 星扩散冰爆炸圆柱 AOE 的高度参数，仅作资料记录；当前空间查询不参与高度。
STELLAR_SWIRL_EXPLOSION_HEIGHT = 4.0
# 星扩散冰爆炸对命中目标附着 1U 冰元素的常规持久 Aura Profile。
STELLAR_SWIRL_ICE_AURA_APPLICATION_PROFILE_KEY = (
    "aura_application_profile.reaction.stellar_swirl.ice"
)
