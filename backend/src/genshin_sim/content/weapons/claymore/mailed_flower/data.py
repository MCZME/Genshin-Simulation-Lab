"""饰铁之花内容数据"""

from __future__ import annotations

MAILED_FLOWER_KEY_PREFIX = "weapon.mailed_flower"
MAILED_FLOWER_HANDLER_KEY = MAILED_FLOWER_KEY_PREFIX
MAILED_FLOWER_PASSIVE_EFFECT_HANDLER_KEY = f"{MAILED_FLOWER_KEY_PREFIX}.passive"
MAILED_FLOWER_CONTENT_VERSION = "dev"

# 「风与花的密语」的属性词条键。
MAILED_FLOWER_ATK_TERM_KEY = f"{MAILED_FLOWER_KEY_PREFIX}.atk_percent"
MAILED_FLOWER_EM_TERM_KEY = f"{MAILED_FLOWER_KEY_PREFIX}.elemental_mastery"

# 帧率基准：资产效果参数以秒记录时间，运行态以帧推进。
FRAMES_PER_SECOND = 60

# 文案常量（取自资产效果文案，不是我们维护的词汇表）：
# - 元素战技命中敌人或触发元素反应后的 8 秒内，攻击力提升、元素精通提升。
DURATION_SECONDS = 8.0

# 元素战技伤害的主攻击标签，取自游戏数据。
ELEMENTAL_SKILL_MAIN_ATTACK_TAG = "元素战技"

# 敌方目标判据按 entity_id 前缀区分。
ENEMY_TARGET_PREFIX = "target:"

# 资产效果参数的位置约定：
# components[0] 攻击力加成、components[1] 元素精通提升（固定值）。
ATK_PERCENT_COMPONENT_INDEX = 0
ELEMENTAL_MASTERY_COMPONENT_INDEX = 1
REQUIRED_COMPONENT_COUNT = 2
