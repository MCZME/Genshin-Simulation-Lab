"""飞天大御剑内容数据：稳定键、版本与被动数值口径。

资产来源：Project Amber / Yatta 当前默认数据（``weapon:12306``）。
被动「勇气」：普通攻击和重击命中时攻击力提升，持续 6 秒，至多叠加 4 层，
每 0.5 秒至多触发一次。
"""

from __future__ import annotations

SKYRIDER_GREATSWORD_KEY_PREFIX = "weapon.skyrider_greatsword"
SKYRIDER_GREATSWORD_HANDLER_KEY = SKYRIDER_GREATSWORD_KEY_PREFIX
SKYRIDER_GREATSWORD_PASSIVE_EFFECT_HANDLER_KEY = f"{SKYRIDER_GREATSWORD_KEY_PREFIX}.passive"
SKYRIDER_GREATSWORD_CONTENT_VERSION = "dev-skyrider-greatsword"

# 叠层 Buff「勇气」的属性词条键。
SKYRIDER_GREATSWORD_ATK_TERM_KEY = f"{SKYRIDER_GREATSWORD_KEY_PREFIX}.atk_percent"

# 帧率基准：资产效果参数以秒记录时间，运行态以帧推进。
FRAMES_PER_SECOND = 60

# 文案常量（取自资产效果文案）：
# - 攻击力提升持续 6 秒，至多叠加 4 层；
# - 每 0.5 秒至多触发一次叠层。
LAYER_DURATION_SECONDS = 6.0
MAX_LAYERS = 4
STACK_TRIGGER_INTERVAL_SECONDS = 0.5

# 触发用主攻击标签：普通攻击与重击。
TRIGGER_ATTACK_TAGS = ("普通攻击", "重击")

# 资产效果参数的位置约定：components[0] 是每层攻击力加成。
ATK_PERCENT_COMPONENT_INDEX = 0
