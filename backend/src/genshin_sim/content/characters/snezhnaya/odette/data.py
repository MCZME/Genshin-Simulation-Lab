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
# 被动与命座。效果行 handler 键对齐 sandrone 命名；行为在后续切片落地，
# bootstrap 先注册占位实现（P8 生活天赋为空实现）。
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
ODETTE_ELEMENTAL_BURST_ENERGY_SPEND_IMPACT_KEY = f"{ODETTE_ELEMENTAL_BURST_ACTION_KEY}.spend_energy"
ODETTE_ELEMENTAL_BURST_SLASH_1_IMPACT_KEY = f"{ODETTE_ELEMENTAL_BURST_ACTION_KEY}.slash_1"
ODETTE_ELEMENTAL_BURST_SLASH_2_IMPACT_KEY = f"{ODETTE_ELEMENTAL_BURST_ACTION_KEY}.slash_2"
ODETTE_ELEMENTAL_BURST_SLASH_3_IMPACT_KEY = f"{ODETTE_ELEMENTAL_BURST_ACTION_KEY}.slash_3"
ODETTE_ELEMENTAL_BURST_FINAL_IMPACT_KEY = f"{ODETTE_ELEMENTAL_BURST_ACTION_KEY}.final"
ODETTE_PLUNGE_COLLISION_IMPACT_KEY = f"{ODETTE_PLUNGE_ACTION_KEY}.collision"
ODETTE_PLUNGE_LANDING_IMPACT_KEY = f"{ODETTE_PLUNGE_ACTION_KEY}.landing"

ODETTE_HIT_IMPACT_KEYS = (
    ODETTE_NORMAL_ATTACK_1_IMPACT_KEY,
    ODETTE_NORMAL_ATTACK_2_IMPACT_KEY,
    ODETTE_NORMAL_ATTACK_3A_IMPACT_KEY,
    ODETTE_NORMAL_ATTACK_3B_IMPACT_KEY,
    ODETTE_NORMAL_ATTACK_4_IMPACT_KEY,
    ODETTE_NORMAL_ATTACK_5_IMPACT_KEY,
    ODETTE_CHARGED_ATTACK_IMPACT_KEY,
    ODETTE_ELEMENTAL_SKILL_IMPACT_KEY,
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
# 元素量序列 1,0,0,0）。定义随内容单元声明；持续段命中在后续切片接入时消费。
# ---------------------------------------------------------------------------
ODETTE_SPECIAL_SKILL_ICD_SEQUENCE_KEY = "奥黛塔元素战技"
ODETTE_SPECIAL_SKILL_ICD_RESET_FRAMES = 180
ODETTE_SPECIAL_SKILL_ICD_APPLICATION_SEQUENCE = (1, 0, 0, 0)

# 奥黛塔为单手剑：下落攻击取单手剑通用资料（content/generic/plunge.py）。
ODETTE_PLUNGE_ATTACK_DATA = PLUNGE_ATTACK_DATA_BY_WEAPON_TYPE["sword"]


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
        hit_frame=23,
        impact_key=ODETTE_ELEMENTAL_SKILL_IMPACT_KEY,
        targeting=ODETTE_TARGETING_SKILL,
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
    # 柔板·破晓终奏：伤害时间轴（DoT 11/20/28f、终结 62f）随独舞倒影召唤物
    # 在后续切片接入；本切片先落动作存续、独立冷却与取消窗口。
    ODETTE_SPECIAL_ELEMENTAL_SKILL_ACTION_KEY: TimedActionSpec(
        action_key=ODETTE_SPECIAL_ELEMENTAL_SKILL_ACTION_KEY,
        duration_frames=76,
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
