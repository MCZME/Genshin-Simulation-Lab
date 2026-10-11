"""讨龙英杰谭内容数据：稳定键、版本与被动数值口径。

资产来源：Project Amber / Yatta 当前默认数据（``weapon:14302``）。
被动「传承」：主动切换角色时，新登场的角色攻击力提升，持续 10 秒，
该效果每 20 秒只能触发一次。
"""

from __future__ import annotations

THRILLING_TALES_KEY_PREFIX = "weapon.thrilling_tales_of_dragon_slayers"
THRILLING_TALES_HANDLER_KEY = THRILLING_TALES_KEY_PREFIX
THRILLING_TALES_PASSIVE_EFFECT_HANDLER_KEY = f"{THRILLING_TALES_KEY_PREFIX}.passive"
THRILLING_TALES_CONTENT_VERSION = "dev-thrilling-tales"

# 攻击力 Buff「传承」的属性词条键。
THRILLING_TALES_ATK_TERM_KEY = f"{THRILLING_TALES_KEY_PREFIX}.atk_percent"

# 帧率基准：资产效果参数以秒记录时间，运行态以帧推进。
FRAMES_PER_SECOND = 60

# 文案常量（取自资产效果文案）：
# - 新登场角色的攻击力提升持续 10 秒；
# - 每 20 秒至多触发一次。
BUFF_DURATION_SECONDS = 10.0
TRIGGER_INTERVAL_SECONDS = 20.0

# 资产效果参数的位置约定：components[0] 是攻击力提升。
ATK_PERCENT_COMPONENT_INDEX = 0
