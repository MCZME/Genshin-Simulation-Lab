"""钺矛内容数据：稳定键、版本与被动数值口径。

资产来源：Project Amber / Yatta 当前默认数据（``weapon:13302``）。
被动「沉重」：对普通攻击命中的敌人造成额外攻击力伤害，每 10 秒至多触发一次。
"""

from __future__ import annotations

from genshin_sim.core.elements import Element

HALBERD_KEY_PREFIX = "weapon.halberd"
HALBERD_HANDLER_KEY = HALBERD_KEY_PREFIX
HALBERD_PASSIVE_EFFECT_HANDLER_KEY = f"{HALBERD_KEY_PREFIX}.passive"
HALBERD_CONTENT_VERSION = "dev-halberd"

# proc 命中键与主攻击标签：武器追加伤害使用独立标签，不与普攻/战技混叠。
HALBERD_PROC_IMPACT_KEY = f"{HALBERD_KEY_PREFIX}.proc"
HALBERD_PROC_ATTACK_TAG = "武器技能"
HALBERD_PROC_DISPLAY_NAME = "沉重"

# 帧率基准：资产效果参数以秒记录时间，运行态以帧推进。
FRAMES_PER_SECOND = 60

# 文案常量（取自资产效果文案）：每 10 秒至多触发一次。
TRIGGER_INTERVAL_SECONDS = 10.0

# 触发用主攻击标签：普通攻击。
TRIGGER_ATTACK_TAG = "普通攻击"

# proc 元素：物理（追加物理伤害）。
PROC_ELEMENT = Element.PHYSICAL

# 资产效果参数的位置约定：components[0] 是追加伤害的攻击力倍率。
MULTIPLIER_COMPONENT_INDEX = 0
