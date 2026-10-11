"""吃虎鱼刀内容数据：稳定键、版本与被动数值口径。

资产来源：Project Amber / Yatta 当前默认数据（``weapon:11305``）。
被动「决」：攻击命中时，有 50% 的概率对单个敌人造成攻击力伤害，
该效果每 15 秒至多触发一次（精炼缩短间隔）。
"""

from __future__ import annotations

from genshin_sim.core.elements import Element

FILLET_BLADE_KEY_PREFIX = "weapon.fillet_blade"
FILLET_BLADE_HANDLER_KEY = FILLET_BLADE_KEY_PREFIX
FILLET_BLADE_PASSIVE_EFFECT_HANDLER_KEY = f"{FILLET_BLADE_KEY_PREFIX}.passive"
FILLET_BLADE_CONTENT_VERSION = "dev-fillet-blade"

# proc 命中键与主攻击标签：武器追加伤害使用独立标签，不与普攻/战技混叠。
# 标签口径说明：武器 proc 资料表中本武器的攻击标签为「-」（空），而仿真契约
# 要求主攻击标签非空，此处按武器 proc 的通用标签「武器技能」统一处理（与
# 苍翠猎弓、天空之翼等 proc 资料条目同标签），属于工程口径而非源数据。
FILLET_BLADE_PROC_IMPACT_KEY = f"{FILLET_BLADE_KEY_PREFIX}.proc"
FILLET_BLADE_PROC_ATTACK_TAG = "武器技能"
FILLET_BLADE_PROC_DISPLAY_NAME = "决"

# 帧率基准：资产效果参数以秒记录时间，运行态以帧推进。
FRAMES_PER_SECOND = 60

# 触发概率：文案声明为 50%，资产效果参数不含概率，由本内容包声明。
TRIGGER_PROBABILITY = 0.5

# proc 元素：物理（追加物理伤害）。
PROC_ELEMENT = Element.PHYSICAL

# 资产效果参数的位置约定：components[0] 追加伤害的攻击力倍率、components[1] 间隔秒数。
MULTIPLIER_COMPONENT_INDEX = 0
INTERVAL_SECONDS_COMPONENT_INDEX = 1
