"""月结晶与月笼的稳定 key 和资料基线常量。"""

from __future__ import annotations

LUNAR_CRYSTALLIZE_REACTION_KEY = "reaction.lunar_crystallize"
# 反应键承担反应身份；伤害标签只作为 DamageProfile 的主攻击标签。
LUNAR_CRYSTALLIZE_DAMAGE_TAG = "月结晶"
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

# 资料基线：反应月结晶的反应系数 1.6，与角色月结晶（直伤）倍率同值。
#
# 口径：本系数**不折入分配权重**。反应复合伤害先按本系数逐组分结算，再按
# ``LUNAR_COMPOSITE_WEIGHTS``（最高 0.60、第二 0.30、其余 0.05）聚合，因此最高
# 组分的实际系数是 1.6 × 0.60 = 0.96。资料另有一套等价口径：把最高权重折进反应
# 倍率，写成「反应倍率 0.96」并配「1 : 1/2 : 1/12」分配。两套口径逐组分等价
# （0.60 : 0.30 : 0.05 == 1 : 1/2 : 1/12），换口径时不得只改一边，否则会重复计入 0.60。
#
# 出处：米游社《元素反应(高等元素论)》(article/25901063)、《月结晶伤害公式》页、
# 米游社《月曜反应》(article/77019346)；详见
# docs/契约/元素反应/反应/月结晶反应契约.md §5。
LUNAR_CRYSTALLIZE_REACTION_MULTIPLIER = 1.6
