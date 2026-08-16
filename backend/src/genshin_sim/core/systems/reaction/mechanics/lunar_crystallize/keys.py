"""月结晶与月笼的稳定 key 和资料基线常量。"""

from __future__ import annotations

LUNAR_CRYSTALLIZE_REACTION_KEY = "reaction.lunar_crystallize"
LUNAR_CRYSTALLIZE_HANDLER_KEY = "reaction_handler.lunar_crystallize"

LUNAR_INCOMING_GEO_ON_HYDRO = "lunar_incoming_geo_on_hydro"

LUNAR_CRYSTALLIZE_GEO_ON_HYDRO_PROFILE_KEY = (
    "reaction_profile.lunar_crystallize.incoming_geo_on_hydro"
)
LUNAR_CRYSTALLIZE_HARMONY_ATTACK_PROFILE_KEY = "reaction_profile.lunar_crystallize.harmony_attack"

LUNAR_CRYSTALLIZE_DAMAGE_PROFILE_KEY = "damage_profile.reaction.lunar_crystallize"
LUNAR_CRYSTALLIZE_DAMAGE_KIND_KEY = "reaction_damage.lunar_crystallize"
LUNAR_CRYSTALLIZE_CAPABILITY_KEY = "reaction_capability:lunar_crystallize"

LUNAR_CAGE_STATE_KEY = "reaction_state.lunar_cage"
LUNAR_CRYSTALLIZE_ACCUMULATOR_STATE_KEY = "reaction_state.lunar_crystallize_accumulator"
LUNAR_CAGE_SPATIAL_PROFILE_KEY = "reaction_spatial_profile.lunar_cage"
LUNAR_CAGE_TEAM_SCOPE = "player_team"

# 资料基线：月笼在被触发目标周围 3~3.5 米半径圆周上等距排布，冻结中点值。
LUNAR_CAGE_COUNT = 3
LUNAR_CAGE_PLACEMENT_RADIUS = 3.25

# 资料基线：月笼索敌范围为半径 12 米、高 5 米的圆柱体积。
LUNAR_CAGE_AGGRO_RADIUS = 12.0
LUNAR_CAGE_AGGRO_HEIGHT = 5.0

# 月笼超过 9 秒未进行谐奏攻击时销毁（540 帧）。
LUNAR_CAGE_LIFETIME_FRAMES = 540

# 投射物飞行帧数 = 0.35 秒 × 60；发射后到命中前月笼不能再次攻击。
LUNAR_CAGE_PROJECTILE_FLIGHT_FRAMES = 21

# 共享累计器最多储存 4 层记录，每 3 次月结晶触发一次谐奏。
LUNAR_CRYSTALLIZE_ACCUMULATOR_MAX_LAYERS = 4
LUNAR_CRYSTALLIZE_HARMONY_TRIGGER_COUNT = 3

# 基线采用角色月结晶反应倍率 1.6；反应月结晶独立倍率以文档资料为准。
LUNAR_CRYSTALLIZE_REACTION_MULTIPLIER = 1.6
