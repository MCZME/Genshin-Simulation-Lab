"""以理服人内容数据：稳定键、版本与被动数值口径。

官方英文名：Debate Club。
资产来源：Project Amber / Yatta 当前默认数据（``weapon:12305``）。
被动「有话直说」：施放元素战技后，普通攻击和重击命中时会在小范围内额外造成
攻击力伤害。该效果持续 15 秒，伤害每 3 秒只能触发一次。

AOE 形态取自维护者提供的武器 proc 资料表（圆柱 3.0/0.0，见下方常量注）；
资产效果参数本身不含 AOE 半径。
"""

from __future__ import annotations

from genshin_sim.core.elements import Element

DEBATE_CLUB_KEY_PREFIX = "weapon.debate_club"
DEBATE_CLUB_HANDLER_KEY = DEBATE_CLUB_KEY_PREFIX
DEBATE_CLUB_PASSIVE_EFFECT_HANDLER_KEY = f"{DEBATE_CLUB_KEY_PREFIX}.passive"
DEBATE_CLUB_CONTENT_VERSION = "dev-debate-club"

# proc 命中键与主攻击标签：武器追加伤害使用独立标签，不与普攻/战技混叠。
DEBATE_CLUB_PROC_IMPACT_KEY = f"{DEBATE_CLUB_KEY_PREFIX}.proc"
DEBATE_CLUB_PROC_ATTACK_TAG = "武器技能"
DEBATE_CLUB_PROC_DISPLAY_NAME = "有话直说"

# 帧率基准：资产效果参数以秒记录时间，运行态以帧推进。
FRAMES_PER_SECOND = 60

# 文案常量（取自资产效果文案）：
# - 窗口持续 15 秒；
# - proc 每 3 秒至多触发一次。
WINDOW_DURATION_SECONDS = 15.0
PROC_INTERVAL_SECONDS = 3.0

# 触发面：
# - 窗口开启：装备者施放元素战技（ability_key 与圣遗物触发面同源）；
# - proc：普通攻击与重击命中敌人。
TRIGGER_ABILITY_KEY = "elemental_skill"
TRIGGER_ATTACK_TAGS = ("普通攻击", "重击")

# proc 元素：物理（追加物理伤害）。
PROC_ELEMENT = Element.PHYSICAL

# 「小范围」AOE：圆柱，半径 3.0、高 0.0，以命中敌人为锚（偏移 0,0,0）。
# 来源：维护者提供的武器 proc 资料表（weapon:12305 条目）。
PROC_AOE_SHAPE = "圆柱"
PROC_AOE_RADIUS = 3.0

# 资产效果参数的位置约定：components[0] 是追加伤害的攻击力倍率。
MULTIPLIER_COMPONENT_INDEX = 0
