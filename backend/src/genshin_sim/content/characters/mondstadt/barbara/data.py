"""芭芭拉内容数据：稳定键、动作数据表与伤害数据。

数据与解释逻辑分离：``actions.py`` 只保留解释器与动作编译，``content.py``
只负责内容单元编译。本文件统一承载角色身份键（handler/action/impact）、
输入映射、帧表与动作表、普攻伤害数据；每个角色只有一张动作数据表，与角色
唯一动作解释器对应。普攻倍率仍来自资产库倍率表，不在本文件维护。
"""

from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.content.generic.timed_action import (
    TimedActionSpec,
    TimedImpactPointSpec,
)
from genshin_sim.core.actions import SearchAreaSpec, TargetingSpec
from genshin_sim.core.elements import AuraAmount, Element
from genshin_sim.core.impacts import StrikeType
from genshin_sim.core.space import Vector3
from genshin_sim.core.systems.aura import AuraStrength

BARBARA_CHARACTER_HANDLER_KEY = "character.barbara"
BARBARA_ASSET_KEY = "character:10000014"
BARBARA_CONTENT_VERSION = "dev-elemental-burst"

BARBARA_ENCORE_EFFECT_HANDLER_KEY = "character.barbara.passive.encore"
BARBARA_ENCORE_EXTEND_IMPACT_KEY = f"{BARBARA_CHARACTER_HANDLER_KEY}.passive.encore.extend"

BARBARA_CONSTELLATION_C1_HANDLER_KEY = "character.barbara.constellation.c1"
BARBARA_CONSTELLATION_C2_HANDLER_KEY = "character.barbara.constellation.c2"
BARBARA_CONSTELLATION_C3_HANDLER_KEY = "character.barbara.constellation.c3"
BARBARA_CONSTELLATION_C4_HANDLER_KEY = "character.barbara.constellation.c4"
BARBARA_CONSTELLATION_C5_HANDLER_KEY = "character.barbara.constellation.c5"
BARBARA_CONSTELLATION_C6_HANDLER_KEY = "character.barbara.constellation.c6"
BARBARA_PASSIVE_SEASON_HANDLER_KEY = "character.barbara.passive.season"
BARBARA_PASSIVE_EXPLORATION_COOKING_HANDLER_KEY = "character.barbara.passive_exploration.cooking"

BARBARA_CONSTELLATION_C1_ENERGY_IMPACT_KEY = f"{BARBARA_CONSTELLATION_C1_HANDLER_KEY}.energy"
BARBARA_CONSTELLATION_C4_ENERGY_IMPACT_KEY = f"{BARBARA_CONSTELLATION_C4_HANDLER_KEY}.energy"
BARBARA_CONSTELLATION_C2_COOLDOWN_TERM_KEY = (
    f"{BARBARA_CONSTELLATION_C2_HANDLER_KEY}.cooldown_reduction"
)
BARBARA_CONSTELLATION_C2_HYDRO_PROVIDER_KEY = f"{BARBARA_CONSTELLATION_C2_HANDLER_KEY}.hydro_bonus"

BARBARA_NORMAL_ATTACK_1_ACTION_KEY = "character.barbara.normal_attack.1"
BARBARA_NORMAL_ATTACK_2_ACTION_KEY = "character.barbara.normal_attack.2"
BARBARA_NORMAL_ATTACK_3_ACTION_KEY = "character.barbara.normal_attack.3"
BARBARA_NORMAL_ATTACK_4_ACTION_KEY = "character.barbara.normal_attack.4"
BARBARA_CHARGED_ATTACK_ACTION_KEY = "character.barbara.charged_attack"
BARBARA_ELEMENTAL_SKILL_ACTION_KEY = "character.barbara.elemental_skill"
BARBARA_ELEMENTAL_BURST_ACTION_KEY = "character.barbara.elemental_burst"
BARBARA_JUMP_ACTION_KEY = "character.barbara.jump"
BARBARA_PLUNGE_ACTION_KEY = "character.barbara.plunge"

BARBARA_RING_OBJECT_KEY = "barbara.ring"

BARBARA_NORMAL_ATTACK_1_IMPACT_KEY = f"{BARBARA_NORMAL_ATTACK_1_ACTION_KEY}.hit"
BARBARA_NORMAL_ATTACK_2_IMPACT_KEY = f"{BARBARA_NORMAL_ATTACK_2_ACTION_KEY}.hit"
BARBARA_NORMAL_ATTACK_3_IMPACT_KEY = f"{BARBARA_NORMAL_ATTACK_3_ACTION_KEY}.hit"
BARBARA_NORMAL_ATTACK_4_IMPACT_KEY = f"{BARBARA_NORMAL_ATTACK_4_ACTION_KEY}.hit"
BARBARA_CHARGED_ATTACK_IMPACT_KEY = f"{BARBARA_CHARGED_ATTACK_ACTION_KEY}.hit"
BARBARA_ELEMENTAL_SKILL_IMPACT_KEY = f"{BARBARA_ELEMENTAL_SKILL_ACTION_KEY}.hit"
BARBARA_ELEMENTAL_SKILL_SELF_WET_IMPACT_KEY = f"{BARBARA_ELEMENTAL_SKILL_ACTION_KEY}.self_wet"
BARBARA_ELEMENTAL_SKILL_RING_CREATE_IMPACT_KEY = f"{BARBARA_ELEMENTAL_SKILL_ACTION_KEY}.create_ring"
BARBARA_ELEMENTAL_SKILL_RING_HEAL_IMPACT_KEY = f"{BARBARA_ELEMENTAL_SKILL_ACTION_KEY}.ring_heal"
BARBARA_ELEMENTAL_SKILL_RING_WET_IMPACT_KEY = f"{BARBARA_ELEMENTAL_SKILL_ACTION_KEY}.ring_wet"
BARBARA_ELEMENTAL_SKILL_ON_HIT_HEAL_IMPACT_KEY = f"{BARBARA_ELEMENTAL_SKILL_ACTION_KEY}.on_hit_heal"
BARBARA_ELEMENTAL_BURST_HEAL_IMPACT_KEY = f"{BARBARA_ELEMENTAL_BURST_ACTION_KEY}.heal"
BARBARA_ELEMENTAL_BURST_ENERGY_SPEND_IMPACT_KEY = (
    f"{BARBARA_ELEMENTAL_BURST_ACTION_KEY}.spend_energy"
)
BARBARA_JUMP_IMPACT_KEY = f"{BARBARA_JUMP_ACTION_KEY}.hit"
BARBARA_PLUNGE_COLLISION_IMPACT_KEY = f"{BARBARA_PLUNGE_ACTION_KEY}.collision"
BARBARA_PLUNGE_LANDING_IMPACT_KEY = f"{BARBARA_PLUNGE_ACTION_KEY}.landing"

BARBARA_HIT_IMPACT_KEYS = (
    BARBARA_NORMAL_ATTACK_1_IMPACT_KEY,
    BARBARA_NORMAL_ATTACK_2_IMPACT_KEY,
    BARBARA_NORMAL_ATTACK_3_IMPACT_KEY,
    BARBARA_NORMAL_ATTACK_4_IMPACT_KEY,
    BARBARA_CHARGED_ATTACK_IMPACT_KEY,
    BARBARA_ELEMENTAL_SKILL_IMPACT_KEY,
    BARBARA_ELEMENTAL_SKILL_SELF_WET_IMPACT_KEY,
    BARBARA_ELEMENTAL_SKILL_RING_CREATE_IMPACT_KEY,
    BARBARA_ELEMENTAL_BURST_HEAL_IMPACT_KEY,
    BARBARA_ELEMENTAL_BURST_ENERGY_SPEND_IMPACT_KEY,
    BARBARA_JUMP_IMPACT_KEY,
    BARBARA_PLUNGE_COLLISION_IMPACT_KEY,
    BARBARA_PLUNGE_LANDING_IMPACT_KEY,
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


BARBARA_DAMAGE_ELEMENT = Element.HYDRO
BARBARA_DAMAGE_ADDITIONAL_ATTACK_TAGS = ()
BARBARA_DAMAGE_STRIKE_TYPE = StrikeType.DEFAULT
BARBARA_DAMAGE_RANGE_TYPE = "默认"
BARBARA_DAMAGE_ELEMENTAL_STRENGTH = AuraStrength.WEAK
BARBARA_DAMAGE_ELEMENTAL_AMOUNT = AuraAmount.one()
BARBARA_DAMAGE_ICD_SEQUENCE_KEY = "默认"
BARBARA_DAMAGE_ICD_TAG_KEY = "普通攻击"
BARBARA_DAMAGE_AOE_SHAPE = "球"
BARBARA_CHARGED_ATTACK_MAIN_ATTACK_TAG = "重击"
BARBARA_CHARGED_ATTACK_AOE_RADIUS = 3.0
BARBARA_CHARGED_ATTACK_AOE_OFFSET = Vector3(0.0, 1.0, 0.0)

BARBARA_ELEMENTAL_SKILL_MAIN_ATTACK_TAG = "元素战技"
BARBARA_ELEMENTAL_SKILL_AOE_RADIUS = 3.0
BARBARA_ELEMENTAL_SKILL_AOE_OFFSET = Vector3(0.0, 0.0, 0.0)
BARBARA_ELEMENTAL_SKILL_ICD_SEQUENCE_KEY = "默认"
BARBARA_ELEMENTAL_SKILL_ICD_TAG_KEY = "元素战技"

# 歌声之环（已确认资料）：持续 15s + 6 帧；首次治疗第 6 帧、间隔 5s；
# 接触施湿首次第 36 帧、间隔 1.5s。环实体跟随当前场上角色。
BARBARA_RING_DURATION_FRAMES = 907
BARBARA_RING_HEAL_FIRST_TICK_OFFSET = 6
BARBARA_RING_HEAL_TICK_INTERVAL = 300
BARBARA_RING_WET_FIRST_TICK_OFFSET = 36
BARBARA_RING_WET_TICK_INTERVAL = 90
BARBARA_RING_WET_AOE_SHAPE = "圆柱"
BARBARA_RING_WET_AOE_RADIUS = 1.0
BARBARA_RING_WET_AOE_OFFSET = Vector3(0.0, -0.25, 0.0)
BARBARA_RING_WET_ICD_SEQUENCE_KEY = "芭芭拉水环"
BARBARA_RING_WET_ICD_TAG_KEY = "元素战技"
BARBARA_RING_WET_ICD_RESET_INTERVAL_FRAMES = 150
BARBARA_RING_WET_ICD_APPLICATION_SEQUENCE = (
    1,
    0,
    0,
    1,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
)

BARBARA_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY = "elemental_skill"
BARBARA_ELEMENTAL_SKILL_COOLDOWN_START_FRAME = 3
BARBARA_ELEMENTAL_SKILL_COOLDOWN_FRAMES = 1920
BARBARA_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY = "elemental_burst"
BARBARA_ELEMENTAL_BURST_COOLDOWN_START_FRAME = 1
BARBARA_ELEMENTAL_BURST_ENERGY_SPEND_FRAME = 6
BARBARA_ELEMENTAL_BURST_HEAL_FRAME = 77
BARBARA_ELEMENTAL_BURST_COOLDOWN_FRAMES = 1200


@dataclass(frozen=True, slots=True)
class BarbaraNormalAttackDamageData:
    """单段普攻的伤害数据（主攻击标签与 AOE 随段变化）。"""

    main_attack_tag: str
    aoe_radius: float
    aoe_offset: Vector3 | None = None


BARBARA_NORMAL_ATTACK_DAMAGE_DATA = (
    BarbaraNormalAttackDamageData(main_attack_tag="普通攻击1", aoe_radius=1.0),
    BarbaraNormalAttackDamageData(main_attack_tag="普通攻击2", aoe_radius=1.0),
    BarbaraNormalAttackDamageData(main_attack_tag="普通攻击3", aoe_radius=1.0),
    BarbaraNormalAttackDamageData(
        main_attack_tag="普通攻击4",
        aoe_radius=2.0,
        aoe_offset=Vector3(0.0, 0.0, 0.0),
    ),
)


BARBARA_TARGETING = TargetingSpec(
    search_area=SearchAreaSpec(shape="圆柱", radius=15.0, height=10.0),
    selection_policy_key="分数",
)


BARBARA_NORMAL_ATTACK_ACTION_KEYS = (
    BARBARA_NORMAL_ATTACK_1_ACTION_KEY,
    BARBARA_NORMAL_ATTACK_2_ACTION_KEY,
    BARBARA_NORMAL_ATTACK_3_ACTION_KEY,
    BARBARA_NORMAL_ATTACK_4_ACTION_KEY,
)


BARBARA_ACTION_TABLE: dict[str, TimedActionSpec] = {
    BARBARA_NORMAL_ATTACK_1_ACTION_KEY: TimedActionSpec(
        action_key=BARBARA_NORMAL_ATTACK_1_ACTION_KEY,
        duration_frames=15,
        hit_frame=6,
        impact_key=BARBARA_NORMAL_ATTACK_1_IMPACT_KEY,
        targeting=BARBARA_TARGETING,
        transitions={NORMAL_ATTACK_INPUT: 15, CHARGED_ATTACK_INPUT: 18},
    ),
    BARBARA_NORMAL_ATTACK_2_ACTION_KEY: TimedActionSpec(
        action_key=BARBARA_NORMAL_ATTACK_2_ACTION_KEY,
        duration_frames=21,
        hit_frame=11,
        impact_key=BARBARA_NORMAL_ATTACK_2_IMPACT_KEY,
        targeting=BARBARA_TARGETING,
        transitions={NORMAL_ATTACK_INPUT: 21, CHARGED_ATTACK_INPUT: 24},
    ),
    BARBARA_NORMAL_ATTACK_3_ACTION_KEY: TimedActionSpec(
        action_key=BARBARA_NORMAL_ATTACK_3_ACTION_KEY,
        duration_frames=22,
        hit_frame=12,
        impact_key=BARBARA_NORMAL_ATTACK_3_IMPACT_KEY,
        targeting=BARBARA_TARGETING,
        transitions={NORMAL_ATTACK_INPUT: 22, CHARGED_ATTACK_INPUT: 28},
    ),
    BARBARA_NORMAL_ATTACK_4_ACTION_KEY: TimedActionSpec(
        action_key=BARBARA_NORMAL_ATTACK_4_ACTION_KEY,
        duration_frames=60,
        hit_frame=32,
        impact_key=BARBARA_NORMAL_ATTACK_4_IMPACT_KEY,
        targeting=BARBARA_TARGETING,
        transitions={NORMAL_ATTACK_INPUT: 60},
    ),
    BARBARA_CHARGED_ATTACK_ACTION_KEY: TimedActionSpec(
        action_key=BARBARA_CHARGED_ATTACK_ACTION_KEY,
        duration_frames=56,
        hit_frame=55,
        impact_key=BARBARA_CHARGED_ATTACK_IMPACT_KEY,
        targeting=BARBARA_TARGETING,
        transitions={
            NORMAL_ATTACK_INPUT: 89,
            CHARGED_ATTACK_INPUT: 88,
            ELEMENTAL_SKILL_INPUT: 88,
            ELEMENTAL_BURST_INPUT: 87,
            JUMP_INPUT: 56,
        },
    ),
    BARBARA_ELEMENTAL_SKILL_ACTION_KEY: TimedActionSpec(
        action_key=BARBARA_ELEMENTAL_SKILL_ACTION_KEY,
        duration_frames=54,
        impact_points=(
            TimedImpactPointSpec(
                impact_key=BARBARA_ELEMENTAL_SKILL_RING_CREATE_IMPACT_KEY,
                frame=0,
            ),
            TimedImpactPointSpec(
                impact_key=BARBARA_ELEMENTAL_SKILL_SELF_WET_IMPACT_KEY,
                frame=3,
            ),
            TimedImpactPointSpec(
                impact_key=BARBARA_ELEMENTAL_SKILL_IMPACT_KEY,
                frame=42,
                targeting=BARBARA_TARGETING,
            ),
        ),
        cooldown_start_frame=BARBARA_ELEMENTAL_SKILL_COOLDOWN_START_FRAME,
        cooldown_ability_key=BARBARA_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
        transitions={
            NORMAL_ATTACK_INPUT: 54,
            CHARGED_ATTACK_INPUT: 54,
            ELEMENTAL_SKILL_INPUT: 54,
            ELEMENTAL_BURST_INPUT: 55,
            JUMP_INPUT: 5,
        },
    ),
    BARBARA_ELEMENTAL_BURST_ACTION_KEY: TimedActionSpec(
        action_key=BARBARA_ELEMENTAL_BURST_ACTION_KEY,
        duration_frames=140,
        impact_points=(
            TimedImpactPointSpec(
                impact_key=BARBARA_ELEMENTAL_BURST_ENERGY_SPEND_IMPACT_KEY,
                frame=BARBARA_ELEMENTAL_BURST_ENERGY_SPEND_FRAME,
            ),
            TimedImpactPointSpec(
                impact_key=BARBARA_ELEMENTAL_BURST_HEAL_IMPACT_KEY,
                frame=BARBARA_ELEMENTAL_BURST_HEAL_FRAME,
            ),
        ),
        cooldown_start_frame=BARBARA_ELEMENTAL_BURST_COOLDOWN_START_FRAME,
        cooldown_ability_key=BARBARA_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY,
        transitions={
            NORMAL_ATTACK_INPUT: 141,
            CHARGED_ATTACK_INPUT: 140,
            ELEMENTAL_SKILL_INPUT: 141,
            JUMP_INPUT: 160,
        },
    ),
    BARBARA_JUMP_ACTION_KEY: TimedActionSpec(
        action_key=BARBARA_JUMP_ACTION_KEY,
        duration_frames=31,
        hit_frame=31,
        impact_key=BARBARA_JUMP_IMPACT_KEY,
        targeting=TargetingSpec(radius=1.0),
        transitions={},
    ),
    BARBARA_PLUNGE_ACTION_KEY: TimedActionSpec(
        action_key=BARBARA_PLUNGE_ACTION_KEY,
        duration_frames=1,
        transitions={},
    ),
}
