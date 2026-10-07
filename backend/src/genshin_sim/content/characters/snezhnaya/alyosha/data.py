"""阿罗夏内容数据：稳定键、命中判定数据与动作帧表。

命中判定数据与帧表来自维护者提供的 V7.0 命中资料表与实测录制
（帧位来自实测资料、不作断言目标）；下落攻击的命中数据取按武器类型的通用资料
（`content/generic/plunge.py`，阿罗夏为长柄武器）。攻击标签、打击类型等游戏
数据字符串按资料保真保留中文原文；代码标识符使用官方英文名 Alyosha。
"""

from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.content.generic.plunge import PLUNGE_ATTACK_DATA_BY_WEAPON_TYPE
from genshin_sim.content.generic.timed_action import TimedActionSpec, TimedImpactPointSpec
from genshin_sim.core.actions import SearchAreaSpec, TargetingSpec
from genshin_sim.core.elements import Element
from genshin_sim.core.impacts import StrikeType
from genshin_sim.core.space import Vector3
from genshin_sim.core.systems.reaction.mechanics.electro_charged.mechanic import (
    ELECTRO_CHARGED_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.lunar_electro_charged.keys import (
    LUNAR_ELECTRO_CHARGED_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.overloaded.mechanic import (
    OVERLOADED_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.stellar_conduct.keys import (
    STELLAR_CONDUCT_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.superconduct.mechanic import (
    SUPERCONDUCT_REACTION_KEY,
)

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
ALYOSHA_ELEMENTAL_SKILL_HOLD_ACTION_KEY = "character.alyosha.elemental_skill_hold"
ALYOSHA_ELEMENTAL_BURST_ACTION_KEY = "character.alyosha.elemental_burst"
ALYOSHA_CHARGED_ATTACK_ACTION_KEY = "character.alyosha.charged_attack"
ALYOSHA_PLUNGE_ACTION_KEY = "character.alyosha.plunge"

ALYOSHA_NORMAL_ATTACK_1_IMPACT_KEY = f"{ALYOSHA_NORMAL_ATTACK_1_ACTION_KEY}.hit"
ALYOSHA_NORMAL_ATTACK_2_IMPACT_KEY = f"{ALYOSHA_NORMAL_ATTACK_2_ACTION_KEY}.hit"
ALYOSHA_NORMAL_ATTACK_3A_IMPACT_KEY = f"{ALYOSHA_NORMAL_ATTACK_3_ACTION_KEY}.hit_a"
ALYOSHA_NORMAL_ATTACK_3B_IMPACT_KEY = f"{ALYOSHA_NORMAL_ATTACK_3_ACTION_KEY}.hit_b"
ALYOSHA_NORMAL_ATTACK_4_IMPACT_KEY = f"{ALYOSHA_NORMAL_ATTACK_4_ACTION_KEY}.hit"
ALYOSHA_ELEMENTAL_SKILL_PRESS_IMPACT_KEY = f"{ALYOSHA_ELEMENTAL_SKILL_ACTION_KEY}.hit"
ALYOSHA_ELEMENTAL_SKILL_HOLD_IMPACT_KEY = f"{ALYOSHA_ELEMENTAL_SKILL_HOLD_ACTION_KEY}.hit"
ALYOSHA_ELEMENTAL_BURST_ENERGY_SPEND_IMPACT_KEY = (
    f"{ALYOSHA_ELEMENTAL_BURST_ACTION_KEY}.spend_energy"
)
# Q 施放影响点：展开为轰霆猎场创建实体请求（场域首拍/图加林首咬全部锚定
# 施放帧）。
ALYOSHA_ELEMENTAL_BURST_SUMMON_IMPACT_KEY = f"{ALYOSHA_ELEMENTAL_BURST_ACTION_KEY}.summon"
# 重击突进段命中影响点（重击链前段复用一段普攻影响点，见动作表 重击条目）。
ALYOSHA_CHARGED_ATTACK_IMPACT_KEY = f"{ALYOSHA_CHARGED_ATTACK_ACTION_KEY}.hit"
# 下落攻击两个影响点：下坠碰撞（每个下落过程一次）与坠地冲击（落地帧）。
# 二者由通用 FallPlungeAction 在位移设施事实帧当场发出（动作不预排影响帧）。
ALYOSHA_PLUNGE_COLLISION_IMPACT_KEY = f"{ALYOSHA_PLUNGE_ACTION_KEY}.collision"
ALYOSHA_PLUNGE_LANDING_IMPACT_KEY = f"{ALYOSHA_PLUNGE_ACTION_KEY}.landing"

ALYOSHA_HIT_IMPACT_KEYS = (
    ALYOSHA_NORMAL_ATTACK_1_IMPACT_KEY,
    ALYOSHA_NORMAL_ATTACK_2_IMPACT_KEY,
    ALYOSHA_NORMAL_ATTACK_3A_IMPACT_KEY,
    ALYOSHA_NORMAL_ATTACK_3B_IMPACT_KEY,
    ALYOSHA_NORMAL_ATTACK_4_IMPACT_KEY,
    ALYOSHA_ELEMENTAL_SKILL_PRESS_IMPACT_KEY,
    ALYOSHA_ELEMENTAL_SKILL_HOLD_IMPACT_KEY,
    ALYOSHA_CHARGED_ATTACK_IMPACT_KEY,
    ALYOSHA_PLUNGE_COLLISION_IMPACT_KEY,
    ALYOSHA_PLUNGE_LANDING_IMPACT_KEY,
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
ALYOSHA_DAMAGE_ELEMENT = Element.ELECTRO
ALYOSHA_MELEE_ELEMENT = Element.PHYSICAL

ALYOSHA_NORMAL_ATTACK_ICD_SEQUENCE_KEY = "默认"
ALYOSHA_NORMAL_ATTACK_ICD_TAG_KEY = "普通攻击"
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
# 索敌规格
# ---------------------------------------------------------------------------
ALYOSHA_TARGETING_NORMAL_ATTACK = TargetingSpec(
    search_area=SearchAreaSpec(shape="圆柱", radius=5.0, height=6.0),
    selection_policy_key="分数",
)
ALYOSHA_TARGETING_ELEMENTAL_SKILL = TargetingSpec(
    search_area=SearchAreaSpec(shape="圆柱", radius=8.0, height=6.0),
    selection_policy_key="分数",
)
# Q 召唤落点选敌
ALYOSHA_TARGETING_ELEMENTAL_BURST = TargetingSpec(
    search_area=SearchAreaSpec(shape="圆柱", radius=15.0, height=10.0),
    selection_policy_key="分数",
)

# ---------------------------------------------------------------------------
# 冷却能力键。冷却时长（E 15s、Q 18s）取资产倍率表「冷却时间」条目，不在
# 代码里另存常量（见 content.py 编译）。
# ---------------------------------------------------------------------------
ALYOSHA_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY = "elemental_skill"
ALYOSHA_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY = "elemental_burst"

FRAMES_PER_SECOND = 60

# 一段普攻帧位；重击链前段引用同一数据，动作表两处共用本常量。
ALYOSHA_NORMAL_ATTACK_1_DURATION_FRAMES = 74
ALYOSHA_NORMAL_ATTACK_1_HIT_FRAME_OFFSET = 21


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

# 长按伤害无独立索敌：命中区域即伤害 AOE，以施放者为锚（工厂经
# anchor_entity_id 交给伤害展开器解析），朝向 = 角色朝向（攻击方向）；高度
# 与偏移 Y 分量不参与 X/Z 查询。按住期间范围随时间增长（增长曲线无资料），
# 仿真按最大范围结算。
ALYOSHA_ELEMENTAL_SKILL_HOLD_AOE_RADIUS = 15.0
ALYOSHA_ELEMENTAL_SKILL_HOLD_AOE_ARC_DEGREES = 150.0
ALYOSHA_ELEMENTAL_SKILL_HOLD_AOE_OFFSET = Vector3(0.0, -3.0, 0.0)

ALYOSHA_ELEMENTAL_BURST_MAIN_ATTACK_TAG = "元素爆发"
ALYOSHA_ELEMENTAL_BURST_RANGE_TYPE = "远程"

ALYOSHA_CHARGED_ATTACK_MAIN_ATTACK_TAG = "重击"
ALYOSHA_CHARGED_ATTACK_STRIKE_TYPE = StrikeType.THRUST
ALYOSHA_CHARGED_ATTACK_RANGE_TYPE = "近战"
ALYOSHA_CHARGED_ATTACK_AOE_SHAPE = "球"
ALYOSHA_CHARGED_ATTACK_AOE_RADIUS = 0.8
ALYOSHA_CHARGED_ICD_SEQUENCE_KEY = "突进攻击"
ALYOSHA_CHARGED_ICD_TAG_KEY = "重击"

ALYOSHA_PLUNGE_ATTACK_DATA = PLUNGE_ATTACK_DATA_BY_WEAPON_TYPE["polearm"]

# ---------------------------------------------------------------------------
# E 长按与重击的输入语义帧位。
#
# - E 长按：按住阶段（瞄准）无仿真效果，持续按住越过上限由解释器自动进入
#   释放阶段；释放阶段时长为实测均值（提前释放在释放时刻进入同一段固定
#   释放动画）。
# - 重击：记录段即重击时序，在前拼接第一段普攻构成完整重击链。
# - 点按/长按输入分界：游戏内实际判定阈值未实测，本值仅作仿真输入语义分界
#   （按住达到该帧数按长按/重击解释），非游戏行为断言，游戏内阈值实测后
#   修正。
# ---------------------------------------------------------------------------
ALYOSHA_ELEMENTAL_SKILL_HOLD_MAX_FRAMES = 250
ALYOSHA_ELEMENTAL_SKILL_HOLD_RELEASE_FRAMES = 146
ALYOSHA_ELEMENTAL_SKILL_HOLD_HIT_FRAME_OFFSET = 26
ALYOSHA_HOLD_INPUT_MIN_FRAMES = 30
ALYOSHA_CHARGED_THRUST_SEGMENT_FRAMES = 55
ALYOSHA_CHARGED_THRUST_HIT_FRAME_OFFSET = 28

# ---------------------------------------------------------------------------
# 动作帧表。
#
# - duration 为完整动画时长，hit_frame 为命中帧位，transitions 为实测衔接
#   打断点（E 点按→Q 为实测取消衔接点，其余普攻衔接为段间打断点）。
# - 未实测的衔接以 duration+1 兜底（动作完整播放后才可衔接），待补充实测
#   后修正。
# - E 长按与重击的帧位口径见「E 长按与重击的输入语义帧位」常量段注释。
# ---------------------------------------------------------------------------
ALYOSHA_ACTION_TABLE: dict[str, TimedActionSpec] = {
    ALYOSHA_NORMAL_ATTACK_1_ACTION_KEY: TimedActionSpec(
        action_key=ALYOSHA_NORMAL_ATTACK_1_ACTION_KEY,
        duration_frames=ALYOSHA_NORMAL_ATTACK_1_DURATION_FRAMES,
        hit_frame=ALYOSHA_NORMAL_ATTACK_1_HIT_FRAME_OFFSET,
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
    # E 长按（按住阶段 → 释放阶段）：动作从释放时刻起手，只承载释放阶段；
    # 按住阶段无仿真效果，由解释器在按住上限自动起手本动作。无独立索敌——
    # 命中目标由 150° 扇区伤害 AOE 以施放者为锚展开。
    ALYOSHA_ELEMENTAL_SKILL_HOLD_ACTION_KEY: TimedActionSpec(
        action_key=ALYOSHA_ELEMENTAL_SKILL_HOLD_ACTION_KEY,
        duration_frames=ALYOSHA_ELEMENTAL_SKILL_HOLD_RELEASE_FRAMES,
        hit_frame=ALYOSHA_ELEMENTAL_SKILL_HOLD_HIT_FRAME_OFFSET,
        impact_key=ALYOSHA_ELEMENTAL_SKILL_HOLD_IMPACT_KEY,
        cooldown_start_frame=1,
        cooldown_ability_key=ALYOSHA_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
        transitions={
            NORMAL_ATTACK_INPUT: ALYOSHA_ELEMENTAL_SKILL_HOLD_RELEASE_FRAMES + 1,
            ELEMENTAL_SKILL_INPUT: ALYOSHA_ELEMENTAL_SKILL_HOLD_RELEASE_FRAMES + 1,
            ELEMENTAL_BURST_INPUT: ALYOSHA_ELEMENTAL_SKILL_HOLD_RELEASE_FRAMES + 1,
        },
    ),
    # 重击（前置一段普攻 + 突进段）：衔接帧未实测，按 duration+1 兜底。
    ALYOSHA_CHARGED_ATTACK_ACTION_KEY: TimedActionSpec(
        action_key=ALYOSHA_CHARGED_ATTACK_ACTION_KEY,
        duration_frames=(
            ALYOSHA_NORMAL_ATTACK_1_DURATION_FRAMES + ALYOSHA_CHARGED_THRUST_SEGMENT_FRAMES
        ),
        impact_points=(
            TimedImpactPointSpec(
                impact_key=ALYOSHA_NORMAL_ATTACK_1_IMPACT_KEY,
                frame=ALYOSHA_NORMAL_ATTACK_1_HIT_FRAME_OFFSET,
                targeting=ALYOSHA_TARGETING_NORMAL_ATTACK,
            ),
            TimedImpactPointSpec(
                impact_key=ALYOSHA_CHARGED_ATTACK_IMPACT_KEY,
                frame=(
                    ALYOSHA_NORMAL_ATTACK_1_DURATION_FRAMES
                    + ALYOSHA_CHARGED_THRUST_HIT_FRAME_OFFSET
                ),
                targeting=ALYOSHA_TARGETING_NORMAL_ATTACK,
            ),
        ),
        transitions={
            NORMAL_ATTACK_INPUT: (
                ALYOSHA_NORMAL_ATTACK_1_DURATION_FRAMES + ALYOSHA_CHARGED_THRUST_SEGMENT_FRAMES + 1
            ),
            ELEMENTAL_SKILL_INPUT: (
                ALYOSHA_NORMAL_ATTACK_1_DURATION_FRAMES + ALYOSHA_CHARGED_THRUST_SEGMENT_FRAMES + 1
            ),
            ELEMENTAL_BURST_INPUT: (
                ALYOSHA_NORMAL_ATTACK_1_DURATION_FRAMES + ALYOSHA_CHARGED_THRUST_SEGMENT_FRAMES + 1
            ),
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
            TimedImpactPointSpec(
                impact_key=ALYOSHA_ELEMENTAL_BURST_SUMMON_IMPACT_KEY,
                frame=1,
                targeting=ALYOSHA_TARGETING_ELEMENTAL_BURST,
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
    # 下落攻击：不使用固定时间线，也不由动作写位移（`docs/架构/动作系统设计.md`
    # §7.4）——动作时长由位移设施的碰撞/落地事实决定，因此本条目只占位声明
    # 动作键与衔接表；`create_alyosha_actions` 会把它替换为通用
    # `FallPlungeAction`。落地后高度归零，解释器据此把连段状态重置（见
    # actions.py），故 transitions 留空不影响后续输入。
    ALYOSHA_PLUNGE_ACTION_KEY: TimedActionSpec(
        action_key=ALYOSHA_PLUNGE_ACTION_KEY,
        duration_frames=1,
        transitions={},
    ),
}

ALYOSHA_NORMAL_ATTACK_ACTION_KEYS = (
    ALYOSHA_NORMAL_ATTACK_1_ACTION_KEY,
    ALYOSHA_NORMAL_ATTACK_2_ACTION_KEY,
    ALYOSHA_NORMAL_ATTACK_3_ACTION_KEY,
    ALYOSHA_NORMAL_ATTACK_4_ACTION_KEY,
)

# ---------------------------------------------------------------------------
# 弋猎印记 / 猎者之准（Buff 定义键与词条键；定义在 buffs.py 构造）。
# 印记持续时间与猎者之准攻击力/持续时间取资产倍率表条目（见 content.py 编译），
# 不在代码里另存常量。
# ---------------------------------------------------------------------------
ALYOSHA_HUNTERS_MARK_BUFF_DEFINITION_KEY = "buff.alyosha.hunters_mark"
ALYOSHA_HUNTERS_MARK_MECHANIC_KEY = "character.alyosha.hunters_mark"
ALYOSHA_HUNTERS_MARK_CONFLICT_KEY = "buff_conflict.alyosha.hunters_mark"

ALYOSHA_HUNTERS_PRECISION_BUFF_DEFINITION_KEY = "buff.alyosha.hunters_precision"
ALYOSHA_HUNTERS_PRECISION_MECHANIC_KEY = "character.alyosha.hunters_precision"
ALYOSHA_HUNTERS_PRECISION_CONFLICT_KEY = "buff_conflict.alyosha.hunters_precision"
ALYOSHA_HUNTERS_PRECISION_ATK_TERM_KEY = "alyosha.hunters_precision.atk_bonus"

# C6 叠满伴生的元素精通 Buff（叠满时 +100 精通，随猎者之准同帧刷新/到期）。
ALYOSHA_HUNTERS_PRECISION_MASTERY_BUFF_DEFINITION_KEY = "buff.alyosha.hunters_precision_mastery"
ALYOSHA_HUNTERS_PRECISION_MASTERY_MECHANIC_KEY = "character.alyosha.hunters_precision_mastery"
ALYOSHA_HUNTERS_PRECISION_MASTERY_CONFLICT_KEY = "buff_conflict.alyosha.hunters_precision_mastery"
ALYOSHA_HUNTERS_PRECISION_MASTERY_TERM_KEY = "alyosha.hunters_precision.mastery_bonus"

# ---------------------------------------------------------------------------
# Q 轰霆猎场创建实体（单一实体、双攻击通道：轰霆猎场 AoE tick + 图加林撕咬）。
# 首拍/首咬/周期帧位来自实测录制，全部锚定施放帧；「出现/完全形成」帧位仅
# 作演出参考，不参与时序。召唤落点 = 召唤索敌选中的最近目标位置（见
# ALYOSHA_TARGETING_ELEMENTAL_BURST），无目标时回退角色原位。
# ---------------------------------------------------------------------------
ALYOSHA_FULGURITE_OBJECT_KEY = "alyosha.fulgurite_hunting_field"
ALYOSHA_FIELD_TICK_SCHEDULE_KEY = "field_tick"
ALYOSHA_TUGARIN_BITE_SCHEDULE_KEY = "tugarin_bite"
ALYOSHA_FIELD_FIRST_TICK_FRAME_OFFSET = 81
ALYOSHA_TUGARIN_FIRST_BITE_FRAME_OFFSET = 127
ALYOSHA_FIELD_TICK_PERIOD_FRAMES = 120
ALYOSHA_TUGARIN_BITE_PERIOD_FRAMES = 120

ALYOSHA_BURST_FIELD_TICK_IMPACT_KEY = f"{ALYOSHA_ELEMENTAL_BURST_ACTION_KEY}.field_tick"
ALYOSHA_BURST_TUGARIN_BITE_IMPACT_KEY = f"{ALYOSHA_ELEMENTAL_BURST_ACTION_KEY}.tugarin_bite"

# AOE 高度分量不参与 X/Z 查询。
ALYOSHA_FIELD_TICK_AOE_RADIUS = 6.0
ALYOSHA_FIELD_TICK_AOE_OFFSET = Vector3(0.0, -0.5, 0.0)
ALYOSHA_TUGARIN_BITE_AOE_RADIUS = 1.0
ALYOSHA_TUGARIN_BITE_AOE_OFFSET = Vector3(0.0, -0.5, 0.0)

# 图加林索敌：中心是轰霆猎场实体、范围远大于伤害范围；范围内有弋猎印记取
# 其中最近者，否则全范围最近者。
ALYOSHA_TUGARIN_SEARCH_RADIUS = 15.0

ALYOSHA_BURST_ICD_TAG_KEY = "元素爆发"

# ---------------------------------------------------------------------------
# P4/C4（图加林攻击动作触发的周期回血）。回复比例取资产效果行 components
# （见 content.py 编译），此处只定承载键。
# ---------------------------------------------------------------------------
ALYOSHA_P4_HEAL_COMPONENT_KEY = "alyosha.passive.p4.heal"
ALYOSHA_C4_HEAL_COMPONENT_KEY = "alyosha.constellation.c4.heal"

# ---------------------------------------------------------------------------
# C1 寒谷轰雷：雷元素相关反应触发判定。reaction_key 恒涉雷的集合 +
# direction_key 携带雷方向（雷扩散/雷结晶/原激化等按方向分流的反应族）。
# ---------------------------------------------------------------------------
ALYOSHA_C1_ELECTRO_REACTION_KEYS = frozenset(
    {
        ELECTRO_CHARGED_REACTION_KEY,
        OVERLOADED_REACTION_KEY,
        SUPERCONDUCT_REACTION_KEY,
        STELLAR_CONDUCT_REACTION_KEY,
        LUNAR_ELECTRO_CHARGED_REACTION_KEY,
    }
)
ALYOSHA_C1_ELECTRO_DIRECTION_MARKER = "electro"

# 队伍作用域稳定 id（单人队伍，与 stellar_conduct/dendro_core 等域内常量同值；
# ACTIVE_CHARACTER 主体记录挂在该作用域上，前台门控由属性投影语义承担）。
ALYOSHA_TEAM_SCOPE = "player_team"

# ---------------------------------------------------------------------------
# 产球：E 点按/长按伤害命中触发；图加林/轰霆猎场不产微粒。飞行帧沿用通用
# 占位（奥黛塔/桑多涅同款）；触发匹配按伤害结果 request_id 内嵌的
# impact_key 识别。
# ---------------------------------------------------------------------------
ALYOSHA_PARTICLE_TRIGGER_IMPACT_KEYS = (
    ALYOSHA_ELEMENTAL_SKILL_PRESS_IMPACT_KEY,
    ALYOSHA_ELEMENTAL_SKILL_HOLD_IMPACT_KEY,
)
ALYOSHA_PARTICLE_SPAWN_IMPACT_KEY = "character.alyosha.particle.spawn"
ALYOSHA_PARTICLE_ELEMENT = Element.ELECTRO
ALYOSHA_PARTICLE_COUNT = 5
ALYOSHA_PARTICLE_COOLDOWN_FRAMES = 30
ALYOSHA_PARTICLE_TRAVEL_FRAMES = 30
