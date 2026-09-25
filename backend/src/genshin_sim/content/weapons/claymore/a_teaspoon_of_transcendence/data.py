"""超越之匙内容数据：稳定键、版本与被动数值口径。

资产来源：Project Amber / Yatta 当前默认数据（``weapon:12516``）。
被动「白女皇的升变」两段数值按精炼顺序取值，解析规则是本内容包的实现细节。
"""

from __future__ import annotations

A_TEASPOON_OF_TRANSCENDENCE_KEY_PREFIX = "weapon.a_teaspoon_of_transcendence"
A_TEASPOON_OF_TRANSCENDENCE_HANDLER_KEY = A_TEASPOON_OF_TRANSCENDENCE_KEY_PREFIX
A_TEASPOON_OF_TRANSCENDENCE_PASSIVE_EFFECT_HANDLER_KEY = (
    f"{A_TEASPOON_OF_TRANSCENDENCE_KEY_PREFIX}.passive"
)
A_TEASPOON_OF_TRANSCENDENCE_CONTENT_VERSION = "dev-a-teaspoon-of-transcendence"

A_TEASPOON_OF_TRANSCENDENCE_AUDIT_TAG = "a_teaspoon_of_transcendence"

# 帧率基准：资产效果参数以秒记录时间，运行态以帧推进。
FRAMES_PER_SECOND = 60

# 文案常量（取自资产效果文案，不是我们维护的词汇表）：
# - 「超越」持续 5 秒，至多叠加 3 层，每 0.2 秒至多叠加一层；
# - 文案未声明「每层持续时间独立计算」，层数共享统一期限：叠层与满层后再命中
#   都刷新剩余持续时间（Buff 的 stack_refresh 策略）。
LAYER_DURATION_SECONDS = 5.0
MAX_LAYERS = 3
STACK_TRIGGER_INTERVAL_SECONDS = 0.2

# 重击伤害的主攻击标签，取自游戏数据（芭芭拉重击同样使用该标签）。
CHARGED_ATTACK_MAIN_ATTACK_TAG = "重击"

# 敌方目标判据按 entity_id 前缀区分，与西风系列、白湖冬羽一致。
ENEMY_TARGET_PREFIX = "target:"

# 资产效果参数的位置约定：
# components[0] 攻击力加成、components[1] 星超导反应伤害加成（每层）。
ATK_PERCENT_COMPONENT_INDEX = 0
STELLAR_SUPERCONDUCT_BONUS_COMPONENT_INDEX = 1
REQUIRED_COMPONENT_COUNT = 2
