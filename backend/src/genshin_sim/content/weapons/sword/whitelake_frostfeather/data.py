"""白湖冬羽内容数据：稳定键、版本与被动数值口径。

资产来源：Project Amber / Yatta 当前默认数据（``weapon:11520``）。
被动「雪鹄的终幕舞」三段数值按精炼顺序取值，解析规则是本内容包的实现细节。
"""

from __future__ import annotations

WHITELAKE_FROSTFEATHER_KEY_PREFIX = "weapon.whitelake_frostfeather"
WHITELAKE_FROSTFEATHER_HANDLER_KEY = WHITELAKE_FROSTFEATHER_KEY_PREFIX
WHITELAKE_FROSTFEATHER_PASSIVE_EFFECT_HANDLER_KEY = f"{WHITELAKE_FROSTFEATHER_KEY_PREFIX}.passive"
WHITELAKE_FROSTFEATHER_CONTENT_VERSION = "dev-whitelake-frostfeather"

# 叠层 Buff「湖色的哀告」的属性词条键。
WHITELAKE_FROSTFEATHER_ATK_TERM_KEY = f"{WHITELAKE_FROSTFEATHER_KEY_PREFIX}.atk_percent"

# 星烁触发回能的 Impact 键。
WHITELAKE_FROSTFEATHER_ENERGY_IMPACT_KEY = f"{WHITELAKE_FROSTFEATHER_KEY_PREFIX}.energy_restore"

# 帧率基准：资产效果参数以秒记录时间，运行态以帧推进。
FRAMES_PER_SECOND = 60

# 文案常量（取自资产效果文案，不是我们维护的词汇表）：
# - 每 0.1 秒至多触发一次叠层；
# - 「湖色的哀告」持续 8 秒，至多叠加 3 层；
# - 触发星烁反应或造成星烁反应伤害后恢复元素能量，每 3.5 秒至多一次。
STACK_TRIGGER_INTERVAL_SECONDS = 0.1
LAYER_DURATION_SECONDS = 8.0
MAX_LAYERS = 3
ENERGY_RESTORE_INTERVAL_SECONDS = 3.5

# 元素战技伤害的主攻击标签，取自游戏数据（芭芭拉元素战技同样使用该标签）。
ELEMENTAL_SKILL_MAIN_ATTACK_TAG = "元素战技"

# 敌方目标判据按 entity_id 前缀区分，与西风系列一致。
ENEMY_TARGET_PREFIX = "target:"

# 资产效果参数的位置约定：
# components[0] 攻击力加成、components[1] 星烁暴击伤害加成、components[2] 回能点数。
ATK_PERCENT_COMPONENT_INDEX = 0
STELLAR_CRIT_DAMAGE_COMPONENT_INDEX = 1
ENERGY_RESTORE_COMPONENT_INDEX = 2
REQUIRED_COMPONENT_COUNT = 3
