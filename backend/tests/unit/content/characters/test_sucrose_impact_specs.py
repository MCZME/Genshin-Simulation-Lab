"""砂糖命中契约编译的单元校验。

只验证「资产倍率行 + 命中数据 -> DamageImpactSpec」的形状与元素口径，
不重复覆盖倍率数值（合成倍率见 ``tests.helpers.sucrose``）。
"""

from __future__ import annotations

from genshin_sim.content.characters.mondstadt.sucrose.data import (
    SUCROSE_CHARGED_ATTACK_IMPACT_KEY,
    SUCROSE_DAMAGE_ELEMENT,
    SUCROSE_DAMAGE_ICD_SEQUENCE_KEY,
    SUCROSE_DAMAGE_ICD_TAG_KEY,
    SUCROSE_ELEMENTAL_SKILL_AOE_OFFSET,
    SUCROSE_ELEMENTAL_SKILL_AOE_RADIUS,
    SUCROSE_ELEMENTAL_SKILL_AOE_SHAPE,
    SUCROSE_ELEMENTAL_SKILL_IMPACT_KEY,
    SUCROSE_ELEMENTAL_SKILL_MAIN_ATTACK_TAG,
    SUCROSE_NORMAL_ATTACK_1_IMPACT_KEY,
    SUCROSE_NORMAL_ATTACK_ACTION_KEYS,
    SUCROSE_PLUNGE_COLLISION_IMPACT_KEY,
    SUCROSE_PLUNGE_LANDING_IMPACT_KEY,
)
from genshin_sim.content.characters.mondstadt.sucrose.impacts import (
    compile_charged_attack_damage_spec,
    compile_elemental_skill_damage_spec,
    compile_normal_attack_damage_specs,
    compile_plunge_damage_specs,
)
from genshin_sim.content.generic.plunge import PLUNGE_ATTACK_DATA_BY_WEAPON_TYPE
from genshin_sim.content.generic.talents import index_talent_scalings
from genshin_sim.core.elements import Element
from tests.helpers import sucrose as sucrose_helpers


def _entries():
    return index_talent_scalings(
        sucrose_helpers.SUCROSE_CHARACTER_KEY,
        sucrose_helpers.minimal_sucrose_scaling_entries(),
    )


def _character_key() -> str:
    return sucrose_helpers.SUCROSE_CHARACTER_KEY


def test_normal_attack_specs_carry_anemo_and_shared_icd():
    specs = compile_normal_attack_damage_specs(_character_key(), _entries(), 1)
    assert len(specs) == 4
    first = specs[SUCROSE_NORMAL_ATTACK_1_IMPACT_KEY]
    assert first.element is SUCROSE_DAMAGE_ELEMENT
    assert first.icd_tag_key == SUCROSE_DAMAGE_ICD_TAG_KEY
    assert first.icd_sequence_key == SUCROSE_DAMAGE_ICD_SEQUENCE_KEY
    assert not first.elemental_amount.is_zero
    assert [specs[key].display_name for key in specs] == [
        "一段伤害",
        "二段伤害",
        "三段伤害",
        "四段伤害",
    ]


def test_fourth_normal_attack_uses_wider_aoe_than_first():
    specs = compile_normal_attack_damage_specs(_character_key(), _entries(), 1)
    first = specs[SUCROSE_NORMAL_ATTACK_1_IMPACT_KEY]
    fourth = specs[f"{SUCROSE_NORMAL_ATTACK_ACTION_KEYS[3]}.hit"]
    assert first.area is not None and fourth.area is not None
    assert fourth.area.radius > first.area.radius


def test_charged_attack_spec_uses_oriented_box_and_no_icd():
    spec = compile_charged_attack_damage_spec(_character_key(), _entries(), 1)
    assert spec.impact_ref.startswith(SUCROSE_CHARGED_ATTACK_IMPACT_KEY)
    assert spec.main_attack_tag == "重击"
    assert spec.icd_tag_key is None
    assert spec.icd_sequence_key is None
    assert spec.area is not None
    assert spec.area.shape == "攻击盒"
    assert spec.area.length > 0 and spec.area.width > 0


def test_elemental_skill_spec_uses_cylinder_and_no_icd():
    spec = compile_elemental_skill_damage_spec(_character_key(), _entries(), 1)
    assert spec.impact_ref.startswith(SUCROSE_ELEMENTAL_SKILL_IMPACT_KEY)
    assert spec.main_attack_tag == SUCROSE_ELEMENTAL_SKILL_MAIN_ATTACK_TAG
    assert spec.element is SUCROSE_DAMAGE_ELEMENT
    assert not spec.elemental_amount.is_zero
    assert spec.icd_tag_key is None
    assert spec.icd_sequence_key is None
    assert spec.display_name == "技能伤害"
    assert spec.area is not None
    assert spec.area.shape == SUCROSE_ELEMENTAL_SKILL_AOE_SHAPE
    assert spec.area.radius == SUCROSE_ELEMENTAL_SKILL_AOE_RADIUS
    assert spec.area.local_offset_xz == SUCROSE_ELEMENTAL_SKILL_AOE_OFFSET


def test_plunge_specs_are_physical_and_follow_catalyst_generic_data():
    specs = compile_plunge_damage_specs(_character_key(), _entries(), 1)
    assert set(specs) == {
        SUCROSE_PLUNGE_COLLISION_IMPACT_KEY,
        f"{SUCROSE_PLUNGE_LANDING_IMPACT_KEY}.low",
        f"{SUCROSE_PLUNGE_LANDING_IMPACT_KEY}.high",
    }
    catalyst = PLUNGE_ATTACK_DATA_BY_WEAPON_TYPE["catalyst"]
    for spec in specs.values():
        assert spec.element is Element.PHYSICAL
        assert spec.elemental_strength is None
        assert spec.elemental_amount.is_zero
        assert spec.main_attack_tag == catalyst.main_attack_tag
    collision = specs[SUCROSE_PLUNGE_COLLISION_IMPACT_KEY]
    landing_low = specs[f"{SUCROSE_PLUNGE_LANDING_IMPACT_KEY}.low"]
    landing_high = specs[f"{SUCROSE_PLUNGE_LANDING_IMPACT_KEY}.high"]
    assert collision.area is not None and collision.area.radius == catalyst.collision.aoe_radius
    assert landing_low.area is not None
    assert landing_low.area.radius == catalyst.landing.low_aoe_radius
    assert landing_high.area is not None
    assert landing_high.area.radius == catalyst.landing.high_aoe_radius


def test_damage_bearing_hit_keys_all_have_compiled_specs():
    """所有「带伤害」的命中键都必须有编译契约，避免影响点静默不结算。

    跳跃命中点（``jump.hit``）**按设计不带伤害**（与芭芭拉同口径）：它只作为
    影响点存在、展开为无伤害请求，因此不在本断言范围内。
    """

    specs = {
        **compile_normal_attack_damage_specs(_character_key(), _entries(), 1),
        SUCROSE_CHARGED_ATTACK_IMPACT_KEY: compile_charged_attack_damage_spec(
            _character_key(), _entries(), 1
        ),
        SUCROSE_ELEMENTAL_SKILL_IMPACT_KEY: compile_elemental_skill_damage_spec(
            _character_key(), _entries(), 1
        ),
        **compile_plunge_damage_specs(_character_key(), _entries(), 1),
    }
    damage_bearing_keys = [
        SUCROSE_NORMAL_ATTACK_1_IMPACT_KEY,
        f"{SUCROSE_NORMAL_ATTACK_ACTION_KEYS[1]}.hit",
        f"{SUCROSE_NORMAL_ATTACK_ACTION_KEYS[2]}.hit",
        f"{SUCROSE_NORMAL_ATTACK_ACTION_KEYS[3]}.hit",
        SUCROSE_CHARGED_ATTACK_IMPACT_KEY,
        SUCROSE_ELEMENTAL_SKILL_IMPACT_KEY,
        SUCROSE_PLUNGE_COLLISION_IMPACT_KEY,
    ]
    for impact_key in damage_bearing_keys:
        assert impact_key in specs, impact_key
    assert f"{SUCROSE_PLUNGE_LANDING_IMPACT_KEY}.low" in specs
    assert f"{SUCROSE_PLUNGE_LANDING_IMPACT_KEY}.high" in specs
