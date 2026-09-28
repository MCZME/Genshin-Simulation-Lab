"""桑多涅内容单元编译的单元测试：伤害契约结构与冷却/状态接线。

帧表数值、AOE 尺寸与冷却时长是 data.py/资产侧的数据真值，此处不断言其
取值（测试规范 §3.3：内容数据本身不作断言目标）；只锁定命中判定数据行
映射为伤害契约的结构语义（标签、ICD 键与组别、单体/AOE 形态）与装配接线。
"""

from __future__ import annotations

from genshin_sim.content.characters.snezhnaya.sandrone.content import (
    create_sandrone_content_unit,
)
from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    SANDRONE_CHARACTER_HANDLER_KEY,
    SANDRONE_CHARGED_ATTACK_OVERLOAD_IMPACT_KEY,
    SANDRONE_CHARGED_ATTACK_RAY_IMPACT_KEY,
    SANDRONE_CHARGED_ATTACK_SWEEP_IMPACT_KEY,
    SANDRONE_CONTENT_VERSION,
    SANDRONE_ELEMENTAL_BURST_BEAM_IMPACT_KEY,
    SANDRONE_ELEMENTAL_SKILL_PRISM_1_IMPACT_KEY,
    SANDRONE_NORMAL_ATTACK_1_IMPACT_KEY,
    SANDRONE_NORMAL_ATTACK_2_IMPACT_KEY,
    SANDRONE_PLUNGE_COLLISION_IMPACT_KEY,
    SANDRONE_PLUNGE_LANDING_IMPACT_KEY,
)
from genshin_sim.content.generic.talents import index_talent_scalings
from genshin_sim.content.registries import CharacterContentUnitRequest
from genshin_sim.core.elements import Element
from genshin_sim.core.impacts import StrikeType
from tests.helpers import sandrone as sandrone_helpers


def _build_unit():
    return create_sandrone_content_unit(
        CharacterContentUnitRequest(
            handler_key=SANDRONE_CHARACTER_HANDLER_KEY,
            character_key=sandrone_helpers.SANDRONE_CHARACTER_KEY,
            slot=1,
            talent_levels={
                "normal_attack": 1,
                "elemental_skill": 1,
                "elemental_burst": 1,
            },
            talent_scalings=sandrone_helpers.minimal_sandrone_scaling_entries(),
        )
    )


def _damage_specs():
    from genshin_sim.content.characters.snezhnaya.sandrone.impacts import (
        compile_charged_attack_damage_specs,
        compile_elemental_burst_damage_specs,
        compile_elemental_skill_damage_specs,
        compile_normal_attack_damage_specs,
        compile_plunge_damage_specs,
    )

    character_key = sandrone_helpers.SANDRONE_CHARACTER_KEY
    entries_by_key = index_talent_scalings(
        character_key,
        sandrone_helpers.minimal_sandrone_scaling_entries(),
    )
    specs = compile_normal_attack_damage_specs(character_key, entries_by_key, 1)
    specs.update(compile_elemental_skill_damage_specs(character_key, entries_by_key, 1))
    specs.update(compile_elemental_burst_damage_specs(character_key, entries_by_key, 1))
    specs.update(compile_plunge_damage_specs(character_key, entries_by_key, 1))
    specs.update(compile_charged_attack_damage_specs(character_key, entries_by_key, 1))
    return specs


def test_content_unit_declares_version():
    assert _build_unit().version == SANDRONE_CONTENT_VERSION


def test_damage_specs_carry_hit_data_tags_and_icd():
    specs = _damage_specs()

    na1 = specs[SANDRONE_NORMAL_ATTACK_1_IMPACT_KEY]
    assert na1.main_attack_tag == "普通攻击1"
    assert na1.icd_tag_key == "普通攻击"
    assert na1.icd_sequence_key == "默认"
    assert na1.strike_type == StrikeType.BLUNT
    assert na1.range_type == "近战"
    assert na1.area is not None and na1.area.shape == "攻击盒"
    # 双手剑普攻未获转化时为物理，不携带附着证据。
    assert na1.element is Element.PHYSICAL
    assert na1.elemental_strength is None
    assert na1.elemental_amount.is_zero

    na2 = specs[SANDRONE_NORMAL_ATTACK_2_IMPACT_KEY]
    assert na2.area is not None and na2.area.shape == "圆柱"
    assert na2.element is Element.PHYSICAL

    prism = specs[SANDRONE_ELEMENTAL_SKILL_PRISM_1_IMPACT_KEY]
    assert prism.main_attack_tag == "元素战技"
    assert prism.icd_tag_key == "元素战技"
    assert prism.range_type == "远程"
    # 法洁欧系攻击按定案为冰元素（与物理近战对照）。
    assert prism.element is Element.CRYO
    assert prism.elemental_strength is not None

    beam = specs[SANDRONE_ELEMENTAL_BURST_BEAM_IMPACT_KEY]
    assert beam.main_attack_tag == "元素爆发"
    assert beam.icd_tag_key == "元素爆发"
    assert beam.element is Element.CRYO


def test_plunge_damage_specs_use_claymore_generic_data():
    specs = _damage_specs()

    collision = specs[SANDRONE_PLUNGE_COLLISION_IMPACT_KEY]
    assert collision.main_attack_tag == "下落攻击"
    assert collision.strike_type is StrikeType.SLASH
    assert collision.range_type == "近战"
    assert collision.elemental_amount.is_zero
    assert collision.area is not None and collision.area.shape == "球"
    # 双手剑下落未获转化时为物理，不携带附着证据（通用资料的元素量仅在
    # 攻击具元素时生效）。
    assert collision.element is Element.PHYSICAL
    assert collision.elemental_strength is None

    landing_low = specs[f"{SANDRONE_PLUNGE_LANDING_IMPACT_KEY}.low"]
    assert landing_low.strike_type is StrikeType.BLUNT
    assert landing_low.range_type == "近战"
    assert landing_low.area is not None and landing_low.area.shape == "圆柱"
    assert landing_low.element is Element.PHYSICAL
    assert landing_low.elemental_amount.is_zero

    landing_high = specs[f"{SANDRONE_PLUNGE_LANDING_IMPACT_KEY}.high"]
    assert landing_high.strike_type is StrikeType.BLUNT
    assert landing_high.area is not None and landing_high.area.shape == "圆柱"
    assert landing_high.element is Element.PHYSICAL


def test_charged_attack_specs_carry_hit_data_tags_and_icd():
    specs = _damage_specs()

    sweep = specs[SANDRONE_CHARGED_ATTACK_SWEEP_IMPACT_KEY]
    assert sweep.main_attack_tag == "重击"
    assert sweep.strike_type is StrikeType.DEFAULT
    assert sweep.range_type == "远程"
    assert sweep.area is None
    assert sweep.icd_tag_key == "桑多涅扫射攻击"
    assert sweep.icd_sequence_key == "桑多涅扫射攻击"

    overload = specs[SANDRONE_CHARGED_ATTACK_OVERLOAD_IMPACT_KEY]
    assert overload.icd_tag_key == "桑多涅扫射攻击"
    assert overload.icd_sequence_key == "桑多涅扫射攻击"

    ray = specs[SANDRONE_CHARGED_ATTACK_RAY_IMPACT_KEY]
    assert ray.main_attack_tag == "重击"
    assert ray.strike_type is StrikeType.BLUNT
    assert ray.area is None
    assert ray.icd_tag_key == "重击射线"
    assert ray.icd_sequence_key == "默认"
    assert ray.additional_attack_tags == ("桑多涅重击普通激光",)


def test_content_unit_declares_sweep_icd_and_fageou_schema():
    unit = _build_unit()

    definitions = unit.aura_icd_definitions
    assert len(definitions) == 1
    assert definitions[0].sequence_key == "桑多涅扫射攻击"

    schema = unit.state_schema
    assert schema is not None
    for name in (
        "fageou_mode",
        "fageou_power",
        "fageou_solve_start_frame",
        "fageou_next_shot_frame",
        "fageou_next_ray_frame",
        "fageou_drain_active",
        "fageou_last_particle_frame",
    ):
        assert schema.field(name) is not None
