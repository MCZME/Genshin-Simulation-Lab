"""奥黛塔内容数据：稳定键、命中数据与动作帧表。

数据与解释逻辑分离：``actions.py`` 只保留解释器与动作编译，``content.py``
只负责内容单元编译。命中几何、索敌、打击类型、衰减序列/衰减标签与元素量
取自维护者提供的命中数据表（2026-10-03），动作帧与取消窗口取自同日提供的
gcsim 动作帧数据（60fps，与仓库帧制一致）；倍率仍来自资产库倍率表。
"""

from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.content.generic.plunge import PLUNGE_ATTACK_DATA_BY_WEAPON_TYPE
from genshin_sim.content.generic.timed_action import TimedActionSpec, TimedImpactPointSpec
from genshin_sim.core.actions import SearchAreaSpec, TargetingSpec
from genshin_sim.core.elements import AuraAmount, Element
from genshin_sim.core.impacts import StrikeType
from genshin_sim.core.space import Vector3
from genshin_sim.core.systems.aura import AuraStrength

ODETTE_CHARACTER_HANDLER_KEY = "character.odette"
ODETTE_ASSET_KEY = "character:10000150"
ODETTE_CONTENT_VERSION = "dev-basic-kit"

# ---------------------------------------------------------------------------
# 被动与命座。效果行 handler 键对齐 sandrone 命名；P4–P6 与 C1–C6 的行为由
# 对应效果单元承载（P8 生活天赋为空实现）。
# ---------------------------------------------------------------------------
ODETTE_PASSIVE_P4_HANDLER_KEY = "character.odette.passive.p4"
ODETTE_PASSIVE_P5_HANDLER_KEY = "character.odette.passive.p5"
ODETTE_PASSIVE_P6_HANDLER_KEY = "character.odette.passive.p6"
# P8 回响中的冬梦（至冬区域特产探测）：不参与仿真，bootstrap 注册空效果 handler。
ODETTE_PASSIVE_P8_HANDLER_KEY = "character.odette.passive.p8"

ODETTE_CONSTELLATION_C1_HANDLER_KEY = "character.odette.constellation.c1"
ODETTE_CONSTELLATION_C2_HANDLER_KEY = "character.odette.constellation.c2"
ODETTE_CONSTELLATION_C3_HANDLER_KEY = "character.odette.constellation.c3"
ODETTE_CONSTELLATION_C4_HANDLER_KEY = "character.odette.constellation.c4"
ODETTE_CONSTELLATION_C5_HANDLER_KEY = "character.odette.constellation.c5"
ODETTE_CONSTELLATION_C6_HANDLER_KEY = "character.odette.constellation.c6"

# ---------------------------------------------------------------------------
# 动作与影响点键。
# ---------------------------------------------------------------------------
ODETTE_NORMAL_ATTACK_1_ACTION_KEY = "character.odette.normal_attack.1"
ODETTE_NORMAL_ATTACK_2_ACTION_KEY = "character.odette.normal_attack.2"
ODETTE_NORMAL_ATTACK_3_ACTION_KEY = "character.odette.normal_attack.3"
ODETTE_NORMAL_ATTACK_4_ACTION_KEY = "character.odette.normal_attack.4"
ODETTE_NORMAL_ATTACK_5_ACTION_KEY = "character.odette.normal_attack.5"
ODETTE_CHARGED_ATTACK_ACTION_KEY = "character.odette.charged_attack"
ODETTE_ELEMENTAL_SKILL_ACTION_KEY = "character.odette.elemental_skill"
ODETTE_SPECIAL_ELEMENTAL_SKILL_ACTION_KEY = "character.odette.special_elemental_skill"
ODETTE_ELEMENTAL_BURST_ACTION_KEY = "character.odette.elemental_burst"
ODETTE_JUMP_ACTION_KEY = "character.odette.jump"
ODETTE_PLUNGE_ACTION_KEY = "character.odette.plunge"

# 单手剑普攻未获转化时为物理：物理是伤害侧合法元素，但不参与元素交互、不形成
# 附着（sandrone 双手剑同款处理）；命中数据表普攻行的「元素量 1」仅在该攻击
# 具元素时生效，未来接入附魔/转化时由 infusion 适配器按 weapon_gauge 补全。
ODETTE_MELEE_ELEMENT = Element.PHYSICAL
ODETTE_DAMAGE_ELEMENT = Element.CRYO
ODETTE_DAMAGE_ELEMENTAL_STRENGTH = AuraStrength.WEAK
ODETTE_DAMAGE_ELEMENTAL_AMOUNT = AuraAmount.one()
# 内置默认衰减序列；命中数据表普攻/重击/爆发行均使用「默认」。
ODETTE_DAMAGE_ICD_SEQUENCE_KEY = "默认"
ODETTE_NORMAL_ICD_TAG_KEY = "普通攻击"
ODETTE_ELEMENTAL_BURST_ICD_TAG_KEY = "元素爆发"

# 普攻五段：三段为 3A/3B 双命中（同一动作两个影响点，帧 16/31）。
ODETTE_NORMAL_ATTACK_1_IMPACT_KEY = f"{ODETTE_NORMAL_ATTACK_1_ACTION_KEY}.hit"
ODETTE_NORMAL_ATTACK_2_IMPACT_KEY = f"{ODETTE_NORMAL_ATTACK_2_ACTION_KEY}.hit"
ODETTE_NORMAL_ATTACK_3A_IMPACT_KEY = f"{ODETTE_NORMAL_ATTACK_3_ACTION_KEY}.hit_3a"
ODETTE_NORMAL_ATTACK_3B_IMPACT_KEY = f"{ODETTE_NORMAL_ATTACK_3_ACTION_KEY}.hit_3b"
ODETTE_NORMAL_ATTACK_4_IMPACT_KEY = f"{ODETTE_NORMAL_ATTACK_4_ACTION_KEY}.hit"
ODETTE_NORMAL_ATTACK_5_IMPACT_KEY = f"{ODETTE_NORMAL_ATTACK_5_ACTION_KEY}.hit"
ODETTE_CHARGED_ATTACK_IMPACT_KEY = f"{ODETTE_CHARGED_ATTACK_ACTION_KEY}.hit"
ODETTE_ELEMENTAL_SKILL_IMPACT_KEY = f"{ODETTE_ELEMENTAL_SKILL_ACTION_KEY}.hit"
ODETTE_SPECIAL_DOT_1_IMPACT_KEY = f"{ODETTE_SPECIAL_ELEMENTAL_SKILL_ACTION_KEY}.dot_1"
ODETTE_SPECIAL_DOT_2_IMPACT_KEY = f"{ODETTE_SPECIAL_ELEMENTAL_SKILL_ACTION_KEY}.dot_2"
ODETTE_SPECIAL_DOT_3_IMPACT_KEY = f"{ODETTE_SPECIAL_ELEMENTAL_SKILL_ACTION_KEY}.dot_3"
ODETTE_SPECIAL_END_IMPACT_KEY = f"{ODETTE_SPECIAL_ELEMENTAL_SKILL_ACTION_KEY}.end"
# 特殊战技恢复影响点（第 1 帧，动作时长内）：展开为 ALIGN_CREATED_ENTITY_TICKS
# 请求，把独舞倒影 tick 调度重锚到施放 +114f（ODETTE_DANCE_RESUME_AFTER_SPECIAL_
# FRAMES，自施放帧起算；影响点在次帧展开，目标帧 = 请求帧 + 113）。无活动倒影
# 时请求被分发器忽略，等价于无需恢复。
ODETTE_SPECIAL_RESUME_IMPACT_KEY = f"{ODETTE_SPECIAL_ELEMENTAL_SKILL_ACTION_KEY}.resume"
ODETTE_SPECIAL_RESUME_IMPACT_FRAME = 1
ODETTE_ELEMENTAL_BURST_ENERGY_SPEND_IMPACT_KEY = f"{ODETTE_ELEMENTAL_BURST_ACTION_KEY}.spend_energy"
ODETTE_ELEMENTAL_BURST_SLASH_1_IMPACT_KEY = f"{ODETTE_ELEMENTAL_BURST_ACTION_KEY}.slash_1"
ODETTE_ELEMENTAL_BURST_SLASH_2_IMPACT_KEY = f"{ODETTE_ELEMENTAL_BURST_ACTION_KEY}.slash_2"
ODETTE_ELEMENTAL_BURST_SLASH_3_IMPACT_KEY = f"{ODETTE_ELEMENTAL_BURST_ACTION_KEY}.slash_3"
ODETTE_ELEMENTAL_BURST_FINAL_IMPACT_KEY = f"{ODETTE_ELEMENTAL_BURST_ACTION_KEY}.final"
ODETTE_PLUNGE_COLLISION_IMPACT_KEY = f"{ODETTE_PLUNGE_ACTION_KEY}.collision"
ODETTE_PLUNGE_LANDING_IMPACT_KEY = f"{ODETTE_PLUNGE_ACTION_KEY}.landing"

# 独舞倒影召唤创建影响点（E 命中帧与爆发第 1 帧各一个，展开为 CREATE_ENTITY）。
ODETTE_SUMMON_CREATE_IMPACT_KEY = f"{ODETTE_CHARACTER_HANDLER_KEY}.summon.create"

# 独舞倒影舞步影响键：请求由轮换 hook 产出（非动作影响点），键用于请求识别
# 与产球/审计匹配。星变体（辉映下额外命中）与冰命中同帧同目标集合。
ODETTE_DANCE_PLUME_IMPACT_KEY = f"{ODETTE_CHARACTER_HANDLER_KEY}.dance.plume"
ODETTE_DANCE_WING_IMPACT_KEY = f"{ODETTE_CHARACTER_HANDLER_KEY}.dance.wing"
ODETTE_PARTICLE_SPAWN_IMPACT_KEY = f"{ODETTE_CHARACTER_HANDLER_KEY}.particle.spawn"

ODETTE_HIT_IMPACT_KEYS = (
    ODETTE_NORMAL_ATTACK_1_IMPACT_KEY,
    ODETTE_NORMAL_ATTACK_2_IMPACT_KEY,
    ODETTE_NORMAL_ATTACK_3A_IMPACT_KEY,
    ODETTE_NORMAL_ATTACK_3B_IMPACT_KEY,
    ODETTE_NORMAL_ATTACK_4_IMPACT_KEY,
    ODETTE_NORMAL_ATTACK_5_IMPACT_KEY,
    ODETTE_CHARGED_ATTACK_IMPACT_KEY,
    ODETTE_ELEMENTAL_SKILL_IMPACT_KEY,
    ODETTE_SPECIAL_DOT_1_IMPACT_KEY,
    ODETTE_SPECIAL_DOT_2_IMPACT_KEY,
    ODETTE_SPECIAL_DOT_3_IMPACT_KEY,
    ODETTE_SPECIAL_END_IMPACT_KEY,
    ODETTE_SPECIAL_RESUME_IMPACT_KEY,
    ODETTE_SUMMON_CREATE_IMPACT_KEY,
    ODETTE_ELEMENTAL_BURST_ENERGY_SPEND_IMPACT_KEY,
    ODETTE_ELEMENTAL_BURST_SLASH_1_IMPACT_KEY,
    ODETTE_ELEMENTAL_BURST_SLASH_2_IMPACT_KEY,
    ODETTE_ELEMENTAL_BURST_SLASH_3_IMPACT_KEY,
    ODETTE_ELEMENTAL_BURST_FINAL_IMPACT_KEY,
    ODETTE_PLUNGE_COLLISION_IMPACT_KEY,
    ODETTE_PLUNGE_LANDING_IMPACT_KEY,
)

NORMAL_ATTACK_INPUT = "normal_attack"
CHARGED_ATTACK_INPUT = "charged_attack"
ELEMENTAL_SKILL_INPUT = "elemental_skill"
ELEMENTAL_BURST_INPUT = "elemental_burst"
JUMP_INPUT = "jump"

# 左键普攻、右键重击（barbara 同款输入位）；特殊战技不占独立输入——施放后
# 6 秒内 E 键被替换为柔板·破晓终奏（见 actions.py 窗口分派）。
INPUT_KIND_BY_KEY = {
    "mouse.left": NORMAL_ATTACK_INPUT,
    "mouse.right": CHARGED_ATTACK_INPUT,
    "keyboard.e": ELEMENTAL_SKILL_INPUT,
    "keyboard.q": ELEMENTAL_BURST_INPUT,
    "keyboard.space": JUMP_INPUT,
}

# ---------------------------------------------------------------------------
# 冷却与特殊战技窗口。
# 帧制为 60 帧/秒；冷却秒数取资产倍率条目（技能冷却时间/破晓终奏冷却时间/
# 冷却时间各 15s），常量随帧表维护（sandrone/barbara 先例）。
# ---------------------------------------------------------------------------
ODETTE_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY = "elemental_skill"
ODETTE_ELEMENTAL_SKILL_COOLDOWN_FRAMES = 900
# 特殊战技独立冷却：独立 ability_key（冷却定义仍为 ELEMENTAL_SKILL 类）。
ODETTE_SPECIAL_SKILL_COOLDOWN_ABILITY_KEY = "special_elemental_skill"
ODETTE_SPECIAL_SKILL_COOLDOWN_FRAMES = 900
ODETTE_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY = "elemental_burst"
ODETTE_ELEMENTAL_BURST_COOLDOWN_FRAMES = 900

# 特殊战技窗口：施放元素战技或元素爆发后 6 秒内 E 被替换为柔板·破晓终奏。
# 窗口锚点记录最近一次 E/Q 施放帧，0 表示窗口未激活；特殊战技施放本身不
# 重设锚点（文本的「施放后」指 E/Q，且特殊战技有独立冷却约束重复施放）。
ODETTE_SPECIAL_WINDOW_FRAMES = 360
ODETTE_STATE_SKILL_WINDOW_ANCHOR_FRAME = "odette_skill_window_anchor_frame"

# ---------------------------------------------------------------------------
# 破晓终奏持续段的专属衰减序列（ICD 表「奥黛塔元素战技」：重置时限 3s、
# 元素量序列 1,0,0,0）。定义随内容单元声明，由破晓终奏持续三段命中消费。
# ---------------------------------------------------------------------------
ODETTE_SPECIAL_SKILL_ICD_SEQUENCE_KEY = "奥黛塔元素战技"
ODETTE_SPECIAL_SKILL_ICD_RESET_FRAMES = 180
ODETTE_SPECIAL_SKILL_ICD_APPLICATION_SEQUENCE = (1, 0, 0, 0)

# 奥黛塔为单手剑：下落攻击取单手剑通用资料（content/generic/plunge.py）。
ODETTE_PLUNGE_ATTACK_DATA = PLUNGE_ATTACK_DATA_BY_WEAPON_TYPE["sword"]

# ---------------------------------------------------------------------------
# 独舞倒影（召唤物）与轮换舞步。
# 节奏参数取自维护者提供的 gcsim 动作帧数据（2026-10-03）：E 命中后 +134f
# 首击；拂羽→旋翼 109f、旋翼→拂羽 125f 交替；特殊战施放 +114f 恢复攻击；
# 爆发施放 +252f 首击，重召唤前已存在时保留拂羽/旋翼顺序。持续时间 20s 取
# 资产倍率条目「独舞倒影持续时间」。倒影由 E 发射并在命中的敌人处停下：
# 位移过程不实现（规划已确认），改为直接在就近敌人位置生成（索敌同舞步
# 口径），飞行时间不计入时序，故首击节奏不变；Q「召唤至身边」取角色位置。
# 轮换节奏由召唤物自身的 tick 调度承载（创建物运行态）：E/Q 施放经创建类型
# 的 build_state 声明初始调度，特殊战技恢复经 ALIGN_CREATED_ENTITY_TICKS 请求
# 重锚（相位保持）。
# ---------------------------------------------------------------------------
ODETTE_DANCE_OBJECT_KEY = "odette.dance_reflection"
ODETTE_DANCE_DURATION_FRAMES = 1200
ODETTE_DANCE_FIRST_ATTACK_AFTER_E_HIT_FRAMES = 134
ODETTE_DANCE_FIRST_ATTACK_AFTER_BURST_FRAMES = 252
ODETTE_DANCE_RESUME_AFTER_SPECIAL_FRAMES = 114
ODETTE_DANCE_PLUME_TO_WING_FRAMES = 109
ODETTE_DANCE_WING_TO_PLUME_FRAMES = 125
# 轮换交替（109/125）以两条并行 tick 调度承载：拂羽/旋翼各自周期 234
# （109+125），首拍错开 109f，展开后即「拂羽→旋翼 109、旋翼→拂羽 125」。
ODETTE_DANCE_STEP_PERIOD_FRAMES = (
    ODETTE_DANCE_PLUME_TO_WING_FRAMES + ODETTE_DANCE_WING_TO_PLUME_FRAMES
)
ODETTE_DANCE_STEP_PLUME = "plume"
ODETTE_DANCE_STEP_WING = "wing"
# 舞步调度键：类型在 build_state 声明的两条 tick 调度（拂羽/旋翼），on_tick
# 按调度键分派产出（调度存储与推进由创建物运行时基座持有）。
ODETTE_DANCE_PLUME_SCHEDULE_KEY = ODETTE_DANCE_STEP_PLUME
ODETTE_DANCE_WING_SCHEDULE_KEY = ODETTE_DANCE_STEP_WING

# 元素战技命中帧（E 动作影响点与轮换首击锚点共用）。
ODETTE_ELEMENTAL_SKILL_HIT_FRAME = 23
# 破晓终奏时间轴：共舞持续三段 11/20/28f，结束星烁段 62f（动画 76f）。
ODETTE_SPECIAL_DOT_FRAMES = (11, 20, 28)
ODETTE_SPECIAL_END_FRAME = 62
# 爆发第 1 帧重召唤/刷新独舞倒影（与能量花费同帧）。
ODETTE_ELEMENTAL_BURST_SUMMON_FRAME = 1

# 命中数据表舞步行与破晓终奏行。舞步索敌「就近」由已实现的「分数」策略承载
# （X/Z 就近、并列取稳定实体 id 较小者，sandrone 棱晶弹先例）。
ODETTE_DANCE_SEARCH_RADIUS = 15.0

# 产球（维护者提供的角色产球表）：战技技能伤害或破晓终奏持续命中触发，
# 5 冰微粒 / 100% / 12s 判定冷却；与命中表「元素战技掉球」附加标签命中面一致。
ODETTE_PARTICLE_TRIGGER_IMPACT_KEYS = (
    ODETTE_ELEMENTAL_SKILL_IMPACT_KEY,
    ODETTE_SPECIAL_DOT_1_IMPACT_KEY,
    ODETTE_SPECIAL_DOT_2_IMPACT_KEY,
    ODETTE_SPECIAL_DOT_3_IMPACT_KEY,
)
ODETTE_PARTICLE_ELEMENT = Element.CRYO
ODETTE_PARTICLE_COUNT = 5
ODETTE_PARTICLE_COOLDOWN_FRAMES = 720
# 待确认：产球载体飞行延迟为占位值（sandrone 同款）。
ODETTE_PARTICLE_TRAVEL_FRAMES = 30
# 产球审计字段：最近一次产球的命中结算帧（0 = 尚未产球）。
ODETTE_STATE_LAST_PARTICLE_FRAME = "odette_last_particle_frame"

# ---------------------------------------------------------------------------
# 华彩（P4 获选者的春祭）：召唤独舞倒影时获得层数 Buff，每层使持有者星烁
# 反应伤害提升（率取资产 dictionary N11500003 props[0] = 0.15，效果行未携带，
# 按桑多涅 data.py 机器常量先例承载并注明出处）；奥黛塔处于队伍后台时每秒
# 清除 1 层并转交给队伍中附近的其他角色（附近简化为全部其他队伍角色：仿真
# 不建模后台角色位置）。持续至独舞倒影退场或重新召唤（Buff 期限对齐召唤物
# 剩余时间实现）。后台 tick 59.25f 平均以 59/60 帧交替承载（gcsim 动作帧
# 数据，2026-10-03）。
# ---------------------------------------------------------------------------
ODETTE_SPLENDOR_BUFF_MECHANIC_KEY = "odette.p4.splendor"


# 定义键按奥黛塔槽位区分（sandrone 改进战术先例）；冲突键与定义键同值，
# 同主体多条申请收敛于单条记录，不同主体各自持层互不冲突。
def odette_splendor_definition_key(slot: int) -> str:
    """华彩 Buff 的定义键（与冲突键同值）。"""

    return f"{ODETTE_SPLENDOR_BUFF_MECHANIC_KEY}.slot:{slot}"


# Buff 词条键：C2（每层华彩再 +7% 攻击力）解锁时随定义携带的攻击力词条，
# 申请值取 C2 行分量、模板按 LINEAR 逐层缩放；C2 未解锁时定义为纯层数载体。
ODETTE_SPLENDOR_ATK_TERM_KEY = "odette.splendor.atk_percent"
ODETTE_SPLENDOR_REACTION_BONUS_PER_STACK = 0.15
# 层数上限为实现边界：C1 清速（2 层/秒）下单次召唤周期（1200f / 59f ≈ 21 tick
# × 2 层 ≈ 41 层）内可转交层数的宽松覆盖，非游戏数值；发放层数（4/6）远低于此。
ODETTE_SPLENDOR_MAX_STACKS = 48
# 后台 tick 整数帧交替序列（平均 59.25f）：59 起步、59/60 交替。
ODETTE_SPLENDOR_TICK_INTERVALS = (59, 60)
# 转交/衰减的 Buff 申请期限跟随召唤物剩余时间；无法解析召唤物时 tick 跳过。
ODETTE_STATE_SPLENDOR_NEXT_TICK_FRAME = "odette_splendor_next_tick_frame"
ODETTE_STATE_SPLENDOR_TICK_PARITY = "odette_splendor_tick_parity"
# 发放（重召唤重置 + 授层）与后台衰减/转交的影响请求审计键。
ODETTE_SPLENDOR_GRANT_IMPACT_KEY = f"{ODETTE_CHARACTER_HANDLER_KEY}.splendor.grant"
ODETTE_SPLENDOR_DECAY_IMPACT_KEY = f"{ODETTE_CHARACTER_HANDLER_KEY}.splendor.decay"

# ---------------------------------------------------------------------------
# 雪鹄之梦（元素爆发）：施放疾板·苍羽一梦后获得的自持标记 Buff，持续 20 秒。
# 效果为「奥黛塔造成的星烁反应伤害提升」，数值随 Q 等级成长，取自资产倍率表
# 元素爆发表条目「雪鹄之梦星烁反应伤害提升」（Lv1 0.14）与「雪鹄之梦持续时间」
# （20 秒）；数值在内容编译期按有效 Q 等级（含 C5 的 +3）编译为确定值，由伤害
# 修饰 provider 在结算期按标记存在性产出词条（D-082）。
# C4「均摊」：获得雪鹄之梦时，队伍中其他角色造成的星烁反应伤害提升其 50%
# （比例取 C4 行 number_1 = 0.5）。
# ---------------------------------------------------------------------------
ODETTE_SWAN_DREAM_BUFF_MECHANIC_KEY = "odette.q.swan_dream"
ODETTE_SWAN_DREAM_BONUS_TALENT_LABEL = "雪鹄之梦星烁反应伤害提升"
ODETTE_SWAN_DREAM_DURATION_TALENT_LABEL = "雪鹄之梦持续时间"
# 发放影响点：与爆发能量花费同帧（Q 施放第 1 帧）。
ODETTE_SWAN_DREAM_GRANT_IMPACT_KEY = f"{ODETTE_ELEMENTAL_BURST_ACTION_KEY}.swan_dream"


def odette_swan_dream_definition_key(slot: int) -> str:
    """雪鹄之梦 Buff 的定义键（与冲突键同值，按槽位区分）。"""

    return f"{ODETTE_SWAN_DREAM_BUFF_MECHANIC_KEY}.slot:{slot}"


# ---------------------------------------------------------------------------
# C1「不曾起舞的清晨，她望向倒影」追加段：特殊战技共舞结束时追加一次冰元素
# 范围伤害（星变体，元素量 0）。倍率取 C1 行 number_2/number_3（300% 星超导 /
# 450% 星扩散）；几何取命中表「C1 额外伤害」行（圆柱 4.5,3.5、偏移 0），索敌
# 与结束段一致（该行索敌列为「-」）。辉映·星扩散走星扩散变体，辉映·星超导或
# 不处于辉映状态走星超导变体（与结束段同口径，见 stellar.py）。
# ---------------------------------------------------------------------------
ODETTE_C1_EXTRA_IMPACT_KEY = f"{ODETTE_SPECIAL_ELEMENTAL_SKILL_ACTION_KEY}.c1_extra"
ODETTE_C1_EXTRA_AOE_RADIUS = 4.5
ODETTE_C1_EXTRA_CONDUCT_DISPLAY_NAME = "破晓终奏追加星超导伤害"
ODETTE_C1_EXTRA_SWIRL_DISPLAY_NAME = "破晓终奏追加星扩散伤害"

# ---------------------------------------------------------------------------
# C2「她想，我要见证雪鹄未见之梦」减抗光环：独舞倒影在场且奥黛塔处于辉映·
# 星烁状态时，倒影附近敌人对应元素抗性 −20%（辉映·星超导：冰、雷；辉映·
# 星扩散：冰、风）。判定周期 60 帧（gcsim 帧表「C2 减抗检查 60f」），按帧号
# 取模触发；每次判定先清除另一变体（以及条件不成立时的本变体）残留，再给
# 命中范围内的目标应用当前变体。
# 「附近」半径未在来源中量化，实现基线取召唤物自身索敌半径（命中表圆柱
# 15,10）——与舞步索敌同口径，待来源确认后替换。
# ---------------------------------------------------------------------------
ODETTE_C2_RESISTANCE_MECHANIC_KEY = "odette.c2.resistance_aura"
ODETTE_C2_CONDUCT_VARIANT = "conduct"
ODETTE_C2_SWIRL_VARIANT = "swirl"
ODETTE_C2_CHECK_INTERVAL_FRAMES = 60
# 光环期限取判定周期的两倍：条件失效由下一次判定显式移除，期限内不会自然过期。
ODETTE_C2_AURA_DURATION_FRAMES = 120
ODETTE_C2_AURA_RADIUS = 15.0
ODETTE_C2_AURA_IMPACT_KEY = f"{ODETTE_CHARACTER_HANDLER_KEY}.c2.resistance_aura"


def odette_c2_resistance_definition_key(slot: int, variant: str) -> str:
    """C2 减抗光环 Buff 的定义键（按变体与槽位区分）。"""

    if variant not in (ODETTE_C2_CONDUCT_VARIANT, ODETTE_C2_SWIRL_VARIANT):
        raise ValueError(f"未知的 C2 减抗变体：{variant}")
    return f"{ODETTE_C2_RESISTANCE_MECHANIC_KEY}.{variant}.slot:{slot}"


# ---------------------------------------------------------------------------
# C4「向上，坠往恍惚、燃烧的蓝空」协同攻击：队伍中的角色对敌人造成星烁反应
# 伤害时，奥黛塔对同一敌人追加一次冰元素范围伤害（星变体，元素量 0），每
# 3.5 秒（210f）至多触发一次，触发后再延迟 5f 落地（gcsim 帧表）。倍率取 C4
# 行 number_3/number_4（66% 星超导 / 99% 星扩散）；变体按**落地时**奥黛塔的
# 辉映状态分派（文本「视为：辉映·星超导或不处于辉映状态…」），无辉映证据时
# 走星超导变体。命中表该行的 AOE 列（圆柱 3.0,4.0）不消费：协同攻击目标为
# 触发命中的敌人（与桑多涅 C4 同口径，行内索敌列为「-」）。
# ---------------------------------------------------------------------------
ODETTE_C4_COORDINATED_IMPACT_KEY = f"{ODETTE_CONSTELLATION_C4_HANDLER_KEY}.coordinated_attack"
ODETTE_C4_COORDINATED_DELAY_FRAMES = 5
ODETTE_C4_COORDINATED_DISPLAY_NAME = "雪鹄·协同攻击"


@dataclass(frozen=True, slots=True)
class OdetteHitData:
    """单个命中的判定数据（命中数据表一行的实现依据列）。

    圆柱区域取第一分量为半径（第二分量高度由 X/Z 模型忽略）；攻击盒区域按
    前后完整边长 / 左右完整边长接入（第三分量高度忽略），偏移保留原始三元组
    并随攻击方向旋转。``icd_tag_key=None`` 表示无衰减序列（逐次独立附着）。
    """

    main_attack_tag: str
    strike_type: StrikeType
    range_type: str
    aoe_shape: str
    aoe_radius: float
    aoe_length: float
    aoe_width: float
    aoe_offset: Vector3
    icd_tag_key: str | None
    icd_sequence_key: str | None = None
    additional_attack_tags: tuple[str, ...] = ()


# 普攻（命中数据表普通攻击 1–5 行；3A/3B 共用普通攻击3 行数据）。
ODETTE_NORMAL_ATTACK_1_HIT = OdetteHitData(
    main_attack_tag="普通攻击1",
    strike_type=StrikeType.SLASH,
    range_type="近战",
    aoe_shape="圆柱",
    aoe_radius=2.0,
    aoe_length=0.0,
    aoe_width=0.0,
    aoe_offset=Vector3(0.0, 0.0, 1.0),
    icd_tag_key=ODETTE_NORMAL_ICD_TAG_KEY,
    icd_sequence_key=ODETTE_DAMAGE_ICD_SEQUENCE_KEY,
)
ODETTE_NORMAL_ATTACK_2_HIT = OdetteHitData(
    main_attack_tag="普通攻击2",
    strike_type=StrikeType.SLASH,
    range_type="近战",
    aoe_shape="圆柱",
    aoe_radius=1.6,
    aoe_length=0.0,
    aoe_width=0.0,
    aoe_offset=Vector3(0.0, 0.0, 0.5),
    icd_tag_key=ODETTE_NORMAL_ICD_TAG_KEY,
    icd_sequence_key=ODETTE_DAMAGE_ICD_SEQUENCE_KEY,
)
ODETTE_NORMAL_ATTACK_3_HIT = OdetteHitData(
    main_attack_tag="普通攻击3",
    strike_type=StrikeType.SLASH,
    range_type="近战",
    aoe_shape="圆柱",
    aoe_radius=1.8,
    aoe_length=0.0,
    aoe_width=0.0,
    aoe_offset=Vector3(0.0, 0.0, 0.4),
    icd_tag_key=ODETTE_NORMAL_ICD_TAG_KEY,
    icd_sequence_key=ODETTE_DAMAGE_ICD_SEQUENCE_KEY,
)
ODETTE_NORMAL_ATTACK_4_HIT = OdetteHitData(
    main_attack_tag="普通攻击4",
    strike_type=StrikeType.SLASH,
    range_type="近战",
    aoe_shape="攻击盒",
    aoe_radius=0.0,
    aoe_length=3.3,
    aoe_width=3.5,
    aoe_offset=Vector3(-0.2, 0.8, -0.6),
    icd_tag_key=ODETTE_NORMAL_ICD_TAG_KEY,
    icd_sequence_key=ODETTE_DAMAGE_ICD_SEQUENCE_KEY,
)
ODETTE_NORMAL_ATTACK_5_HIT = OdetteHitData(
    main_attack_tag="普通攻击5",
    strike_type=StrikeType.SLASH,
    range_type="近战",
    aoe_shape="圆柱",
    aoe_radius=3.7,
    aoe_length=0.0,
    aoe_width=0.0,
    aoe_offset=Vector3(0.0, 0.0, 0.4),
    icd_tag_key=ODETTE_NORMAL_ICD_TAG_KEY,
    icd_sequence_key=ODETTE_DAMAGE_ICD_SEQUENCE_KEY,
)
# 重击（命中数据表重击行；衰减序列按 ICD 表修正为「默认」/标签「普通攻击」）。
ODETTE_CHARGED_ATTACK_HIT = OdetteHitData(
    main_attack_tag="重击",
    strike_type=StrikeType.SLASH,
    range_type="近战",
    aoe_shape="攻击盒",
    aoe_radius=0.0,
    aoe_length=3.3,
    aoe_width=4.2,
    aoe_offset=Vector3(-0.2, 0.8, -0.6),
    icd_tag_key=ODETTE_NORMAL_ICD_TAG_KEY,
    icd_sequence_key=ODETTE_DAMAGE_ICD_SEQUENCE_KEY,
)
# 元素战技初始段（命中数据表元素战技行）：无衰减序列（ICD 表「战技」行为
# 无标签/无冷却）；「元素战技掉球」附加标签是产球 hook 的触发依据之一。
ODETTE_ELEMENTAL_SKILL_HIT = OdetteHitData(
    main_attack_tag="元素战技",
    strike_type=StrikeType.DEFAULT,
    range_type="默认",
    aoe_shape="球",
    aoe_radius=4.0,
    aoe_length=0.0,
    aoe_width=0.0,
    aoe_offset=Vector3(0.0, 0.0, 0.0),
    icd_tag_key=None,
    additional_attack_tags=("元素战技掉球",),
)
# 元素爆发斩击（命中数据表爆发三行）：首段钝击、余为默认；衰减序列「默认」
# + 衰减标签「元素爆发」（维护者 2026-10-03 确认）。
ODETTE_BURST_SLASH_1_HIT = OdetteHitData(
    main_attack_tag="元素爆发",
    strike_type=StrikeType.BLUNT,
    range_type="近战",
    aoe_shape="圆柱",
    aoe_radius=7.0,
    aoe_length=0.0,
    aoe_width=0.0,
    aoe_offset=Vector3(0.0, 0.0, 0.0),
    icd_tag_key=ODETTE_ELEMENTAL_BURST_ICD_TAG_KEY,
    icd_sequence_key=ODETTE_DAMAGE_ICD_SEQUENCE_KEY,
)
ODETTE_BURST_SLASH_2_HIT = OdetteHitData(
    main_attack_tag="元素爆发",
    strike_type=StrikeType.DEFAULT,
    range_type="近战",
    aoe_shape="圆柱",
    aoe_radius=7.0,
    aoe_length=0.0,
    aoe_width=0.0,
    aoe_offset=Vector3(0.0, 0.0, 0.0),
    icd_tag_key=ODETTE_ELEMENTAL_BURST_ICD_TAG_KEY,
    icd_sequence_key=ODETTE_DAMAGE_ICD_SEQUENCE_KEY,
)
ODETTE_BURST_SLASH_3_HIT = ODETTE_BURST_SLASH_2_HIT
ODETTE_BURST_FINAL_HIT = ODETTE_BURST_SLASH_2_HIT

# 破晓终奏持续段（命中数据表「元素战技 破晓终奏持续」行）：专属衰减序列
# 「奥黛塔元素战技」；「元素战技掉球，破晓终奏持续」附加标签与产球表触发面
# 一致（见下方产球常量）。
ODETTE_SPECIAL_DOT_HIT = OdetteHitData(
    main_attack_tag="元素战技",
    strike_type=StrikeType.DEFAULT,
    range_type="远程",
    aoe_shape="圆柱",
    aoe_radius=4.2,
    aoe_length=0.0,
    aoe_width=0.0,
    aoe_offset=Vector3(0.0, 0.0, 0.5),
    icd_tag_key=ODETTE_SPECIAL_SKILL_ICD_SEQUENCE_KEY,
    icd_sequence_key=ODETTE_SPECIAL_SKILL_ICD_SEQUENCE_KEY,
    additional_attack_tags=("元素战技掉球", "破晓终奏持续"),
)
# 舞步冰命中（命中数据表「元素战技 拂羽舞步 / 旋翼舞步」行）：无衰减序列
# （ICD 表无标签/无冷却，逐次独立附着）；星变体（辉映下额外命中）由
# stellar.py 按星超导冰/星扩散冰标签编译，元素量 0、不参与附着。
ODETTE_DANCE_PLUME_HIT = OdetteHitData(
    main_attack_tag="元素战技",
    strike_type=StrikeType.DEFAULT,
    range_type="远程",
    aoe_shape="圆柱",
    aoe_radius=4.0,
    aoe_length=0.0,
    aoe_width=0.0,
    aoe_offset=Vector3(0.0, 0.0, 0.0),
    icd_tag_key=None,
)
ODETTE_DANCE_WING_HIT = OdetteHitData(
    main_attack_tag="元素战技",
    strike_type=StrikeType.DEFAULT,
    range_type="远程",
    aoe_shape="圆柱",
    aoe_radius=4.0,
    aoe_length=0.0,
    aoe_width=0.0,
    aoe_offset=Vector3(0.0, 0.0, 1.0),
    icd_tag_key=None,
)

# 普攻编译计划：倍率条目按 (talent_key, label, 分量序号) 取值；三段伤害条目
# 自带 3A/3B 两个分量。
ODETTE_NORMAL_ATTACK_DAMAGE_PLANS = (
    (ODETTE_NORMAL_ATTACK_1_IMPACT_KEY, "一段伤害", 0, ODETTE_NORMAL_ATTACK_1_HIT),
    (ODETTE_NORMAL_ATTACK_2_IMPACT_KEY, "二段伤害", 0, ODETTE_NORMAL_ATTACK_2_HIT),
    (ODETTE_NORMAL_ATTACK_3A_IMPACT_KEY, "三段伤害", 0, ODETTE_NORMAL_ATTACK_3_HIT),
    (ODETTE_NORMAL_ATTACK_3B_IMPACT_KEY, "三段伤害", 1, ODETTE_NORMAL_ATTACK_3_HIT),
    (ODETTE_NORMAL_ATTACK_4_IMPACT_KEY, "四段伤害", 0, ODETTE_NORMAL_ATTACK_4_HIT),
    (ODETTE_NORMAL_ATTACK_5_IMPACT_KEY, "五段伤害", 0, ODETTE_NORMAL_ATTACK_5_HIT),
)

# 索敌规格来自命中数据表（普攻/重击圆柱 5.0,6.0、战技/爆发圆柱 15,10）。
ODETTE_TARGETING_NORMAL_ATTACK = TargetingSpec(
    search_area=SearchAreaSpec(shape="圆柱", radius=5.0, height=6.0),
    selection_policy_key="分数",
)
ODETTE_TARGETING_SKILL = TargetingSpec(
    search_area=SearchAreaSpec(shape="圆柱", radius=15.0, height=10.0),
    selection_policy_key="分数",
)

ODETTE_NORMAL_ATTACK_ACTION_KEYS = (
    ODETTE_NORMAL_ATTACK_1_ACTION_KEY,
    ODETTE_NORMAL_ATTACK_2_ACTION_KEY,
    ODETTE_NORMAL_ATTACK_3_ACTION_KEY,
    ODETTE_NORMAL_ATTACK_4_ACTION_KEY,
    ODETTE_NORMAL_ATTACK_5_ACTION_KEY,
)

# ---------------------------------------------------------------------------
# 动作帧表（gcsim 动作帧数据，60fps）。取消窗口语义：默认取消等到动画结束
# 帧，普攻连段/重击/战技/爆发/跳跃可从表内帧衔接；duration_frames 覆盖完整
# 伤害时间轴（爆发动画 126f 结束但伤害持续到 144f，故 duration 取 145）。
# ---------------------------------------------------------------------------
ODETTE_ACTION_TABLE: dict[str, TimedActionSpec] = {
    ODETTE_NORMAL_ATTACK_1_ACTION_KEY: TimedActionSpec(
        action_key=ODETTE_NORMAL_ATTACK_1_ACTION_KEY,
        duration_frames=25,
        hit_frame=9,
        impact_key=ODETTE_NORMAL_ATTACK_1_IMPACT_KEY,
        targeting=ODETTE_TARGETING_NORMAL_ATTACK,
        transitions={
            NORMAL_ATTACK_INPUT: 17,
            CHARGED_ATTACK_INPUT: 25,
            ELEMENTAL_SKILL_INPUT: 9,
            ELEMENTAL_BURST_INPUT: 9,
            JUMP_INPUT: 9,
        },
    ),
    ODETTE_NORMAL_ATTACK_2_ACTION_KEY: TimedActionSpec(
        action_key=ODETTE_NORMAL_ATTACK_2_ACTION_KEY,
        duration_frames=23,
        hit_frame=9,
        impact_key=ODETTE_NORMAL_ATTACK_2_IMPACT_KEY,
        targeting=ODETTE_TARGETING_NORMAL_ATTACK,
        transitions={
            NORMAL_ATTACK_INPUT: 19,
            CHARGED_ATTACK_INPUT: 21,
            ELEMENTAL_SKILL_INPUT: 9,
            ELEMENTAL_BURST_INPUT: 9,
            JUMP_INPUT: 9,
        },
    ),
    ODETTE_NORMAL_ATTACK_3_ACTION_KEY: TimedActionSpec(
        action_key=ODETTE_NORMAL_ATTACK_3_ACTION_KEY,
        duration_frames=69,
        impact_points=(
            TimedImpactPointSpec(
                impact_key=ODETTE_NORMAL_ATTACK_3A_IMPACT_KEY,
                frame=16,
                targeting=ODETTE_TARGETING_NORMAL_ATTACK,
            ),
            TimedImpactPointSpec(
                impact_key=ODETTE_NORMAL_ATTACK_3B_IMPACT_KEY,
                frame=31,
                targeting=ODETTE_TARGETING_NORMAL_ATTACK,
            ),
        ),
        transitions={
            NORMAL_ATTACK_INPUT: 54,
            CHARGED_ATTACK_INPUT: 69,
            ELEMENTAL_SKILL_INPUT: 31,
            ELEMENTAL_BURST_INPUT: 31,
            JUMP_INPUT: 31,
        },
    ),
    ODETTE_NORMAL_ATTACK_4_ACTION_KEY: TimedActionSpec(
        action_key=ODETTE_NORMAL_ATTACK_4_ACTION_KEY,
        duration_frames=85,
        hit_frame=15,
        impact_key=ODETTE_NORMAL_ATTACK_4_IMPACT_KEY,
        targeting=ODETTE_TARGETING_NORMAL_ATTACK,
        transitions={
            NORMAL_ATTACK_INPUT: 53,
            CHARGED_ATTACK_INPUT: 73,
            ELEMENTAL_SKILL_INPUT: 15,
            ELEMENTAL_BURST_INPUT: 15,
            JUMP_INPUT: 15,
        },
    ),
    ODETTE_NORMAL_ATTACK_5_ACTION_KEY: TimedActionSpec(
        action_key=ODETTE_NORMAL_ATTACK_5_ACTION_KEY,
        duration_frames=70,
        hit_frame=15,
        impact_key=ODETTE_NORMAL_ATTACK_5_IMPACT_KEY,
        targeting=ODETTE_TARGETING_NORMAL_ATTACK,
        transitions={
            NORMAL_ATTACK_INPUT: 62,
            CHARGED_ATTACK_INPUT: 70,
            ELEMENTAL_SKILL_INPUT: 15,
            ELEMENTAL_BURST_INPUT: 15,
            JUMP_INPUT: 15,
        },
    ),
    ODETTE_CHARGED_ATTACK_ACTION_KEY: TimedActionSpec(
        action_key=ODETTE_CHARGED_ATTACK_ACTION_KEY,
        duration_frames=83,
        hit_frame=30,
        impact_key=ODETTE_CHARGED_ATTACK_IMPACT_KEY,
        targeting=ODETTE_TARGETING_NORMAL_ATTACK,
        transitions={
            NORMAL_ATTACK_INPUT: 83,
            CHARGED_ATTACK_INPUT: 83,
            ELEMENTAL_SKILL_INPUT: 57,
            ELEMENTAL_BURST_INPUT: 58,
            JUMP_INPUT: 30,
        },
    ),
    ODETTE_ELEMENTAL_SKILL_ACTION_KEY: TimedActionSpec(
        action_key=ODETTE_ELEMENTAL_SKILL_ACTION_KEY,
        duration_frames=42,
        impact_points=(
            # 命中与召唤同帧（23f）：独舞倒影随技能伤害一同出现，轮换首击
            # 锚点为「命中后 +134f」（见 actions.py 解释器）。
            TimedImpactPointSpec(
                impact_key=ODETTE_ELEMENTAL_SKILL_IMPACT_KEY,
                frame=ODETTE_ELEMENTAL_SKILL_HIT_FRAME,
                targeting=ODETTE_TARGETING_SKILL,
            ),
            TimedImpactPointSpec(
                impact_key=ODETTE_SUMMON_CREATE_IMPACT_KEY,
                frame=ODETTE_ELEMENTAL_SKILL_HIT_FRAME,
            ),
        ),
        cooldown_start_frame=1,
        cooldown_ability_key=ODETTE_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
        transitions={
            NORMAL_ATTACK_INPUT: 41,
            CHARGED_ATTACK_INPUT: 42,
            ELEMENTAL_SKILL_INPUT: 41,
            ELEMENTAL_BURST_INPUT: 41,
            JUMP_INPUT: 42,
        },
    ),
    # 柔板·破晓终奏：共舞持续冰伤与结束星烁段已随本切片接入（见影响点）。
    ODETTE_SPECIAL_ELEMENTAL_SKILL_ACTION_KEY: TimedActionSpec(
        action_key=ODETTE_SPECIAL_ELEMENTAL_SKILL_ACTION_KEY,
        duration_frames=76,
        impact_points=(
            # 恢复影响点（第 1 帧）：施放即把倒影轮换重锚到 +114f（恢复影响
            # 点展开为 ALIGN_CREATED_ENTITY_TICKS，见 impacts.py）。共舞持续
            # 三段（11/20/28f）+ 结束星烁段（62f），结束段的星变体由影响工厂
            # 按辉映证据分派（见 impacts.py / stellar.py）。
            TimedImpactPointSpec(
                impact_key=ODETTE_SPECIAL_RESUME_IMPACT_KEY,
                frame=ODETTE_SPECIAL_RESUME_IMPACT_FRAME,
            ),
            TimedImpactPointSpec(
                impact_key=ODETTE_SPECIAL_DOT_1_IMPACT_KEY,
                frame=ODETTE_SPECIAL_DOT_FRAMES[0],
                targeting=ODETTE_TARGETING_SKILL,
            ),
            TimedImpactPointSpec(
                impact_key=ODETTE_SPECIAL_DOT_2_IMPACT_KEY,
                frame=ODETTE_SPECIAL_DOT_FRAMES[1],
                targeting=ODETTE_TARGETING_SKILL,
            ),
            TimedImpactPointSpec(
                impact_key=ODETTE_SPECIAL_DOT_3_IMPACT_KEY,
                frame=ODETTE_SPECIAL_DOT_FRAMES[2],
                targeting=ODETTE_TARGETING_SKILL,
            ),
            TimedImpactPointSpec(
                impact_key=ODETTE_SPECIAL_END_IMPACT_KEY,
                frame=ODETTE_SPECIAL_END_FRAME,
                targeting=ODETTE_TARGETING_SKILL,
            ),
        ),
        cooldown_start_frame=1,
        cooldown_ability_key=ODETTE_SPECIAL_SKILL_COOLDOWN_ABILITY_KEY,
        transitions={
            NORMAL_ATTACK_INPUT: 75,
            CHARGED_ATTACK_INPUT: 76,
            ELEMENTAL_SKILL_INPUT: 76,
            ELEMENTAL_BURST_INPUT: 76,
            JUMP_INPUT: 75,
        },
    ),
    ODETTE_ELEMENTAL_BURST_ACTION_KEY: TimedActionSpec(
        action_key=ODETTE_ELEMENTAL_BURST_ACTION_KEY,
        duration_frames=145,
        impact_points=(
            TimedImpactPointSpec(
                impact_key=ODETTE_ELEMENTAL_BURST_ENERGY_SPEND_IMPACT_KEY,
                frame=1,
            ),
            TimedImpactPointSpec(
                impact_key=ODETTE_SUMMON_CREATE_IMPACT_KEY,
                frame=ODETTE_ELEMENTAL_BURST_SUMMON_FRAME,
            ),
            TimedImpactPointSpec(
                impact_key=ODETTE_ELEMENTAL_BURST_SLASH_1_IMPACT_KEY,
                frame=112,
                targeting=ODETTE_TARGETING_SKILL,
            ),
            TimedImpactPointSpec(
                impact_key=ODETTE_ELEMENTAL_BURST_SLASH_2_IMPACT_KEY,
                frame=128,
                targeting=ODETTE_TARGETING_SKILL,
            ),
            TimedImpactPointSpec(
                impact_key=ODETTE_ELEMENTAL_BURST_SLASH_3_IMPACT_KEY,
                frame=140,
                targeting=ODETTE_TARGETING_SKILL,
            ),
            TimedImpactPointSpec(
                impact_key=ODETTE_ELEMENTAL_BURST_FINAL_IMPACT_KEY,
                frame=144,
                targeting=ODETTE_TARGETING_SKILL,
            ),
        ),
        cooldown_start_frame=1,
        cooldown_ability_key=ODETTE_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY,
        transitions={
            NORMAL_ATTACK_INPUT: 108,
            CHARGED_ATTACK_INPUT: 126,
            ELEMENTAL_SKILL_INPUT: 107,
            ELEMENTAL_BURST_INPUT: 126,
            JUMP_INPUT: 109,
        },
    ),
    ODETTE_JUMP_ACTION_KEY: TimedActionSpec(
        action_key=ODETTE_JUMP_ACTION_KEY,
        duration_frames=31,
        transitions={},
    ),
    ODETTE_PLUNGE_ACTION_KEY: TimedActionSpec(
        action_key=ODETTE_PLUNGE_ACTION_KEY,
        duration_frames=1,
        transitions={},
    ),
}
