"""砂糖内容数据：稳定键、动作数据表与伤害数据。"""

from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.content.generic.timed_action import TimedActionSpec, TimedImpactPointSpec
from genshin_sim.core.actions import SearchAreaSpec, TargetingSpec
from genshin_sim.core.elements import AuraAmount, AuraKind, Element
from genshin_sim.core.impacts import StrikeType
from genshin_sim.core.space import Vector3
from genshin_sim.core.systems.aura import AuraStrength
from genshin_sim.core.systems.reaction.mechanics.stellar_swirl.keys import (
    STELLAR_SWIRL_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.swirl import SWIRL_REACTION_KEY

SUCROSE_CHARACTER_HANDLER_KEY = "character.sucrose"
SUCROSE_CONTENT_VERSION = "dev"

SUCROSE_JUMP_ACTION_KEY = "character.sucrose.jump"
SUCROSE_PLUNGE_ACTION_KEY = "character.sucrose.plunge"

# --- 动作键 ---------------------------

SUCROSE_NORMAL_ATTACK_1_ACTION_KEY = "character.sucrose.wind_spirit_creation.1"
SUCROSE_NORMAL_ATTACK_2_ACTION_KEY = "character.sucrose.wind_spirit_creation.2"
SUCROSE_NORMAL_ATTACK_3_ACTION_KEY = "character.sucrose.wind_spirit_creation.3"
SUCROSE_NORMAL_ATTACK_4_ACTION_KEY = "character.sucrose.wind_spirit_creation.4"
SUCROSE_CHARGED_ATTACK_ACTION_KEY = "character.sucrose.wind_spirit_creation.charged"

# 元素战技 / 元素爆发动作键。
SUCROSE_ELEMENTAL_SKILL_ACTION_KEY = "character.sucrose.astable_anemohypostasis_creation_6308"
SUCROSE_ELEMENTAL_BURST_ACTION_KEY = "character.sucrose.forbidden_creation_isomer_75_type_ii"

SUCROSE_NORMAL_ATTACK_ACTION_KEYS = (
    SUCROSE_NORMAL_ATTACK_1_ACTION_KEY,
    SUCROSE_NORMAL_ATTACK_2_ACTION_KEY,
    SUCROSE_NORMAL_ATTACK_3_ACTION_KEY,
    SUCROSE_NORMAL_ATTACK_4_ACTION_KEY,
)

# --- 影响点键 -------------------------------------------------------------

SUCROSE_NORMAL_ATTACK_1_IMPACT_KEY = f"{SUCROSE_NORMAL_ATTACK_1_ACTION_KEY}.hit"
SUCROSE_NORMAL_ATTACK_2_IMPACT_KEY = f"{SUCROSE_NORMAL_ATTACK_2_ACTION_KEY}.hit"
SUCROSE_NORMAL_ATTACK_3_IMPACT_KEY = f"{SUCROSE_NORMAL_ATTACK_3_ACTION_KEY}.hit"
SUCROSE_NORMAL_ATTACK_4_IMPACT_KEY = f"{SUCROSE_NORMAL_ATTACK_4_ACTION_KEY}.hit"
SUCROSE_CHARGED_ATTACK_IMPACT_KEY = f"{SUCROSE_CHARGED_ATTACK_ACTION_KEY}.hit"
SUCROSE_ELEMENTAL_SKILL_IMPACT_KEY = f"{SUCROSE_ELEMENTAL_SKILL_ACTION_KEY}.hit"
SUCROSE_JUMP_IMPACT_KEY = f"{SUCROSE_JUMP_ACTION_KEY}.hit"
SUCROSE_PLUNGE_COLLISION_IMPACT_KEY = f"{SUCROSE_PLUNGE_ACTION_KEY}.collision"
SUCROSE_PLUNGE_LANDING_IMPACT_KEY = f"{SUCROSE_PLUNGE_ACTION_KEY}.landing"

# 元素爆发本体不产生角色侧命中点（伤害由大型风灵独立按拍产出），故爆发在动作
# 表上只有两个非伤害影响点：大型风灵创建（创建帧）与能量花费帧。
SUCROSE_SPIRIT_CREATE_IMPACT_KEY = f"{SUCROSE_CHARACTER_HANDLER_KEY}.spirit.create"
SUCROSE_ELEMENTAL_BURST_ENERGY_SPEND_IMPACT_KEY = (
    f"{SUCROSE_ELEMENTAL_BURST_ACTION_KEY}.energy_spend"
)

# 大型风灵产出的两个伤害通道影响键：请求由创建物 tick 产出（非动作影响点），
# 键用于请求识别与审计。染色通道的风元素伤与染色伤害同帧、共用同一目标集合。
SUCROSE_SPIRIT_ANEMO_TICK_IMPACT_KEY = f"{SUCROSE_CHARACTER_HANDLER_KEY}.spirit.anemo_tick"
SUCROSE_SPIRIT_ABSORBED_TICK_IMPACT_KEY = f"{SUCROSE_CHARACTER_HANDLER_KEY}.spirit.absorbed_tick"

# 产球请求的影响键：请求不是动作影响点产出，而是由产球 hook 产出；键用于
# 请求识别与审计匹配。
SUCROSE_PARTICLE_SPAWN_IMPACT_KEY = f"{SUCROSE_CHARACTER_HANDLER_KEY}.particle.spawn"

SUCROSE_HIT_IMPACT_KEYS = (
    SUCROSE_NORMAL_ATTACK_1_IMPACT_KEY,
    SUCROSE_NORMAL_ATTACK_2_IMPACT_KEY,
    SUCROSE_NORMAL_ATTACK_3_IMPACT_KEY,
    SUCROSE_NORMAL_ATTACK_4_IMPACT_KEY,
    SUCROSE_CHARGED_ATTACK_IMPACT_KEY,
    SUCROSE_ELEMENTAL_SKILL_IMPACT_KEY,
    SUCROSE_JUMP_IMPACT_KEY,
    SUCROSE_PLUNGE_COLLISION_IMPACT_KEY,
    SUCROSE_PLUNGE_LANDING_IMPACT_KEY,
    SUCROSE_SPIRIT_CREATE_IMPACT_KEY,
    SUCROSE_ELEMENTAL_BURST_ENERGY_SPEND_IMPACT_KEY,
)

# --- 输入映射 -------------------------------------------------------------

NORMAL_ATTACK_INPUT = "normal_attack"
CHARGED_ATTACK_INPUT = "charged_attack"
ELEMENTAL_SKILL_INPUT = "elemental_skill"
ELEMENTAL_BURST_INPUT = "elemental_burst"
JUMP_INPUT = "jump"

# 左键长按分界（帧）：按住时长达到该值按重击解释，未达到按点按普攻解释。
# 16 帧为分界值。
SUCROSE_HOLD_INPUT_MIN_FRAMES = 16

# 物理键到输入种类的映射。重击是左键的点按/长按双语义，不占独立按键；「右键」
# 是冲刺位，本项目冲刺未接入，故不映射。当前开放普攻 / 重击 / 跳跃 / 元素
# 战技 / 元素爆发五类输入。
SUCROSE_INPUT_KIND_BY_KEY = {
    "mouse.left": NORMAL_ATTACK_INPUT,
    "keyboard.e": ELEMENTAL_SKILL_INPUT,
    "keyboard.q": ELEMENTAL_BURST_INPUT,
    "keyboard.space": JUMP_INPUT,
}

# --- 伤害稳定数据 ---------------------------------------------------------

SUCROSE_DAMAGE_ELEMENT = Element.ANEMO
SUCROSE_DAMAGE_ADDITIONAL_ATTACK_TAGS = ()
SUCROSE_DAMAGE_STRIKE_TYPE = StrikeType.DEFAULT
SUCROSE_DAMAGE_RANGE_TYPE = "默认"
SUCROSE_DAMAGE_ELEMENTAL_STRENGTH = AuraStrength.WEAK
SUCROSE_DAMAGE_ELEMENTAL_AMOUNT = AuraAmount.one()
SUCROSE_DAMAGE_ICD_SEQUENCE_KEY = "默认"
SUCROSE_DAMAGE_ICD_TAG_KEY = "普通攻击"
SUCROSE_DAMAGE_AOE_SHAPE = "球"

SUCROSE_CHARGED_ATTACK_MAIN_ATTACK_TAG = "重击"
SUCROSE_CHARGED_ATTACK_AOE_SHAPE = "攻击盒"
SUCROSE_CHARGED_ATTACK_AOE_RADIUS = 0.0
SUCROSE_CHARGED_ATTACK_AOE_LENGTH = 3.2
SUCROSE_CHARGED_ATTACK_AOE_WIDTH = 3.0
SUCROSE_CHARGED_ATTACK_AOE_OFFSET = Vector3(0.0, 1.5, -0.2)


@dataclass(frozen=True, slots=True)
class SucroseNormalAttackDamageData:
    """单段普攻的伤害数据（主攻击标签与 AOE 随段变化）。"""

    main_attack_tag: str
    aoe_radius: float
    aoe_offset: Vector3 | None = None


SUCROSE_NORMAL_ATTACK_DAMAGE_DATA = (
    SucroseNormalAttackDamageData(main_attack_tag="普通攻击1", aoe_radius=1.0),
    SucroseNormalAttackDamageData(main_attack_tag="普通攻击2", aoe_radius=1.0),
    SucroseNormalAttackDamageData(main_attack_tag="普通攻击3", aoe_radius=1.0),
    SucroseNormalAttackDamageData(main_attack_tag="普通攻击4", aoe_radius=2.0),
)


SUCROSE_TARGETING = TargetingSpec(
    search_area=SearchAreaSpec(shape="圆柱", radius=15.0, height=10.0),
    selection_policy_key="分数",
)


# --- 元素战技伤害数据 -----------------------------------------------------

SUCROSE_ELEMENTAL_SKILL_HIT_FRAME = 42
SUCROSE_ELEMENTAL_SKILL_MAIN_ATTACK_TAG = "元素战技"
SUCROSE_ELEMENTAL_SKILL_AOE_SHAPE = "圆柱"
SUCROSE_ELEMENTAL_SKILL_AOE_RADIUS = 6.0
SUCROSE_ELEMENTAL_SKILL_AOE_OFFSET = Vector3(0.0, -3.0, 0.0)

# --- 冷却（元素战技） ------------------------------------------------------

SUCROSE_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY = "elemental_skill"
SUCROSE_ELEMENTAL_SKILL_COOLDOWN_FRAMES = 900
SUCROSE_ELEMENTAL_SKILL_COOLDOWN_START_FRAME = 9
SUCROSE_ELEMENTAL_SKILL_BASE_CHARGES = 1

# --- 产球 -----------------------------------------------------------------

SUCROSE_PARTICLE_TRIGGER_IMPACT_KEYS = (SUCROSE_ELEMENTAL_SKILL_IMPACT_KEY,)
SUCROSE_PARTICLE_ELEMENT = Element.ANEMO
SUCROSE_PARTICLE_COUNT = 4
SUCROSE_PARTICLE_COOLDOWN_FRAMES = 24
SUCROSE_PARTICLE_TRAVEL_FRAMES = 30
SUCROSE_STATE_LAST_PARTICLE_FRAME = "sucrose_last_particle_frame"


# --- 元素爆发伤害数据 -----------------------------------------------------

SUCROSE_ELEMENTAL_BURST_CREATE_FRAME = 17
SUCROSE_ELEMENTAL_BURST_ENERGY_SPEND_FRAME = 21
SUCROSE_ELEMENTAL_BURST_MAIN_ATTACK_TAG = "元素爆发"
SUCROSE_ELEMENTAL_BURST_AOE_SHAPE = "圆柱"
SUCROSE_ELEMENTAL_BURST_AOE_RADIUS = 8.0
SUCROSE_ELEMENTAL_BURST_AOE_OFFSET = Vector3(0.0, -2.5, 0.0)

# --- 冷却（元素爆发） ------------------------------------------------------

SUCROSE_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY = "elemental_burst"
SUCROSE_ELEMENTAL_BURST_COOLDOWN_FRAMES = 1200
SUCROSE_ELEMENTAL_BURST_COOLDOWN_START_FRAME = 18

# --- 大型风灵（元素爆发创建物） --------------------------------------------

SUCROSE_SPIRIT_OBJECT_KEY = "sucrose.large_wind_spirit"
SUCROSE_SPIRIT_ATTACK_SCHEDULE_KEY = "attack"
SUCROSE_SPIRIT_PROBE_SCHEDULE_KEY = "probe"
SUCROSE_SPIRIT_TICK_PERIOD_FRAMES = 120
SUCROSE_SPIRIT_TICK_COUNT = 3
SUCROSE_SPIRIT_WINDOW_FRAMES = 360
SUCROSE_SPIRIT_DURATION_FRAMES = SUCROSE_SPIRIT_WINDOW_FRAMES + 1

# --- 染色机制（判定区 / 节奏 / 优先级） ------------------------------------

SUCROSE_SPIRIT_PROBE_INTERVAL_FRAMES = 18
SUCROSE_SPIRIT_PROBE_BOX_LATERAL = 2.5  # x：左右
SUCROSE_SPIRIT_PROBE_BOX_DEPTH = 2.5  # z：前后
SUCROSE_SPIRIT_PROBE_BOX_SHAPE = "攻击盒"
SUCROSE_SPIRIT_PROBE_BOX_RADIUS = 0.0

SUCROSE_SPIRIT_ABSORPTION_PRIORITY = (
    (AuraKind.PYRO, Element.PYRO),
    (AuraKind.HYDRO, Element.HYDRO),
    (AuraKind.ELECTRO, Element.ELECTRO),
    (AuraKind.CRYO, Element.CRYO),
    (AuraKind.FROZEN, Element.CRYO),
)


# --- 固有天赋 -------------------------------------------------------------

SUCROSE_PASSIVE_A1_HANDLER_KEY = "sucrose.passive.catalyst_conversion"
SUCROSE_PASSIVE_A4_HANDLER_KEY = "sucrose.passive.mollis_favonius"

SUCROSE_TALENT_FRAMES_PER_SECOND = 60

SUCROSE_A1_MASTERY_FLAT = 50.0
SUCROSE_A1_DURATION_FRAMES = 8 * SUCROSE_TALENT_FRAMES_PER_SECOND
SUCROSE_A1_MECHANIC_KEY = f"{SUCROSE_PASSIVE_A1_HANDLER_KEY}.mastery"
SUCROSE_A1_BUFF_DEFINITION_KEY = f"{SUCROSE_PASSIVE_A1_HANDLER_KEY}.mastery.buff"
SUCROSE_A1_CONFLICT_KEY = f"{SUCROSE_PASSIVE_A1_HANDLER_KEY}.mastery.conflict"
SUCROSE_A1_MASTERY_TERM_KEY = f"{SUCROSE_PASSIVE_A1_HANDLER_KEY}.mastery.term"

# A1 触发面：普通扩散与星扩散。
SUCROSE_A1_TRIGGER_REACTION_KEYS = frozenset(
    {
        SWIRL_REACTION_KEY,
        STELLAR_SWIRL_REACTION_KEY,
    }
)

# 被扩散附着到元素伤害元素的映射：风元素不形成持久附着，故只覆盖四种可扩散
# 附着；FROZEN 与染色判定的第 4 档同口径，映射为冰元素。
SUCROSE_AURA_ELEMENT_MAP = {
    AuraKind.PYRO: Element.PYRO,
    AuraKind.HYDRO: Element.HYDRO,
    AuraKind.ELECTRO: Element.ELECTRO,
    AuraKind.CRYO: Element.CRYO,
    AuraKind.FROZEN: Element.CRYO,
}

SUCROSE_A4_MASTERY_RATIO = 0.2
SUCROSE_A4_DURATION_FRAMES = 8 * SUCROSE_TALENT_FRAMES_PER_SECOND
SUCROSE_A4_MECHANIC_KEY = f"{SUCROSE_PASSIVE_A4_HANDLER_KEY}.mastery"
SUCROSE_A4_BUFF_DEFINITION_KEY = f"{SUCROSE_PASSIVE_A4_HANDLER_KEY}.mastery.buff"
SUCROSE_A4_CONFLICT_KEY = f"{SUCROSE_PASSIVE_A4_HANDLER_KEY}.mastery.conflict"
SUCROSE_A4_MASTERY_TERM_KEY = f"{SUCROSE_PASSIVE_A4_HANDLER_KEY}.mastery.term"

# A4 触发面：命中敌人且攻击标签为元素战技 / 元素爆发（不区分哪一拍、哪一次命中；
# 爆发染色伤害同为「元素爆发」标签，风灵按拍输出故每拍覆盖刷新）。
SUCROSE_A4_TRIGGER_MAIN_ATTACK_TAGS = frozenset(
    {
        SUCROSE_ELEMENTAL_SKILL_MAIN_ATTACK_TAG,
        SUCROSE_ELEMENTAL_BURST_MAIN_ATTACK_TAG,
    }
)


# --- 魔女的前夜礼 --------------------------------------------
SUCROSE_WITCHES_EVE_DAMAGE_TAGS = frozenset(
    {
        "普通攻击1",
        "普通攻击2",
        "普通攻击3",
        "普通攻击4",
        "普通攻击5",
        "重击",
        "下落攻击",
        "元素战技",
        "元素爆发",
    }
)

SUCROSE_PASSIVE_WITCHES_EVE_HANDLER_KEY = "sucrose.passive.witches_eve_rite"

SUCROSE_WITCHES_EVE_SMALL_DURATION_FRAMES = 15 * SUCROSE_TALENT_FRAMES_PER_SECOND
SUCROSE_WITCHES_EVE_SMALL_BONUS = 0.0571428
SUCROSE_WITCHES_EVE_SMALL_MECHANIC_KEY = f"{SUCROSE_PASSIVE_WITCHES_EVE_HANDLER_KEY}.small"
SUCROSE_WITCHES_EVE_SMALL_BUFF_DEFINITION_KEY = f"{SUCROSE_WITCHES_EVE_SMALL_MECHANIC_KEY}.buff"
SUCROSE_WITCHES_EVE_SMALL_CONFLICT_KEY = f"{SUCROSE_WITCHES_EVE_SMALL_MECHANIC_KEY}.conflict"
SUCROSE_WITCHES_EVE_SMALL_TRIGGER_ABILITY_KEY = SUCROSE_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY

SUCROSE_WITCHES_EVE_LARGE_DURATION_FRAMES = 20 * SUCROSE_TALENT_FRAMES_PER_SECOND
SUCROSE_WITCHES_EVE_LARGE_BONUS = 0.0714285
SUCROSE_WITCHES_EVE_LARGE_MECHANIC_KEY = f"{SUCROSE_PASSIVE_WITCHES_EVE_HANDLER_KEY}.large"
SUCROSE_WITCHES_EVE_LARGE_BUFF_DEFINITION_KEY = f"{SUCROSE_WITCHES_EVE_LARGE_MECHANIC_KEY}.buff"
SUCROSE_WITCHES_EVE_LARGE_CONFLICT_KEY = f"{SUCROSE_WITCHES_EVE_LARGE_MECHANIC_KEY}.conflict"
SUCROSE_WITCHES_EVE_LARGE_TRIGGER_OBJECT_KEY = SUCROSE_SPIRIT_OBJECT_KEY

SUCROSE_WITCHES_EVE_AUDIT_TAG = "sucrose_witches_eve_rite"

# --- C6 魔导增强（+8.57142%） ---------------------------------------------
#
# C6 描述在 20% 之外另含一句「并使队伍中附近的魔导角色额外获得 8.57142% 的
# 对应元素伤害加成」。该句**不在资产库内**，故数值在内容侧以常量定义并使用。
SUCROSE_C6_MAGE_ENHANCEMENT_BONUS = 0.0857142
SUCROSE_C6_MAGE_ENHANCEMENT_MECHANIC_KEY = "sucrose.constellation.c6.mage_enhancement"
SUCROSE_C6_MAGE_ENHANCEMENT_BUFF_DEFINITION_KEY = f"{SUCROSE_C6_MAGE_ENHANCEMENT_MECHANIC_KEY}.buff"
SUCROSE_C6_MAGE_ENHANCEMENT_CONFLICT_KEY = f"{SUCROSE_C6_MAGE_ENHANCEMENT_MECHANIC_KEY}.conflict"


# --- 命座 -----------------------------------------------------------------

SUCROSE_CONSTELLATION_C1_HANDLER_KEY = "character.sucrose.constellation.c1"
SUCROSE_CONSTELLATION_C2_HANDLER_KEY = "character.sucrose.constellation.c2"
SUCROSE_CONSTELLATION_C3_HANDLER_KEY = "character.sucrose.constellation.c3"
SUCROSE_CONSTELLATION_C4_HANDLER_KEY = "character.sucrose.constellation.c4"
SUCROSE_CONSTELLATION_C5_HANDLER_KEY = "character.sucrose.constellation.c5"
SUCROSE_CONSTELLATION_C6_HANDLER_KEY = "character.sucrose.constellation.c6"

SUCROSE_C1_EXTRA_CHARGES = 1
SUCROSE_C2_EXTRA_SECONDS = 2
SUCROSE_C3_TALENT_BOOST = 3
SUCROSE_C5_TALENT_BOOST = 3
SUCROSE_TALENT_LEVEL_CAP = 15
SUCROSE_C4_TRIGGER_HIT_COUNT = 7
SUCROSE_C4_MIN_REDUCTION_SECONDS = 1
SUCROSE_C4_MAX_REDUCTION_SECONDS = 7
SUCROSE_C4_COUNT_INTERVAL_FRAMES = 6
SUCROSE_C4_TRIGGER_MAIN_ATTACK_TAGS = (
    "普通攻击1",
    "普通攻击2",
    "普通攻击3",
    "普通攻击4",
    "重击",
)
SUCROSE_C6_DAMAGE_BONUS = 0.2
SUCROSE_C6_TRIGGER_IMPACT_KEYS = (SUCROSE_SPIRIT_ABSORBED_TICK_IMPACT_KEY,)
SUCROSE_C6_MECHANIC_KEY = "sucrose.constellation.c6.elemental_damage_bonus"
SUCROSE_C6_BUFF_DEFINITION_KEY = f"{SUCROSE_C6_MECHANIC_KEY}.buff"
SUCROSE_C6_CONFLICT_KEY = f"{SUCROSE_C6_MECHANIC_KEY}.conflict"
SUCROSE_C6_AUDIT_TAG = "sucrose_constellation_c6"


# --- 动作表 ---------------------------------------------------------------

SUCROSE_ACTION_TABLE: dict[str, TimedActionSpec] = {
    SUCROSE_NORMAL_ATTACK_1_ACTION_KEY: TimedActionSpec(
        action_key=SUCROSE_NORMAL_ATTACK_1_ACTION_KEY,
        duration_frames=21,
        hit_frame=14,
        impact_key=SUCROSE_NORMAL_ATTACK_1_IMPACT_KEY,
        targeting=SUCROSE_TARGETING,
        transitions={NORMAL_ATTACK_INPUT: 21, CHARGED_ATTACK_INPUT: 2},
    ),
    SUCROSE_NORMAL_ATTACK_2_ACTION_KEY: TimedActionSpec(
        action_key=SUCROSE_NORMAL_ATTACK_2_ACTION_KEY,
        duration_frames=26,
        hit_frame=18,
        impact_key=SUCROSE_NORMAL_ATTACK_2_IMPACT_KEY,
        targeting=SUCROSE_TARGETING,
        transitions={NORMAL_ATTACK_INPUT: 26, CHARGED_ATTACK_INPUT: 4},
    ),
    SUCROSE_NORMAL_ATTACK_3_ACTION_KEY: TimedActionSpec(
        action_key=SUCROSE_NORMAL_ATTACK_3_ACTION_KEY,
        duration_frames=33,
        hit_frame=27,
        impact_key=SUCROSE_NORMAL_ATTACK_3_IMPACT_KEY,
        targeting=SUCROSE_TARGETING,
        transitions={NORMAL_ATTACK_INPUT: 33, CHARGED_ATTACK_INPUT: 16},
    ),
    SUCROSE_NORMAL_ATTACK_4_ACTION_KEY: TimedActionSpec(
        action_key=SUCROSE_NORMAL_ATTACK_4_ACTION_KEY,
        duration_frames=51,
        hit_frame=28,
        impact_key=SUCROSE_NORMAL_ATTACK_4_IMPACT_KEY,
        targeting=SUCROSE_TARGETING,
        transitions={NORMAL_ATTACK_INPUT: 51, CHARGED_ATTACK_INPUT: 42},
    ),
    SUCROSE_CHARGED_ATTACK_ACTION_KEY: TimedActionSpec(
        action_key=SUCROSE_CHARGED_ATTACK_ACTION_KEY,
        duration_frames=69,
        hit_frame=54,
        impact_key=SUCROSE_CHARGED_ATTACK_IMPACT_KEY,
        targeting=SUCROSE_TARGETING,
        transitions={
            NORMAL_ATTACK_INPUT: 69,
            CHARGED_ATTACK_INPUT: 66,
            ELEMENTAL_SKILL_INPUT: 60,
            ELEMENTAL_BURST_INPUT: 61,
            JUMP_INPUT: 53,
        },
    ),
    SUCROSE_ELEMENTAL_SKILL_ACTION_KEY: TimedActionSpec(
        action_key=SUCROSE_ELEMENTAL_SKILL_ACTION_KEY,
        duration_frames=57,
        hit_frame=SUCROSE_ELEMENTAL_SKILL_HIT_FRAME,
        impact_key=SUCROSE_ELEMENTAL_SKILL_IMPACT_KEY,
        targeting=SUCROSE_TARGETING,
        cooldown_start_frame=SUCROSE_ELEMENTAL_SKILL_COOLDOWN_START_FRAME,
        cooldown_ability_key=SUCROSE_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
        transitions={
            NORMAL_ATTACK_INPUT: 57,
            CHARGED_ATTACK_INPUT: 56,
            ELEMENTAL_SKILL_INPUT: 56,
            ELEMENTAL_BURST_INPUT: 57,
            JUMP_INPUT: 11,
        },
    ),
    SUCROSE_ELEMENTAL_BURST_ACTION_KEY: TimedActionSpec(
        action_key=SUCROSE_ELEMENTAL_BURST_ACTION_KEY,
        duration_frames=49,
        impact_points=(
            # 创建帧 17 生成大型风灵；能量花费帧 21 走 ENERGY spend_burst。
            # 两者都不索敌（非伤害影响点），伤害由风灵独立按拍产出。
            TimedImpactPointSpec(
                impact_key=SUCROSE_SPIRIT_CREATE_IMPACT_KEY,
                frame=SUCROSE_ELEMENTAL_BURST_CREATE_FRAME,
            ),
            TimedImpactPointSpec(
                impact_key=SUCROSE_ELEMENTAL_BURST_ENERGY_SPEND_IMPACT_KEY,
                frame=SUCROSE_ELEMENTAL_BURST_ENERGY_SPEND_FRAME,
            ),
        ),
        cooldown_start_frame=SUCROSE_ELEMENTAL_BURST_COOLDOWN_START_FRAME,
        cooldown_ability_key=SUCROSE_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY,
        transitions={
            NORMAL_ATTACK_INPUT: 49,
            CHARGED_ATTACK_INPUT: 48,
            ELEMENTAL_SKILL_INPUT: 48,
            JUMP_INPUT: 47,
        },
    ),
    SUCROSE_JUMP_ACTION_KEY: TimedActionSpec(
        action_key=SUCROSE_JUMP_ACTION_KEY,
        duration_frames=30,
        hit_frame=30,
        impact_key=SUCROSE_JUMP_IMPACT_KEY,
        targeting=TargetingSpec(radius=1.0),
        transitions={},
    ),
    SUCROSE_PLUNGE_ACTION_KEY: TimedActionSpec(
        action_key=SUCROSE_PLUNGE_ACTION_KEY,
        duration_frames=1,
        transitions={},
    ),
}
