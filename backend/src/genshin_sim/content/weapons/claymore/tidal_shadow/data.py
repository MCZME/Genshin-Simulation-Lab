"""浪影阔剑内容数据"""

from __future__ import annotations

TIDAL_SHADOW_KEY_PREFIX = "weapon.tidal_shadow"
TIDAL_SHADOW_HANDLER_KEY = TIDAL_SHADOW_KEY_PREFIX
TIDAL_SHADOW_PASSIVE_EFFECT_HANDLER_KEY = f"{TIDAL_SHADOW_KEY_PREFIX}.passive"
TIDAL_SHADOW_CONTENT_VERSION = "release"

# 「巡航的白浪」的属性词条键。
TIDAL_SHADOW_ATK_TERM_KEY = f"{TIDAL_SHADOW_KEY_PREFIX}.atk_percent"

# 帧率基准：资产效果参数以秒记录时间，运行态以帧推进。
FRAMES_PER_SECOND = 60

# 文案常量（取自资产效果文案，不是我们维护的词汇表）：
# - 受到治疗后攻击力提升，持续 8 秒；
# - 角色处于队伍后台也能触发。
DURATION_SECONDS = 8.0

# 资产效果参数的位置约定：components[0] 攻击力加成。
ATK_PERCENT_COMPONENT_INDEX = 0
REQUIRED_COMPONENT_COUNT = 1
