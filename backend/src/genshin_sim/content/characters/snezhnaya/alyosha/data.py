"""阿罗夏内容数据：稳定键、命中判定数据与动作帧表。

命中判定数据与帧表来自维护者提供的 V7.0 命中资料表与 2026-10-06 实测录制
（帧位口径见 `docs/工程/阿罗夏接入规划.md` §3/§3.1：数值来自实测资料、不作
断言目标）。攻击标签、打击类型等游戏数据字符串按资料保真保留中文原文；
代码标识符使用官方英文名 Alyosha。
"""

from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.content.generic.timed_action import TimedActionSpec, TimedImpactPointSpec
from genshin_sim.core.actions import SearchAreaSpec, TargetingSpec
from genshin_sim.core.elements import AuraAmount, Element
from genshin_sim.core.impacts import StrikeType
from genshin_sim.core.space import Vector3
from genshin_sim.core.systems.aura import AuraStrength

ALYOSHA_CHARACTER_HANDLER_KEY = "character.alyosha"
ALYOSHA_CONTENT_VERSION = "dev-skeleton"

# ---------------------------------------------------------------------------
# 被动与命座。效果行 handler 键对齐 sandrone 命名。
# ---------------------------------------------------------------------------
ALYOSHA_PASSIVE_P4_HANDLER_KEY = "character.alyosha.passive.p4"
ALYOSHA_PASSIVE_P5_HANDLER_KEY = "character.alyosha.passive.p5"
ALYOSHA_PASSIVE_P6_HANDLER_KEY = "character.alyosha.passive.p6"
# P8 树梢察伺（探索天赋，小地图特产探测）无仿真效果，bootstrap 注册空效果
# handler（键仍被装配引用）。
ALYOSHA_PASSIVE_P8_HANDLER_KEY = "character.alyosha.passive.p8"

ALYOSHA_CONSTELLATION_C1_HANDLER_KEY = "character.alyosha.constellation.c1"
ALYOSHA_CONSTELLATION_C2_HANDLER_KEY = "character.alyosha.constellation.c2"
ALYOSHA_CONSTELLATION_C3_HANDLER_KEY = "character.alyosha.constellation.c3"
ALYOSHA_CONSTELLATION_C4_HANDLER_KEY = "character.alyosha.constellation.c4"
ALYOSHA_CONSTELLATION_C5_HANDLER_KEY = "character.alyosha.constellation.c5"
ALYOSHA_CONSTELLATION_C6_HANDLER_KEY = "character.alyosha.constellation.c6"

# ---------------------------------------------------------------------------
# 动作与影响点键。
# ---------------------------------------------------------------------------
ALYOSHA_NORMAL_ATTACK_1_ACTION_KEY = "character.alyosha.normal_attack.1"
ALYOSHA_NORMAL_ATTACK_2_ACTION_KEY = "character.alyosha.normal_attack.2"
ALYOSHA_NORMAL_ATTACK_3_ACTION_KEY = "character.alyosha.normal_attack.3"
ALYOSHA_NORMAL_ATTACK_4_ACTION_KEY = "character.alyosha.normal_attack.4"
ALYOSHA_ELEMENTAL_SKILL_ACTION_KEY = "character.alyosha.elemental_skill"
ALYOSHA_ELEMENTAL_BURST_ACTION_KEY = "character.alyosha.elemental_burst"

ALYOSHA_NORMAL_ATTACK_1_IMPACT_KEY = f"{ALYOSHA_NORMAL_ATTACK_1_ACTION_KEY}.hit"
ALYOSHA_NORMAL_ATTACK_2_IMPACT_KEY = f"{ALYOSHA_NORMAL_ATTACK_2_ACTION_KEY}.hit"
# 第三段双判定（资料表 普通攻击3A/3B 两条）：A 段切割、B 段突刺，形状与偏移
# 各自独立，倍率取「三段伤害」条目的两个分量。
ALYOSHA_NORMAL_ATTACK_3A_IMPACT_KEY = f"{ALYOSHA_NORMAL_ATTACK_3_ACTION_KEY}.hit_a"
ALYOSHA_NORMAL_ATTACK_3B_IMPACT_KEY = f"{ALYOSHA_NORMAL_ATTACK_3_ACTION_KEY}.hit_b"
ALYOSHA_NORMAL_ATTACK_4_IMPACT_KEY = f"{ALYOSHA_NORMAL_ATTACK_4_ACTION_KEY}.hit"
ALYOSHA_ELEMENTAL_SKILL_PRESS_IMPACT_KEY = f"{ALYOSHA_ELEMENTAL_SKILL_ACTION_KEY}.hit"
ALYOSHA_ELEMENTAL_BURST_ENERGY_SPEND_IMPACT_KEY = (
    f"{ALYOSHA_ELEMENTAL_BURST_ACTION_KEY}.spend_energy"
)

ALYOSHA_HIT_IMPACT_KEYS = (
    ALYOSHA_NORMAL_ATTACK_1_IMPACT_KEY,
    ALYOSHA_NORMAL_ATTACK_2_IMPACT_KEY,
    ALYOSHA_NORMAL_ATTACK_3A_IMPACT_KEY,
    ALYOSHA_NORMAL_ATTACK_3B_IMPACT_KEY,
    ALYOSHA_NORMAL_ATTACK_4_IMPACT_KEY,
    ALYOSHA_ELEMENTAL_SKILL_PRESS_IMPACT_KEY,
)

NORMAL_ATTACK_INPUT = "normal_attack"
ELEMENTAL_SKILL_INPUT = "elemental_skill"
ELEMENTAL_BURST_INPUT = "elemental_burst"

INPUT_KIND_BY_KEY = {
    "mouse.left": NORMAL_ATTACK_INPUT,
    "keyboard.e": ELEMENTAL_SKILL_INPUT,
    "keyboard.q": ELEMENTAL_BURST_INPUT,
}

# ---------------------------------------------------------------------------
# 元素与 ICD。
# ---------------------------------------------------------------------------
# E/Q 为雷元素伤害；普攻未获元素转化时为物理（物理是伤害侧合法元素，不参与
# 元素交互、不形成附着），命中判定数据普攻行的「元素量 1」仅在该攻击具元素
# 时生效（桑多涅同款边界）。
ALYOSHA_DAMAGE_ELEMENT = Element.ELECTRO
ALYOSHA_DAMAGE_ELEMENTAL_STRENGTH = AuraStrength.WEAK
ALYOSHA_DAMAGE_ELEMENTAL_AMOUNT = AuraAmount.one()
ALYOSHA_MELEE_ELEMENT = Element.PHYSICAL

# 普攻衰减：默认序列、标签「普通攻击」。
ALYOSHA_NORMAL_ATTACK_ICD_SEQUENCE_KEY = "默认"
ALYOSHA_NORMAL_ATTACK_ICD_TAG_KEY = "普通攻击"
# E 点按/长按无 ICD（单次判定，无实质约束）。
# Q 专属衰减序列「阿罗夏元素爆发」（资料：重置 1.6s、序列 [1,0]），轰霆猎场
# 与图加林两个伤害源共享同一附着序列（2 hits / 1.6s）。
ALYOSHA_BURST_ICD_SEQUENCE_KEY = "阿罗夏元素爆发"
ALYOSHA_BURST_ICD_RESET_FRAMES = 96

# NA4 与 E 的附加攻击标签（资料表：弋猎印记的施加与锁定交互，原始数据串）。
ALYOSHA_MARK_LOCK_ADDITIONAL_TAG = "阿罗夏锁定印记"
ALYOSHA_MARK_APPLY_ADDITIONAL_TAG = "阿罗夏施加印记"
ALYOSHA_MARK_ADDITIONAL_TAGS = (
    ALYOSHA_MARK_LOCK_ADDITIONAL_TAG,
    ALYOSHA_MARK_APPLY_ADDITIONAL_TAG,
)

# ---------------------------------------------------------------------------
# 索敌规格（命中判定数据：普攻圆柱 5.0,6.0 分数；E 点按圆柱 8.0,6.0 分数）。
# ---------------------------------------------------------------------------
ALYOSHA_TARGETING_NORMAL_ATTACK = TargetingSpec(
    search_area=SearchAreaSpec(shape="圆柱", radius=5.0, height=6.0),
    selection_policy_key="分数",
)
ALYOSHA_TARGETING_ELEMENTAL_SKILL = TargetingSpec(
    search_area=SearchAreaSpec(shape="圆柱", radius=8.0, height=6.0),
    selection_policy_key="分数",
)

# ---------------------------------------------------------------------------
# 冷却能力键。冷却时长（E 15s、Q 18s）取资产倍率表「冷却时间」条目，不在
# 代码里另存常量（见 content.py 编译）。
# ---------------------------------------------------------------------------
ALYOSHA_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY = "elemental_skill"
ALYOSHA_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY = "elemental_burst"

FRAMES_PER_SECOND = 60


@dataclass(frozen=True, slots=True)
class AlyoshaNormalAttackDamageData:
    """单段普攻的伤害数据（主攻击标签、打击类型、AOE 与偏移随段变化）。

    形状/偏移保留资料原始三元组：圆柱区域取（半径,高）前两分量；攻击盒按
    （长,宽,高）接入，第三分量（高度）由 X/Z 模型忽略；偏移投影时随攻击
    方向旋转（Y 轴分量不参与查询）。
    """

    main_attack_tag: str
    strike_type: StrikeType
    range_type: str
    aoe_shape: str
    aoe_radius: float
    aoe_length: float
    aoe_width: float
    aoe_offset: Vector3
    additional_attack_tags: tuple[str, ...] = ()


ALYOSHA_NORMAL_ATTACK_DAMAGE_DATA = (
    # 普通攻击1：圆柱 2.0,1.5 / 0,0,0.6，切割，近战。
    AlyoshaNormalAttackDamageData(
        main_attack_tag="普通攻击1",
        strike_type=StrikeType.SLASH,
        range_type="近战",
        aoe_shape="圆柱",
        aoe_radius=2.0,
        aoe_length=0.0,
        aoe_width=0.0,
        aoe_offset=Vector3(0.0, 0.0, 0.6),
    ),
    # 普通攻击2：攻击盒 2.0,2.0,4.0 / 0.2,1.0,0，突刺，近战。
    AlyoshaNormalAttackDamageData(
        main_attack_tag="普通攻击2",
        strike_type=StrikeType.THRUST,
        range_type="近战",
        aoe_shape="攻击盒",
        aoe_radius=0.0,
        aoe_length=2.0,
        aoe_width=2.0,
        aoe_offset=Vector3(0.2, 1.0, 0.0),
    ),
    # 普通攻击3A：圆柱 1.8,2.0 / 0,0,0.8，切割，近战。
    AlyoshaNormalAttackDamageData(
        main_attack_tag="普通攻击3",
        strike_type=StrikeType.SLASH,
        range_type="近战",
        aoe_shape="圆柱",
        aoe_radius=1.8,
        aoe_length=0.0,
        aoe_width=0.0,
        aoe_offset=Vector3(0.0, 0.0, 0.8),
    ),
    # 普通攻击3B：攻击盒 2.0,2.0,4.0 / 0,1.0,-0.5，突刺，近战。
    AlyoshaNormalAttackDamageData(
        main_attack_tag="普通攻击3",
        strike_type=StrikeType.THRUST,
        range_type="近战",
        aoe_shape="攻击盒",
        aoe_radius=0.0,
        aoe_length=2.0,
        aoe_width=2.0,
        aoe_offset=Vector3(0.0, 1.0, -0.5),
    ),
    # 普通攻击4：攻击盒 2.4,2.0,6.0 / 0,1.0,0.5，突刺，远程；附加弋猎印记
    # 交互标签（官方文本：最后一击命中的敌人施加弋猎印记）。
    AlyoshaNormalAttackDamageData(
        main_attack_tag="普通攻击4",
        strike_type=StrikeType.THRUST,
        range_type="远程",
        aoe_shape="攻击盒",
        aoe_radius=0.0,
        aoe_length=2.4,
        aoe_width=2.0,
        aoe_offset=Vector3(0.0, 1.0, 0.5),
        additional_attack_tags=ALYOSHA_MARK_ADDITIONAL_TAGS,
    ),
)

ALYOSHA_ELEMENTAL_SKILL_MAIN_ATTACK_TAG = "元素战技"
ALYOSHA_ELEMENTAL_SKILL_STRIKE_TYPE = StrikeType.THRUST
ALYOSHA_ELEMENTAL_SKILL_RANGE_TYPE = "远程"
ALYOSHA_ELEMENTAL_SKILL_AOE_SHAPE = "攻击盒"
ALYOSHA_ELEMENTAL_SKILL_AOE_LENGTH = 2.5
ALYOSHA_ELEMENTAL_SKILL_AOE_WIDTH = 3.5
ALYOSHA_ELEMENTAL_SKILL_AOE_OFFSET = Vector3(0.0, 1.5, 0.0)

ALYOSHA_ELEMENTAL_BURST_MAIN_ATTACK_TAG = "元素爆发"
ALYOSHA_ELEMENTAL_BURST_RANGE_TYPE = "远程"

# ---------------------------------------------------------------------------
# 动作帧表（实测录制，帧制 60 帧/秒；口径见规划文档 §3.1）。
#
# - duration：完整动画时长（录制二：N1 74 / N2 82 / N3 161 / N4 226；E 点按
#   152；Q 148，两次独立实测一致）。
# - hit_frame：命中帧位（录制五：N1 +21 / N2 +20 / N3 +24 与 +32（双判定，
#   间隔 8 帧）/ N4 +23；E 点按 +43）。
# - transitions：普攻衔接取录制一第一轮打断点（N1→N2 40 / N2→N3 35 /
#   N3→N4 72 / N4→N1 60，连续攻击下段间实测仅隔 1 帧）；E→Q 取实测打断点 55
#   （录制四/六，点按 E 命中后可被 Q 取消）；未实测的衔接以 duration+1 兜底
#   （动作完整播放后才可衔接），待补充实测后修正。
# ---------------------------------------------------------------------------
ALYOSHA_ACTION_TABLE: dict[str, TimedActionSpec] = {
    ALYOSHA_NORMAL_ATTACK_1_ACTION_KEY: TimedActionSpec(
        action_key=ALYOSHA_NORMAL_ATTACK_1_ACTION_KEY,
        duration_frames=74,
        hit_frame=21,
        impact_key=ALYOSHA_NORMAL_ATTACK_1_IMPACT_KEY,
        targeting=ALYOSHA_TARGETING_NORMAL_ATTACK,
        transitions={
            NORMAL_ATTACK_INPUT: 40,
            ELEMENTAL_SKILL_INPUT: 75,
            ELEMENTAL_BURST_INPUT: 75,
        },
    ),
    ALYOSHA_NORMAL_ATTACK_2_ACTION_KEY: TimedActionSpec(
        action_key=ALYOSHA_NORMAL_ATTACK_2_ACTION_KEY,
        duration_frames=82,
        hit_frame=20,
        impact_key=ALYOSHA_NORMAL_ATTACK_2_IMPACT_KEY,
        targeting=ALYOSHA_TARGETING_NORMAL_ATTACK,
        transitions={
            NORMAL_ATTACK_INPUT: 35,
            ELEMENTAL_SKILL_INPUT: 83,
            ELEMENTAL_BURST_INPUT: 83,
        },
    ),
    ALYOSHA_NORMAL_ATTACK_3_ACTION_KEY: TimedActionSpec(
        action_key=ALYOSHA_NORMAL_ATTACK_3_ACTION_KEY,
        duration_frames=161,
        impact_points=(
            TimedImpactPointSpec(
                impact_key=ALYOSHA_NORMAL_ATTACK_3A_IMPACT_KEY,
                frame=24,
                targeting=ALYOSHA_TARGETING_NORMAL_ATTACK,
            ),
            TimedImpactPointSpec(
                impact_key=ALYOSHA_NORMAL_ATTACK_3B_IMPACT_KEY,
                frame=32,
                targeting=ALYOSHA_TARGETING_NORMAL_ATTACK,
            ),
        ),
        transitions={
            NORMAL_ATTACK_INPUT: 72,
            ELEMENTAL_SKILL_INPUT: 162,
            ELEMENTAL_BURST_INPUT: 162,
        },
    ),
    ALYOSHA_NORMAL_ATTACK_4_ACTION_KEY: TimedActionSpec(
        action_key=ALYOSHA_NORMAL_ATTACK_4_ACTION_KEY,
        duration_frames=226,
        hit_frame=23,
        impact_key=ALYOSHA_NORMAL_ATTACK_4_IMPACT_KEY,
        targeting=ALYOSHA_TARGETING_NORMAL_ATTACK,
        transitions={
            NORMAL_ATTACK_INPUT: 60,
            ELEMENTAL_SKILL_INPUT: 227,
            ELEMENTAL_BURST_INPUT: 227,
        },
    ),
    ALYOSHA_ELEMENTAL_SKILL_ACTION_KEY: TimedActionSpec(
        action_key=ALYOSHA_ELEMENTAL_SKILL_ACTION_KEY,
        duration_frames=152,
        hit_frame=43,
        impact_key=ALYOSHA_ELEMENTAL_SKILL_PRESS_IMPACT_KEY,
        targeting=ALYOSHA_TARGETING_ELEMENTAL_SKILL,
        cooldown_start_frame=1,
        cooldown_ability_key=ALYOSHA_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
        transitions={
            NORMAL_ATTACK_INPUT: 153,
            ELEMENTAL_SKILL_INPUT: 153,
            ELEMENTAL_BURST_INPUT: 55,
        },
    ),
    ALYOSHA_ELEMENTAL_BURST_ACTION_KEY: TimedActionSpec(
        action_key=ALYOSHA_ELEMENTAL_BURST_ACTION_KEY,
        duration_frames=148,
        impact_points=(
            TimedImpactPointSpec(
                impact_key=ALYOSHA_ELEMENTAL_BURST_ENERGY_SPEND_IMPACT_KEY,
                frame=1,
            ),
        ),
        cooldown_start_frame=1,
        cooldown_ability_key=ALYOSHA_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY,
        transitions={
            NORMAL_ATTACK_INPUT: 149,
            ELEMENTAL_SKILL_INPUT: 149,
            ELEMENTAL_BURST_INPUT: 149,
        },
    ),
}

ALYOSHA_NORMAL_ATTACK_ACTION_KEYS = (
    ALYOSHA_NORMAL_ATTACK_1_ACTION_KEY,
    ALYOSHA_NORMAL_ATTACK_2_ACTION_KEY,
    ALYOSHA_NORMAL_ATTACK_3_ACTION_KEY,
    ALYOSHA_NORMAL_ATTACK_4_ACTION_KEY,
)
