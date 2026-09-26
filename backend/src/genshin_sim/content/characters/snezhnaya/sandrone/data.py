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
SANDRONE_CONTENT_VERSION = "slice-3-stellar-channel"

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

# ---------------------------------------------------------------------------
# 法洁欧与解算模式（切片 2）。
# 机器参数来源：米游社 @Asgater 攻略实测约值（3.6，约值即基线）+ 维护者
# 30fps 视频帧表定稿（3.9.2，节奏以 0.35s/1.1s 为权威）。帧制为 60 帧/秒。
# ---------------------------------------------------------------------------
SANDRONE_CHARGED_ATTACK_ACTION_KEY = "character.sandrone.charged_attack"
SANDRONE_CHARGED_ATTACK_SWEEP_IMPACT_KEY = f"{SANDRONE_CHARGED_ATTACK_ACTION_KEY}.sweep"
SANDRONE_CHARGED_ATTACK_OVERLOAD_IMPACT_KEY = f"{SANDRONE_CHARGED_ATTACK_ACTION_KEY}.overload"
SANDRONE_CHARGED_ATTACK_RAY_IMPACT_KEY = f"{SANDRONE_CHARGED_ATTACK_ACTION_KEY}.ray"

# 法洁欧内容状态字段（state_key = handler key，与连段状态同挂载）。
FAGEOU_STATE_MODE = "fageou_mode"
FAGEOU_STATE_POWER = "fageou_power"
FAGEOU_STATE_SOLVE_START_FRAME = "fageou_solve_start_frame"
FAGEOU_STATE_NEXT_SHOT_FRAME = "fageou_next_shot_frame"
FAGEOU_STATE_NEXT_RAY_FRAME = "fageou_next_ray_frame"
FAGEOU_STATE_DRAIN_ACTIVE = "fageou_drain_active"

FAGEOU_MODE_IDLE = "idle"
FAGEOU_MODE_SOLVE = "solve"
FAGEOU_MODE_OVERLOAD = "overload"
FAGEOU_MODES = (FAGEOU_MODE_IDLE, FAGEOU_MODE_SOLVE, FAGEOU_MODE_OVERLOAD)

# 前摇 36F（按下→首颗子弹/进入解算）；功率自解算起算（solve_start）。
FAGEOU_PRE_SWING_FRAMES = 36
# 射击轨：解算 0.35s（21F）、过载 0.5s（30F），换节奏不重置相位
# （进入过载后首发射击 = 过载起点 +30F）。
FAGEOU_SOLVE_SHOT_INTERVAL_FRAMES = 21
FAGEOU_OVERLOAD_SHOT_INTERVAL_FRAMES = 30
# 射线轨：解算起算 +90F 首法、间隔 66F（1.1s）；次数由功率动力学涌现。
FAGEOU_RAY_FIRST_OFFSET_FRAMES = 90
FAGEOU_RAY_INTERVAL_FRAMES = 66
# 功率动力学：上升 20/s、射线命中 +12、场上衰减 5.5/s、后台 ×3（文本 300%）、
# E 排空 ≈200/s（约 0.5s 排满 100）；过载退出阈值 50；上限 100。
FAGEOU_POWER_RISE_PER_SECOND = 20.0
FAGEOU_RAY_HIT_POWER_GAIN = 12.0
FAGEOU_POWER_DECAY_PER_SECOND = 5.5
FAGEOU_BENCH_DECAY_MULTIPLIER = 3.0
FAGEOU_DRAIN_PER_SECOND = 200.0
FAGEOU_OVERLOAD_EXIT_POWER = 50.0
FAGEOU_POWER_MAX = 100.0

# 直线几何：瞄准方向 = 桑多涅实体 facing（静态），出发点 = 桑多涅位置
# （偏移 0，法洁欧同位）。射线为 oriented box 穿透（即时结算）；子弹取直线
# 首个交点（单一实例），延迟按距离折算。子弹速度 60 m/s 为无来源占位。
FAGEOU_RAY_LENGTH = 12.0
FAGEOU_RAY_WIDTH = 1.0
FAGEOU_BULLET_SPEED_M_PER_S = 60.0

# 命中判定数据（3.4 重击三行，单体 = 每实例无 AOE 形状，命中集合由直线
# 几何确定）。扫射与功率过载共用自定义 ICD 组「桑多涅扫射攻击」
# （重置 1.4s = 84F、序列 (1,0)，扫射/过载游标共享）。
SANDRONE_SWEEP_ICD_SEQUENCE_KEY = "桑多涅扫射攻击"
SANDRONE_SWEEP_ICD_RESET_FRAMES = 84
SANDRONE_CHARGED_ATTACK_MAIN_TAG = "重击"
SANDRONE_RAY_ICD_TAG_KEY = "重击射线"
SANDRONE_RAY_ADDITIONAL_TAG = "桑多涅重击普通激光"


@dataclass(frozen=True, slots=True)
class SandroneChargedAttackDamageData:
    """重击单类攻击的伤害数据（扫射/过载/射线，普通变体）。"""

    impact_key: str
    strike_type: StrikeType
    range_type: str
    icd_tag_key: str
    icd_sequence_key: str
    additional_attack_tags: tuple[str, ...] = ()


SANDRONE_CHARGED_ATTACK_DAMAGE_DATA = {
    SANDRONE_CHARGED_ATTACK_SWEEP_IMPACT_KEY: SandroneChargedAttackDamageData(
        impact_key=SANDRONE_CHARGED_ATTACK_SWEEP_IMPACT_KEY,
        strike_type=StrikeType.DEFAULT,
        range_type="远程",
        icd_tag_key=SANDRONE_SWEEP_ICD_SEQUENCE_KEY,
        icd_sequence_key=SANDRONE_SWEEP_ICD_SEQUENCE_KEY,
    ),
    SANDRONE_CHARGED_ATTACK_OVERLOAD_IMPACT_KEY: SandroneChargedAttackDamageData(
        impact_key=SANDRONE_CHARGED_ATTACK_OVERLOAD_IMPACT_KEY,
        strike_type=StrikeType.DEFAULT,
        range_type="远程",
        icd_tag_key=SANDRONE_SWEEP_ICD_SEQUENCE_KEY,
        icd_sequence_key=SANDRONE_SWEEP_ICD_SEQUENCE_KEY,
    ),
    SANDRONE_CHARGED_ATTACK_RAY_IMPACT_KEY: SandroneChargedAttackDamageData(
        impact_key=SANDRONE_CHARGED_ATTACK_RAY_IMPACT_KEY,
        strike_type=StrikeType.BLUNT,
        range_type="远程",
        icd_tag_key=SANDRONE_RAY_ICD_TAG_KEY,
        icd_sequence_key=SANDRONE_DAMAGE_ICD_SEQUENCE_KEY,
        additional_attack_tags=(SANDRONE_RAY_ADDITIONAL_TAG,),
    ),
}

# ---- 辉映·星烁直伤分支（切片 3）----
# 冷凝射线/第二枚棱晶弹/聚能光束在辉映状态下切换到星烁通道（星超导反应契约
# §8、命中判定数据 3.4 星变体行）。星变体：攻击标签 星超导冰/星扩散冰、元素量
# 0、无衰减序列与衰减标签（不参与附着判定）；显示名取资产倍率条目同名行。
# 星扩散变体无资产倍率条目（原始源数据 0 处提及），数值与显示名以编译参数
# 占位、来源待补（规划讨论待定项 6）；星扩散触发前提（capability 角色）接入
# 前该分支不会被激活。
SANDRONE_STELLAR_RAY_CONDUCT_LABEL = "重击冷凝射线星超导伤害"
SANDRONE_STELLAR_PRISM_CONDUCT_LABEL = "棱晶弹星超导伤害"
SANDRONE_STELLAR_BEAM_CONDUCT_LABEL = "聚能光束星超导伤害"
SANDRONE_STELLAR_RAY_SWIRL_DISPLAY_NAME = "重击冷凝射线星扩散伤害"
SANDRONE_STELLAR_PRISM_SWIRL_DISPLAY_NAME = "棱晶弹星扩散伤害"
SANDRONE_STELLAR_BEAM_SWIRL_DISPLAY_NAME = "聚能光束星扩散伤害"
SANDRONE_RAY_STELLAR_ADDITIONAL_TAG = "桑多涅激光"
SANDRONE_PRISM_STELLAR_ADDITIONAL_TAG = "桑多涅战技星烁"


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
