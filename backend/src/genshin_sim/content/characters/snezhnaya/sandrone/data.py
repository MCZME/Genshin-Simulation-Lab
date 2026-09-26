"""桑多涅内容数据：稳定键、动作数据表与伤害数据。

数据与解释逻辑分离：``actions.py`` 只保留解释器与动作编译，``content.py``
只负责内容单元编译。本文件统一承载角色身份键（handler/action/impact）、
输入映射、帧表与动作表、伤害标签与 AOE 数据；普攻倍率仍来自资产库倍率表，
不在本文件维护。

帧表来源：维护者 30fps 视频实测换算（60 帧制，见临时规划文档 3.9.2）——
普攻一段完整 130F/衔接切入 59F/命中均值 +44F，二段 59F/+24F，三段 159F/+50F；
元素战技棱晶弹 +16F/+32F；元素爆发轰炸 +182/+198/+214（16F 等间隔）、
光束 +252F、结束 +306F。重击（按住持续）与法洁欧在后续切片接入。
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

SANDRONE_CHARACTER_HANDLER_KEY = "character.sandrone"
SANDRONE_ASSET_KEY = "character:10000133"
SANDRONE_CONTENT_VERSION = "slice-1-skeleton"

# 桑多涅为双手剑：下落攻击取双手剑通用资料（content/generic/plunge.py）。
SANDRONE_PLUNGE_ATTACK_DATA = PLUNGE_ATTACK_DATA_BY_WEAPON_TYPE["claymore"]

SANDRONE_NORMAL_ATTACK_1_ACTION_KEY = "character.sandrone.normal_attack.1"
SANDRONE_NORMAL_ATTACK_2_ACTION_KEY = "character.sandrone.normal_attack.2"
SANDRONE_NORMAL_ATTACK_3_ACTION_KEY = "character.sandrone.normal_attack.3"
SANDRONE_ELEMENTAL_SKILL_ACTION_KEY = "character.sandrone.elemental_skill"
SANDRONE_ELEMENTAL_BURST_ACTION_KEY = "character.sandrone.elemental_burst"
SANDRONE_JUMP_ACTION_KEY = "character.sandrone.jump"
SANDRONE_PLUNGE_ACTION_KEY = "character.sandrone.plunge"

SANDRONE_NORMAL_ATTACK_1_IMPACT_KEY = f"{SANDRONE_NORMAL_ATTACK_1_ACTION_KEY}.hit"
SANDRONE_NORMAL_ATTACK_2_IMPACT_KEY = f"{SANDRONE_NORMAL_ATTACK_2_ACTION_KEY}.hit"
SANDRONE_NORMAL_ATTACK_3_IMPACT_KEY = f"{SANDRONE_NORMAL_ATTACK_3_ACTION_KEY}.hit"
SANDRONE_ELEMENTAL_SKILL_PRISM_1_IMPACT_KEY = f"{SANDRONE_ELEMENTAL_SKILL_ACTION_KEY}.prism_1"
SANDRONE_ELEMENTAL_SKILL_PRISM_2_IMPACT_KEY = f"{SANDRONE_ELEMENTAL_SKILL_ACTION_KEY}.prism_2"
SANDRONE_ELEMENTAL_BURST_ENERGY_SPEND_IMPACT_KEY = (
    f"{SANDRONE_ELEMENTAL_BURST_ACTION_KEY}.spend_energy"
)
SANDRONE_ELEMENTAL_BURST_BOMBARDMENT_1_IMPACT_KEY = (
    f"{SANDRONE_ELEMENTAL_BURST_ACTION_KEY}.bombardment_1"
)
SANDRONE_ELEMENTAL_BURST_BOMBARDMENT_2_IMPACT_KEY = (
    f"{SANDRONE_ELEMENTAL_BURST_ACTION_KEY}.bombardment_2"
)
SANDRONE_ELEMENTAL_BURST_BOMBARDMENT_3_IMPACT_KEY = (
    f"{SANDRONE_ELEMENTAL_BURST_ACTION_KEY}.bombardment_3"
)
SANDRONE_ELEMENTAL_BURST_BEAM_IMPACT_KEY = f"{SANDRONE_ELEMENTAL_BURST_ACTION_KEY}.beam"
SANDRONE_PLUNGE_COLLISION_IMPACT_KEY = f"{SANDRONE_PLUNGE_ACTION_KEY}.collision"
SANDRONE_PLUNGE_LANDING_IMPACT_KEY = f"{SANDRONE_PLUNGE_ACTION_KEY}.landing"

SANDRONE_HIT_IMPACT_KEYS = (
    SANDRONE_NORMAL_ATTACK_1_IMPACT_KEY,
    SANDRONE_NORMAL_ATTACK_2_IMPACT_KEY,
    SANDRONE_NORMAL_ATTACK_3_IMPACT_KEY,
    SANDRONE_ELEMENTAL_SKILL_PRISM_1_IMPACT_KEY,
    SANDRONE_ELEMENTAL_SKILL_PRISM_2_IMPACT_KEY,
    SANDRONE_ELEMENTAL_BURST_ENERGY_SPEND_IMPACT_KEY,
    SANDRONE_ELEMENTAL_BURST_BOMBARDMENT_1_IMPACT_KEY,
    SANDRONE_ELEMENTAL_BURST_BOMBARDMENT_2_IMPACT_KEY,
    SANDRONE_ELEMENTAL_BURST_BOMBARDMENT_3_IMPACT_KEY,
    SANDRONE_ELEMENTAL_BURST_BEAM_IMPACT_KEY,
    SANDRONE_PLUNGE_COLLISION_IMPACT_KEY,
    SANDRONE_PLUNGE_LANDING_IMPACT_KEY,
)

NORMAL_ATTACK_INPUT = "normal_attack"
CHARGED_ATTACK_INPUT = "charged_attack"
ELEMENTAL_SKILL_INPUT = "elemental_skill"
ELEMENTAL_BURST_INPUT = "elemental_burst"
JUMP_INPUT = "jump"

INPUT_KIND_BY_KEY = {
    "mouse.left": NORMAL_ATTACK_INPUT,
    "mouse.right": CHARGED_ATTACK_INPUT,
    "keyboard.e": ELEMENTAL_SKILL_INPUT,
    "keyboard.q": ELEMENTAL_BURST_INPUT,
    "keyboard.space": JUMP_INPUT,
}

SANDRONE_DAMAGE_ELEMENT = Element.CRYO
SANDRONE_DAMAGE_ELEMENTAL_STRENGTH = AuraStrength.WEAK
SANDRONE_DAMAGE_ELEMENTAL_AMOUNT = AuraAmount.one()
SANDRONE_DAMAGE_ICD_SEQUENCE_KEY = "默认"

SANDRONE_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY = "elemental_skill"
SANDRONE_ELEMENTAL_SKILL_COOLDOWN_START_FRAME = 1
SANDRONE_ELEMENTAL_SKILL_COOLDOWN_FRAMES = 240
SANDRONE_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY = "elemental_burst"
SANDRONE_ELEMENTAL_BURST_COOLDOWN_START_FRAME = 1
SANDRONE_ELEMENTAL_BURST_ENERGY_SPEND_FRAME = 1
SANDRONE_ELEMENTAL_BURST_COOLDOWN_FRAMES = 900


@dataclass(frozen=True, slots=True)
class SandroneNormalAttackDamageData:
    """单段普攻的伤害数据（主攻击标签、AOE 与偏移随段变化）。

    一段的资料形状为攻击盒（区域 4.3,2.5,2.5，偏移 0.0,1.1,0.5）：按前后完整
    边长 4.3、左右完整边长 2.5 接入，资料第三分量（高度）由 X/Z 模型忽略；
    区域三个数值的轴向解释（4.3 取前后向）待资料出处确认后复核（规划文档
    待定项 8）。二、三段为圆柱，半径取资料区域第一分量。偏移保留资料原始
    三元组，投影时随攻击方向旋转（Y 轴分量不参与查询）。
    """

    main_attack_tag: str
    strike_type: StrikeType
    range_type: str
    aoe_shape: str
    aoe_radius: float
    aoe_length: float
    aoe_width: float
    aoe_offset: Vector3


SANDRONE_NORMAL_ATTACK_DAMAGE_DATA = (
    SandroneNormalAttackDamageData(
        main_attack_tag="普通攻击1",
        strike_type=StrikeType.BLUNT,
        range_type="近战",
        aoe_shape="攻击盒",
        aoe_radius=0.0,
        aoe_length=4.3,
        aoe_width=2.5,
        aoe_offset=Vector3(0.0, 1.1, 0.5),
    ),
    SandroneNormalAttackDamageData(
        main_attack_tag="普通攻击2",
        strike_type=StrikeType.BLUNT,
        range_type="近战",
        aoe_shape="圆柱",
        aoe_radius=2.7,
        aoe_length=0.0,
        aoe_width=0.0,
        aoe_offset=Vector3(0.0, 0.15, -0.3),
    ),
    SandroneNormalAttackDamageData(
        main_attack_tag="普通攻击3",
        strike_type=StrikeType.BLUNT,
        range_type="近战",
        aoe_shape="圆柱",
        aoe_radius=2.5,
        aoe_length=0.0,
        aoe_width=0.0,
        aoe_offset=Vector3(0.0, -0.3, 2.0),
    ),
)

SANDRONE_ELEMENTAL_SKILL_MAIN_ATTACK_TAG = "元素战技"
SANDRONE_ELEMENTAL_SKILL_STRIKE_TYPE = StrikeType.DEFAULT
SANDRONE_ELEMENTAL_SKILL_RANGE_TYPE = "远程"
SANDRONE_ELEMENTAL_SKILL_AOE_SHAPE = "球"
SANDRONE_ELEMENTAL_SKILL_AOE_RADIUS = 0.5
SANDRONE_ELEMENTAL_SKILL_ICD_TAG_KEY = "元素战技"

SANDRONE_ELEMENTAL_BURST_MAIN_ATTACK_TAG = "元素爆发"
SANDRONE_ELEMENTAL_BURST_STRIKE_TYPE = StrikeType.DEFAULT
SANDRONE_ELEMENTAL_BURST_RANGE_TYPE = "远程"
SANDRONE_ELEMENTAL_BURST_BOMBARDMENT_AOE_RADIUS = 7.3
SANDRONE_ELEMENTAL_BURST_BEAM_AOE_RADIUS = 7.5
SANDRONE_ELEMENTAL_BURST_ICD_TAG_KEY = "元素爆发"

# 索敌规格来自命中判定数据（普攻圆柱 5.0,6.0、棱晶弹圆柱 20,10、爆发圆柱 12,14）。
# 资料中棱晶弹的"就近"选择由当前已实现的"分数"策略承载（X/Z 就近、并列取稳定
# 实体 id 较小者）。
SANDRONE_TARGETING_NORMAL_ATTACK = TargetingSpec(
    search_area=SearchAreaSpec(shape="圆柱", radius=5.0, height=6.0),
    selection_policy_key="分数",
)
SANDRONE_TARGETING_ELEMENTAL_SKILL = TargetingSpec(
    search_area=SearchAreaSpec(shape="圆柱", radius=20.0, height=10.0),
    selection_policy_key="分数",
)
SANDRONE_TARGETING_ELEMENTAL_BURST = TargetingSpec(
    search_area=SearchAreaSpec(shape="圆柱", radius=12.0, height=14.0),
    selection_policy_key="分数",
)

SANDRONE_NORMAL_ATTACK_ACTION_KEYS = (
    SANDRONE_NORMAL_ATTACK_1_ACTION_KEY,
    SANDRONE_NORMAL_ATTACK_2_ACTION_KEY,
    SANDRONE_NORMAL_ATTACK_3_ACTION_KEY,
)

SANDRONE_ACTION_TABLE: dict[str, TimedActionSpec] = {
    SANDRONE_NORMAL_ATTACK_1_ACTION_KEY: TimedActionSpec(
        action_key=SANDRONE_NORMAL_ATTACK_1_ACTION_KEY,
        duration_frames=130,
        hit_frame=44,
        impact_key=SANDRONE_NORMAL_ATTACK_1_IMPACT_KEY,
        targeting=SANDRONE_TARGETING_NORMAL_ATTACK,
        transitions={NORMAL_ATTACK_INPUT: 59},
    ),
    SANDRONE_NORMAL_ATTACK_2_ACTION_KEY: TimedActionSpec(
        action_key=SANDRONE_NORMAL_ATTACK_2_ACTION_KEY,
        duration_frames=59,
        hit_frame=24,
        impact_key=SANDRONE_NORMAL_ATTACK_2_IMPACT_KEY,
        targeting=SANDRONE_TARGETING_NORMAL_ATTACK,
        transitions={NORMAL_ATTACK_INPUT: 59},
    ),
    SANDRONE_NORMAL_ATTACK_3_ACTION_KEY: TimedActionSpec(
        action_key=SANDRONE_NORMAL_ATTACK_3_ACTION_KEY,
        duration_frames=159,
        hit_frame=50,
        impact_key=SANDRONE_NORMAL_ATTACK_3_IMPACT_KEY,
        targeting=SANDRONE_TARGETING_NORMAL_ATTACK,
        transitions={NORMAL_ATTACK_INPUT: 159},
    ),
    SANDRONE_ELEMENTAL_SKILL_ACTION_KEY: TimedActionSpec(
        action_key=SANDRONE_ELEMENTAL_SKILL_ACTION_KEY,
        duration_frames=33,
        impact_points=(
            TimedImpactPointSpec(
                impact_key=SANDRONE_ELEMENTAL_SKILL_PRISM_1_IMPACT_KEY,
                frame=16,
                targeting=SANDRONE_TARGETING_ELEMENTAL_SKILL,
            ),
            TimedImpactPointSpec(
                impact_key=SANDRONE_ELEMENTAL_SKILL_PRISM_2_IMPACT_KEY,
                frame=32,
                targeting=SANDRONE_TARGETING_ELEMENTAL_SKILL,
            ),
        ),
        cooldown_start_frame=SANDRONE_ELEMENTAL_SKILL_COOLDOWN_START_FRAME,
        cooldown_ability_key=SANDRONE_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
        transitions={
            NORMAL_ATTACK_INPUT: 33,
            ELEMENTAL_SKILL_INPUT: 33,
            ELEMENTAL_BURST_INPUT: 34,
            JUMP_INPUT: 5,
        },
    ),
    SANDRONE_ELEMENTAL_BURST_ACTION_KEY: TimedActionSpec(
        action_key=SANDRONE_ELEMENTAL_BURST_ACTION_KEY,
        duration_frames=306,
        impact_points=(
            TimedImpactPointSpec(
                impact_key=SANDRONE_ELEMENTAL_BURST_ENERGY_SPEND_IMPACT_KEY,
                frame=SANDRONE_ELEMENTAL_BURST_ENERGY_SPEND_FRAME,
            ),
            TimedImpactPointSpec(
                impact_key=SANDRONE_ELEMENTAL_BURST_BOMBARDMENT_1_IMPACT_KEY,
                frame=182,
                targeting=SANDRONE_TARGETING_ELEMENTAL_BURST,
            ),
            TimedImpactPointSpec(
                impact_key=SANDRONE_ELEMENTAL_BURST_BOMBARDMENT_2_IMPACT_KEY,
                frame=198,
                targeting=SANDRONE_TARGETING_ELEMENTAL_BURST,
            ),
            TimedImpactPointSpec(
                impact_key=SANDRONE_ELEMENTAL_BURST_BOMBARDMENT_3_IMPACT_KEY,
                frame=214,
                targeting=SANDRONE_TARGETING_ELEMENTAL_BURST,
            ),
            TimedImpactPointSpec(
                impact_key=SANDRONE_ELEMENTAL_BURST_BEAM_IMPACT_KEY,
                frame=252,
                targeting=SANDRONE_TARGETING_ELEMENTAL_BURST,
            ),
        ),
        cooldown_start_frame=SANDRONE_ELEMENTAL_BURST_COOLDOWN_START_FRAME,
        cooldown_ability_key=SANDRONE_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY,
        transitions={
            NORMAL_ATTACK_INPUT: 307,
            ELEMENTAL_SKILL_INPUT: 307,
            JUMP_INPUT: 340,
        },
    ),
    SANDRONE_JUMP_ACTION_KEY: TimedActionSpec(
        action_key=SANDRONE_JUMP_ACTION_KEY,
        duration_frames=31,
        transitions={},
    ),
    SANDRONE_PLUNGE_ACTION_KEY: TimedActionSpec(
        action_key=SANDRONE_PLUNGE_ACTION_KEY,
        duration_frames=1,
        transitions={},
    ),
}
