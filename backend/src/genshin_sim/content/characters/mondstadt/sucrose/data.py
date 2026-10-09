"""砂糖内容数据：稳定键、动作数据表与伤害数据。

数据与解释逻辑分离：``actions.py`` 只保留解释器与动作编译，``content.py``
只负责内容单元编译。本文件统一承载角色身份键（handler/action/impact）、
输入映射、帧表与动作表、普攻/重击/战技/爆发伤害数据、冷却/能量/产球常量、
大型风灵（创建物）与染色机制的实现基线常量，以及固有天赋（A1 / A4）的触发面
与 buff 常量；倍率仍来自资产库倍率表，不在本文件维护。

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
SUCROSE_ASSET_KEY = "character:10000043"
SUCROSE_CONTENT_VERSION = "dev-passives"

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
# 键用于请求识别与审计（奥黛塔舞步同款）。染色通道的风元素伤与染色伤害同帧、
# 共用同一目标集合。
SUCROSE_SPIRIT_ANEMO_TICK_IMPACT_KEY = f"{SUCROSE_CHARACTER_HANDLER_KEY}.spirit.anemo_tick"
SUCROSE_SPIRIT_ABSORBED_TICK_IMPACT_KEY = f"{SUCROSE_CHARACTER_HANDLER_KEY}.spirit.absorbed_tick"

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
    SUCROSE_SPIRIT_CREATE_IMPACT_KEY,
    SUCROSE_ELEMENTAL_BURST_ENERGY_SPEND_IMPACT_KEY,
)

# --- 输入映射 -------------------------------------------------------------

NORMAL_ATTACK_INPUT = "normal_attack"
CHARGED_ATTACK_INPUT = "charged_attack"
ELEMENTAL_SKILL_INPUT = "elemental_skill"
ELEMENTAL_BURST_INPUT = "elemental_burst"
JUMP_INPUT = "jump"

# S1 开放普攻 / 重击 / 跳跃；S2 加入元素战技；S3 加入元素爆发。
SUCROSE_INPUT_KIND_BY_KEY = {
    "mouse.left": NORMAL_ATTACK_INPUT,
    "mouse.right": CHARGED_ATTACK_INPUT,
    "keyboard.e": ELEMENTAL_SKILL_INPUT,
    "keyboard.q": ELEMENTAL_BURST_INPUT,
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


# --- 元素爆发伤害数据（维护者命中判定表，实施规划 §6.2 爆发两行） ----------
#
# 元素爆发本体不产生角色侧命中点：伤害由大型风灵创建物独立按拍产出
# （实施规划 §11.3）。两行（元素爆发 / 元素爆发染色）共用同一区域与攻击标签，
# 染色行不单独索敌（复用风伤的目标集合）。

SUCROSE_ELEMENTAL_BURST_CREATE_FRAME = 17
SUCROSE_ELEMENTAL_BURST_ENERGY_SPEND_FRAME = 21
SUCROSE_ELEMENTAL_BURST_MAIN_ATTACK_TAG = "元素爆发"
SUCROSE_ELEMENTAL_BURST_AOE_SHAPE = "圆柱"
SUCROSE_ELEMENTAL_BURST_AOE_RADIUS = 8.0
SUCROSE_ELEMENTAL_BURST_AOE_OFFSET = Vector3(0.0, -2.5, 0.0)

# --- 冷却（元素爆发） ------------------------------------------------------
#
# 冷却秒数取资产倍率条目「冷却时间」20s = 1200 帧；CD 起始帧取帧表「CD」列
# （§4.4）= 18，能量花费帧取「Energy」列 = 21。能量花费量（80）不在内容侧
# 维护，由角色资产的爆发能量花费承担。

SUCROSE_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY = "elemental_burst"
SUCROSE_ELEMENTAL_BURST_COOLDOWN_FRAMES = 1200
SUCROSE_ELEMENTAL_BURST_COOLDOWN_START_FRAME = 18

# --- 大型风灵（元素爆发创建物） --------------------------------------------
#
# 时序（实施规划 §11.3）：创建帧 17、每 120 帧一拍、共 3 拍（137 / 257 / 377）。
# 窗口时长取资产倍率条目「持续时间」6s = 360 帧（60fps）；创建物过期判据为
# ``frame < 创建帧 + 生命周期``（不含端点帧），而第三拍恰好落在窗口端点
# （创建帧 + 360），故生命周期取窗口 + 1 帧以容纳该拍——这是项目端点判据与
# 「第三拍落在窗末」的组合结果，不是新的时长取值。风灵与角色解耦：切人 /
# 离场后继续按拍输出。

SUCROSE_SPIRIT_OBJECT_KEY = "sucrose.large_wind_spirit"
SUCROSE_SPIRIT_ATTACK_SCHEDULE_KEY = "attack"
SUCROSE_SPIRIT_PROBE_SCHEDULE_KEY = "probe"
SUCROSE_SPIRIT_TICK_PERIOD_FRAMES = 120
SUCROSE_SPIRIT_TICK_COUNT = 3
SUCROSE_SPIRIT_WINDOW_FRAMES = 360
SUCROSE_SPIRIT_DURATION_FRAMES = SUCROSE_SPIRIT_WINDOW_FRAMES + 1

# --- 染色机制（判定区 / 节奏 / 优先级） ------------------------------------
#
# 判定区为长方体，尺寸按维护者数据的 ``(x, y, z) = (左右, 上下, 前后)`` 口径
# 接入：项目 X/Z 模型取「左右→width、前后→length」，上下分量被忽略（与攻击盒
# 命中行同口径）。判定区以风灵自身为原点、跟随风灵。
#
# 节奏：风灵存在期间每 18 帧（0.3s）重复探测，首次探到即固定（此后不再探测，
# 探测调度停机）。判定对象为判定区内**敌人**的元素附着；按 火 > 水 > 雷 > 冰
# 取靠前者，第 4 档兼容 CRYO 与 FROZEN 两种附着（均对应冰元素伤害）；不实现
# 资料给出的「抗火」探测逻辑（项目无抗元素），始终未探到则保持纯风伤。

SUCROSE_SPIRIT_PROBE_INTERVAL_FRAMES = 18
SUCROSE_SPIRIT_PROBE_BOX_LATERAL = 2.5  # x：左右
SUCROSE_SPIRIT_PROBE_BOX_VERTICAL = 5.0  # y：上下（X/Z 模型忽略）
SUCROSE_SPIRIT_PROBE_BOX_DEPTH = 2.5  # z：前后
SUCROSE_SPIRIT_PROBE_BOX_SHAPE = "攻击盒"
# 攻击盒不使用半径（投影为有向盒），按 D-076 区划口径取 0.0 占位。
SUCROSE_SPIRIT_PROBE_BOX_RADIUS = 0.0

SUCROSE_SPIRIT_ABSORPTION_PRIORITY = (
    (AuraKind.PYRO, Element.PYRO),
    (AuraKind.HYDRO, Element.HYDRO),
    (AuraKind.ELECTRO, Element.ELECTRO),
    (AuraKind.CRYO, Element.CRYO),
    (AuraKind.FROZEN, Element.CRYO),
)


# --- 固有天赋（实施规划 §11.5） --------------------------------------------
#
# A1「触媒置换术」：砂糖触发扩散 / 星扩散反应时，队伍中与被扩散元素同元素的
# 角色（不包括砂糖自己）元素精通 +50、持续 8s；按属性面板精通加成处理（作为
# 面板精通词条），数值取资产 ``passive:4`` 效果行 components（50 / 8）。
#
# A4「小小的慧风」：风灵作成·陆叁零捌（E）或禁·风灵作成·柒伍同构贰型（Q）
# 命中敌人时，基于**快照的**砂糖元素精通的 20%，为队伍中所有角色（不包括砂糖
# 自己）提供元素精通加成、持续 8s；数值取资产 ``passive:5`` 效果行 components
# （20% / 8）。A4 的产物是「基于属性折算」的转化效果，故产出修饰标
# ``reconvertible=False``（不可被二次转化，见属性系统契约 §11.4）。
#
# 两档 buff 均为覆盖刷新（重触发刷新时长、不叠数值），目标为**角色主体**逐个
# 投放（元素匹配在投放侧判定），因此不受队伍人数变化影响。

SUCROSE_PASSIVE_A1_HANDLER_KEY = "sucrose.passive.catalyst_conversion"
SUCROSE_PASSIVE_A4_HANDLER_KEY = "sucrose.passive.mollis_favonius"

SUCROSE_TALENT_FRAMES_PER_SECOND = 60

SUCROSE_A1_MASTERY_FLAT = 50.0
SUCROSE_A1_DURATION_FRAMES = 8 * SUCROSE_TALENT_FRAMES_PER_SECOND
SUCROSE_A1_MECHANIC_KEY = f"{SUCROSE_PASSIVE_A1_HANDLER_KEY}.mastery"
SUCROSE_A1_BUFF_DEFINITION_KEY = f"{SUCROSE_PASSIVE_A1_HANDLER_KEY}.mastery.buff"
SUCROSE_A1_CONFLICT_KEY = f"{SUCROSE_PASSIVE_A1_HANDLER_KEY}.mastery.conflict"
SUCROSE_A1_MASTERY_TERM_KEY = f"{SUCROSE_PASSIVE_A1_HANDLER_KEY}.mastery.term"

# A1 触发面：普通扩散与星扩散（实施规划 §8 第 3 项：含星扩散）。
SUCROSE_A1_TRIGGER_REACTION_KEYS = frozenset(
    {
        SWIRL_REACTION_KEY,
        STELLAR_SWIRL_REACTION_KEY,
    }
)

# 被扩散附着到元素伤害元素的映射：风元素不形成持久附着，故只覆盖四种可扩散
# 附着；FROZEN 与 S3 染色判定的第 4 档同口径，映射为冰元素。
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
