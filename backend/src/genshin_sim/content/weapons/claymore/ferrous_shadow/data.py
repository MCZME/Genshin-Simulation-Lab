"""铁影阔剑内容数据：稳定键、版本与被动数值口径。

资产来源：Project Amber / Yatta 当前默认数据（``weapon:12301``）。
被动「不屈」：生命值低于 70% 时，重击不会轻易被打断，并提高重击伤害。

范围边界：被动的「重击不会轻易被打断」条款依赖敌方打断/削韧模型，明确不在
当前仿真范围（与下落攻击通用部件同一边界），本内容包按 no-op 处理并在此
记录；增伤条款完整实现。
"""

from __future__ import annotations

FERROUS_SHADOW_KEY_PREFIX = "weapon.ferrous_shadow"
FERROUS_SHADOW_HANDLER_KEY = FERROUS_SHADOW_KEY_PREFIX
FERROUS_SHADOW_PASSIVE_EFFECT_HANDLER_KEY = f"{FERROUS_SHADOW_KEY_PREFIX}.passive"
FERROUS_SHADOW_CONTENT_VERSION = "dev-ferrous-shadow"

# 生命门控标记 Buff：仅作条件证据（marker_only），不携带属性词条。
FERROUS_SHADOW_MARKER_DEFINITION_KEY_TEMPLATE = f"{FERROUS_SHADOW_KEY_PREFIX}.low_hp.slot:{{slot}}"

# 被动主攻击标签：重击。
FERROUS_SHADOW_ATTACK_TAG = "重击"

# 帧率基准：资产效果参数以秒记录时间，运行态以帧推进。
FRAMES_PER_SECOND = 60

# 条件重评与标记续期口径（工程约定，见 hooks.py 模块说明）：
# 每 10 帧（1/6 秒）重评一次条件，标记每次施加持续 20 帧（1/3 秒）。
HP_GATE_REFRESH_INTERVAL_FRAMES = 10
MARKER_DURATION_FRAMES = 20

# 生命阈值：低于 70%。资产效果参数不含阈值，由本内容包按文案声明。
HP_THRESHOLD = 0.7

# 资产效果参数的位置约定：components[0] 重击伤害加成、components[1] 生命阈值。
CHARGED_BONUS_COMPONENT_INDEX = 0
