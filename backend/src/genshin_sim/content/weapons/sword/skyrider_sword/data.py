"""飞天御剑内容数据：稳定键、版本与被动数值口径。

资产来源：Project Amber / Yatta 当前默认数据（``weapon:11306``）。
被动「决心」：施放元素爆发后，攻击力和移动速度提升，持续 15 秒。

范围边界：移动速度在当前仿真中没有属性与位移语义（与双风共鸣移速同状态），
按 no-op 处理并在此记录；攻击力提升完整实现。
"""

from __future__ import annotations

SKYRIDER_SWORD_KEY_PREFIX = "weapon.skyrider_sword"
SKYRIDER_SWORD_HANDLER_KEY = SKYRIDER_SWORD_KEY_PREFIX
SKYRIDER_SWORD_PASSIVE_EFFECT_HANDLER_KEY = f"{SKYRIDER_SWORD_KEY_PREFIX}.passive"
SKYRIDER_SWORD_CONTENT_VERSION = "dev-skyrider-sword"

# 攻击力 Buff「决心」的属性词条键。
SKYRIDER_SWORD_ATK_TERM_KEY = f"{SKYRIDER_SWORD_KEY_PREFIX}.atk_percent"

# 帧率基准：资产效果参数以秒记录时间，运行态以帧推进。
FRAMES_PER_SECOND = 60

# 文案常量（取自资产效果文案）：攻击力提升持续 15 秒。
BUFF_DURATION_SECONDS = 15.0

# 触发面：装备者施放元素爆发（ability_key 与圣遗物触发面同源）。
TRIGGER_ABILITY_KEY = "elemental_burst"

# 资产效果参数的位置约定：components[0] 是攻击力提升。
ATK_PERCENT_COMPONENT_INDEX = 0
