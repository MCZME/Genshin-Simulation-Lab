"""砂糖内容数据：稳定键、动作数据表与伤害数据。

数据与解释逻辑分离：``actions.py`` 只保留解释器与动作编译，``content.py``
只负责内容单元编译。本文件统一承载角色身份键（handler/action/impact）、
输入映射、帧表与动作表、普攻/重击/战技伤害数据与冷却/产球常量；倍率仍来自
资产库倍率表，不在本文件维护。

**命名口径**：稳定键沿用官方英文名称（资料站 meropide.cn/en/characters/Sucrose）：

- 普通攻击（含重击、下落攻击）``Wind Spirit Creation``
- 元素战技 ``Astable Anemohypostasis Creation - 6308``
- 元素爆发 ``Forbidden Creation - Isomer 75 / Type II``
- 固有天赋 ``Catalyst Conversion``（A1）/ ``Mollis Favonius``（A4）
- 额外天赋 ``Witch's Eve Rite: Sevenfold Transmutation``（魔导）
- 命座 ``Clustered Vacuum Field`` … ``Chaotic Entropy``（C1–C6）

**帧表来源**：维护者提供的数据（实施规划 §4.4，60fps），KQM 抓取值仅作
交叉参考、不作为取数来源；两者 6 处不一致一律取维护者数据。

**伤害标签**沿用项目中文攻击标签口径（D-076：角色攻击标签为中文）。
"""

from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.content.generic.timed_action import TimedActionSpec
from genshin_sim.core.actions import SearchAreaSpec, TargetingSpec
from genshin_sim.core.elements import AuraAmount, Element
from genshin_sim.core.impacts import StrikeType
from genshin_sim.core.space import Vector3
from genshin_sim.core.systems.aura import AuraStrength

SUCROSE_CHARACTER_HANDLER_KEY = "character.sucrose"
SUCROSE_ASSET_KEY = "character:10000043"
SUCROSE_CONTENT_VERSION = "dev-elemental-skill"

SUCROSE_JUMP_ACTION_KEY = "character.sucrose.jump"
SUCROSE_PLUNGE_ACTION_KEY = "character.sucrose.plunge"

# --- 动作键（官方技能名罗马化，逐段/变体加后缀） ---------------------------

SUCROSE_NORMAL_ATTACK_1_ACTION_KEY = "character.sucrose.wind_spirit_creation.1"
SUCROSE_NORMAL_ATTACK_2_ACTION_KEY = "character.sucrose.wind_spirit_creation.2"
SUCROSE_NORMAL_ATTACK_3_ACTION_KEY = "character.sucrose.wind_spirit_creation.3"
SUCROSE_NORMAL_ATTACK_4_ACTION_KEY = "character.sucrose.wind_spirit_creation.4"
SUCROSE_CHARGED_ATTACK_ACTION_KEY = "character.sucrose.wind_spirit_creation.charged"

# 元素战技 / 元素爆发动作在 S2 / S3 接入；键先固定，避免后续重命名。
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
SUCROSE_ELEMENTAL_BURST_IMPACT_KEY = f"{SUCROSE_ELEMENTAL_BURST_ACTION_KEY}.hit"
SUCROSE_JUMP_IMPACT_KEY = f"{SUCROSE_JUMP_ACTION_KEY}.hit"
SUCROSE_PLUNGE_COLLISION_IMPACT_KEY = f"{SUCROSE_PLUNGE_ACTION_KEY}.collision"
SUCROSE_PLUNGE_LANDING_IMPACT_KEY = f"{SUCROSE_PLUNGE_ACTION_KEY}.landing"

# 产球请求的影响键：请求不是动作影响点产出，而是由产球 hook 产出；键用于
# 请求识别与审计匹配（奥黛塔同款）。
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
)

# --- 输入映射 -------------------------------------------------------------

NORMAL_ATTACK_INPUT = "normal_attack"
CHARGED_ATTACK_INPUT = "charged_attack"
ELEMENTAL_SKILL_INPUT = "elemental_skill"
ELEMENTAL_BURST_INPUT = "elemental_burst"
JUMP_INPUT = "jump"

# S1 开放普攻 / 重击 / 跳跃；S2 加入元素战技；元素爆发输入在 S3 接入后加入。
SUCROSE_INPUT_KIND_BY_KEY = {
    "mouse.left": NORMAL_ATTACK_INPUT,
    "mouse.right": CHARGED_ATTACK_INPUT,
    "keyboard.e": ELEMENTAL_SKILL_INPUT,
    "keyboard.space": JUMP_INPUT,
}

# --- 伤害稳定数据（维护者命中判定表，实施规划 §6.2） -----------------------

SUCROSE_DAMAGE_ELEMENT = Element.ANEMO
SUCROSE_DAMAGE_ADDITIONAL_ATTACK_TAGS = ()
SUCROSE_DAMAGE_STRIKE_TYPE = StrikeType.DEFAULT
SUCROSE_DAMAGE_RANGE_TYPE = "默认"
# 1U 取 WEAK 档位，与芭芭拉的 1U 行一致（实施规划 §6.3 保留了该取值的确认需求）。
SUCROSE_DAMAGE_ELEMENTAL_STRENGTH = AuraStrength.WEAK
SUCROSE_DAMAGE_ELEMENTAL_AMOUNT = AuraAmount.one()
SUCROSE_DAMAGE_ICD_SEQUENCE_KEY = "默认"
SUCROSE_DAMAGE_ICD_TAG_KEY = "普通攻击"
SUCROSE_DAMAGE_AOE_SHAPE = "球"

SUCROSE_CHARGED_ATTACK_MAIN_ATTACK_TAG = "重击"
SUCROSE_CHARGED_ATTACK_AOE_SHAPE = "攻击盒"
# 攻击盒形状不使用半径（投影为有向盒），按 D-076 区划口径取 0.0 占位。
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


# --- 元素战技伤害数据（维护者命中判定表，实施规划 §6.2 元素战技行） --------
#
# 战技不引入创建物（牵引与吸附不实现，实施规划 §11.2）：退化为单次范围风伤，
# 区域锚定砂糖自身 XZ、半径 6，元素量 1U、无 ICD（衰减列为「—」，不写 ICD
# 键即为逐次独立附着）；命中帧 42 取帧表 §4.4。

SUCROSE_ELEMENTAL_SKILL_HIT_FRAME = 42
SUCROSE_ELEMENTAL_SKILL_MAIN_ATTACK_TAG = "元素战技"
SUCROSE_ELEMENTAL_SKILL_AOE_SHAPE = "圆柱"
SUCROSE_ELEMENTAL_SKILL_AOE_RADIUS = 6.0
SUCROSE_ELEMENTAL_SKILL_AOE_OFFSET = Vector3(0.0, -3.0, 0.0)

# --- 冷却（元素战技） ------------------------------------------------------
#
# 帧制为 60 帧/秒；冷却秒数取资产倍率条目「技能冷却时间」15s = 900 帧，常量
# 随帧表维护（奥黛塔 / 芭芭拉先例）。CD 起始帧取帧表「CD」列（§4.4）= 9。

SUCROSE_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY = "elemental_skill"
SUCROSE_ELEMENTAL_SKILL_COOLDOWN_FRAMES = 900
SUCROSE_ELEMENTAL_SKILL_COOLDOWN_START_FRAME = 9

# --- 产球（维护者提供的角色产球表，实施规划 §6.5） -------------------------
#
# 战技技能伤害命中触发：4 风微粒 / 100% / 判定冷却 0.4s = 24 帧（时间窗去重，
# 等价于一次战技只产一次球）。概率 100%：无分布可选，不消费 ``RandomSource``
# （与 C4 的随机减冷却不同，后者才涉及随机源）。触发面为战技命中影响点；
# 「元素战技（对己方非角色单位）」行本期不实现（§6.3），不涉及产球。

SUCROSE_PARTICLE_TRIGGER_IMPACT_KEYS = (SUCROSE_ELEMENTAL_SKILL_IMPACT_KEY,)
SUCROSE_PARTICLE_ELEMENT = Element.ANEMO
SUCROSE_PARTICLE_COUNT = 4
SUCROSE_PARTICLE_COOLDOWN_FRAMES = 24
# 微粒载体飞行延迟：资料未给，沿用奥黛塔 / 桑多涅同款占位值（30 帧）。
SUCROSE_PARTICLE_TRAVEL_FRAMES = 30
# 产球审计字段：最近一次产球的命中结算帧（0 = 尚未产球）。
SUCROSE_STATE_LAST_PARTICLE_FRAME = "sucrose_last_particle_frame"


# --- 动作表（帧表来源：实施规划 §4.4） ------------------------------------
#
# duration_frames 取该行「普攻」列（动作自然结束帧）；transitions 取各输入列
# 的「最早衔接帧」（相对本动作起始帧的偏移），「×」不写入（查无条目即终局
# 拒绝）。「闪避 / 走 / 切人」列不由角色解释器消费，故不落入 transitions。

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
