"""砂糖命中判定与染色机制 golden 基线。

验证能力：维护者命中判定表对砂糖四类伤害行的承载（普攻四段 / 重击 /
元素战技 / 元素爆发的区域形状与尺寸、元素量、衰减标签、索敌），以及大型
风灵染色机制的判定区、探测节奏与元素优先级。
资料来源及适用版本：维护者提供的命中判定表（实施规划 §6.2 / §6.3 /
§6.5）与染色判定区数据（§11.3 裁决，长方体 2.5×5.0×2.5、0.3s 重复探测、
顺序 火 > 水 > 雷 > 冰）；资料站 meropide.cn/en/characters/Sucrose
（纳塔 5.x 数据版本）。
完整输入条件：无常量输入——本文件冻结的是内容数据真值。
预期输出与允许误差：形状与标签逐字相等；尺寸浮点精确比较。
不覆盖的行为：命中判定的运行期消费（集成 / 系统测试承担）；倍率数值
（资产库承担，不进 golden）。
"""

from __future__ import annotations

from genshin_sim.content.characters.mondstadt.sucrose.data import (
    SUCROSE_CHARGED_ATTACK_AOE_LENGTH,
    SUCROSE_CHARGED_ATTACK_AOE_OFFSET,
    SUCROSE_CHARGED_ATTACK_AOE_WIDTH,
    SUCROSE_CHARGED_ATTACK_MAIN_ATTACK_TAG,
    SUCROSE_DAMAGE_ADDITIONAL_ATTACK_TAGS,
    SUCROSE_DAMAGE_AOE_SHAPE,
    SUCROSE_DAMAGE_ELEMENT,
    SUCROSE_DAMAGE_ICD_SEQUENCE_KEY,
    SUCROSE_DAMAGE_ICD_TAG_KEY,
    SUCROSE_DAMAGE_RANGE_TYPE,
    SUCROSE_DAMAGE_STRIKE_TYPE,
    SUCROSE_ELEMENTAL_BURST_AOE_RADIUS,
    SUCROSE_ELEMENTAL_BURST_MAIN_ATTACK_TAG,
    SUCROSE_ELEMENTAL_SKILL_AOE_RADIUS,
    SUCROSE_ELEMENTAL_SKILL_MAIN_ATTACK_TAG,
    SUCROSE_NORMAL_ATTACK_DAMAGE_DATA,
    SUCROSE_PARTICLE_COOLDOWN_FRAMES,
    SUCROSE_PARTICLE_COUNT,
    SUCROSE_PARTICLE_ELEMENT,
    SUCROSE_SPIRIT_ABSORPTION_PRIORITY,
    SUCROSE_SPIRIT_PROBE_BOX_DEPTH,
    SUCROSE_SPIRIT_PROBE_BOX_LATERAL,
    SUCROSE_SPIRIT_PROBE_BOX_VERTICAL,
    SUCROSE_SPIRIT_PROBE_INTERVAL_FRAMES,
    SUCROSE_TARGETING,
)


def test_normal_attack_hit_rows():
    """普攻四段：标签逐段、球形区域半径 1/1/1/2、无附加标签。"""

    assert [row.main_attack_tag for row in SUCROSE_NORMAL_ATTACK_DAMAGE_DATA] == [
        "普通攻击1",
        "普通攻击2",
        "普通攻击3",
        "普通攻击4",
    ]
    assert [row.aoe_radius for row in SUCROSE_NORMAL_ATTACK_DAMAGE_DATA] == [1.0, 1.0, 1.0, 2.0]
    assert all(row.aoe_offset is None for row in SUCROSE_NORMAL_ATTACK_DAMAGE_DATA)
    assert SUCROSE_DAMAGE_AOE_SHAPE == "球"
    assert SUCROSE_DAMAGE_ADDITIONAL_ATTACK_TAGS == ()


def test_charged_attack_hit_row():
    """重击：攻击盒 3.2×3.0、偏移 (0, 1.5, -0.2)、标签「重击」。"""

    assert SUCROSE_CHARGED_ATTACK_MAIN_ATTACK_TAG == "重击"
    assert SUCROSE_CHARGED_ATTACK_AOE_LENGTH == 3.2
    assert SUCROSE_CHARGED_ATTACK_AOE_WIDTH == 3.0
    offset = SUCROSE_CHARGED_ATTACK_AOE_OFFSET
    assert (offset.x, offset.y, offset.z) == (0.0, 1.5, -0.2)


def test_shared_damage_row_columns():
    """命中行公共列：风元素 / 默认打击类型 / 默认远近 / 1U（WEAK）/ 普攻 ICD。"""

    assert SUCROSE_DAMAGE_ELEMENT.value == "anemo"
    assert SUCROSE_DAMAGE_STRIKE_TYPE.value == "默认"
    assert SUCROSE_DAMAGE_RANGE_TYPE == "默认"
    assert SUCROSE_DAMAGE_ICD_TAG_KEY == "普通攻击"
    assert SUCROSE_DAMAGE_ICD_SEQUENCE_KEY == "默认"


def test_elemental_skill_and_burst_hit_rows():
    """战技圆柱半径 6；爆发圆柱半径 8；攻击标签各自独立。"""

    assert SUCROSE_ELEMENTAL_SKILL_MAIN_ATTACK_TAG == "元素战技"
    assert SUCROSE_ELEMENTAL_SKILL_AOE_RADIUS == 6.0
    assert SUCROSE_ELEMENTAL_BURST_MAIN_ATTACK_TAG == "元素爆发"
    assert SUCROSE_ELEMENTAL_BURST_AOE_RADIUS == 8.0


def test_targeting_spec():
    """索敌：圆柱 15,10 / 分数选择（全部伤害行共用）。"""

    search_area = SUCROSE_TARGETING.search_area
    assert search_area is not None
    assert search_area.shape == "圆柱"
    assert search_area.radius == 15.0
    assert search_area.height == 10.0
    assert SUCROSE_TARGETING.selection_policy_key == "分数"


def test_particle_spawn_values():
    """产球：战技命中产 4 风微粒，判定冷却 0.4s = 24 帧（§6.5）。"""

    assert SUCROSE_PARTICLE_ELEMENT.value == "anemo"
    assert SUCROSE_PARTICLE_COUNT == 4
    assert SUCROSE_PARTICLE_COOLDOWN_FRAMES == 24


def test_absorption_probe_and_priority():
    """染色判定区 2.5×5.0×2.5、探测间隔 18 帧（0.3s）、优先级 火>水>雷>冰。"""

    assert SUCROSE_SPIRIT_PROBE_BOX_LATERAL == 2.5
    assert SUCROSE_SPIRIT_PROBE_BOX_VERTICAL == 5.0
    assert SUCROSE_SPIRIT_PROBE_BOX_DEPTH == 2.5
    assert SUCROSE_SPIRIT_PROBE_INTERVAL_FRAMES == 18
    assert [(kind.name, element.value) for kind, element in SUCROSE_SPIRIT_ABSORPTION_PRIORITY] == [
        ("PYRO", "pyro"),
        ("HYDRO", "hydro"),
        ("ELECTRO", "electro"),
        ("CRYO", "cryo"),
        ("FROZEN", "cryo"),
    ]
