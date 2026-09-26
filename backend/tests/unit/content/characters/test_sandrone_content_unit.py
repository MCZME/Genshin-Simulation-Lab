"""桑多涅内容单元编译的单元测试：帧表、伤害契约与冷却定义。"""

from __future__ import annotations

import pytest

from genshin_sim.content.characters.snezhnaya.sandrone.content import (
    create_sandrone_content_unit,
)
from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    SANDRONE_ACTION_TABLE,
    SANDRONE_CHARACTER_HANDLER_KEY,
    SANDRONE_CONTENT_VERSION,
    SANDRONE_ELEMENTAL_BURST_BEAM_IMPACT_KEY,
    SANDRONE_ELEMENTAL_BURST_BOMBARDMENT_1_IMPACT_KEY,
    SANDRONE_ELEMENTAL_SKILL_PRISM_1_IMPACT_KEY,
    SANDRONE_NORMAL_ATTACK_1_IMPACT_KEY,
    SANDRONE_NORMAL_ATTACK_2_IMPACT_KEY,
    SANDRONE_PLUNGE_COLLISION_IMPACT_KEY,
    SANDRONE_PLUNGE_LANDING_IMPACT_KEY,
)
from genshin_sim.content.generic.talents import index_talent_scalings
from genshin_sim.content.registries import CharacterContentUnitRequest
from genshin_sim.core.impacts import StrikeType
from genshin_sim.core.space import Vector3
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
            talent_scalings=sandrone_helpers._minimal_sandrone_scaling_entries(),
        )
    )


def test_content_unit_exposes_version_and_actions():
    unit = _build_unit()

    assert unit.version == SANDRONE_CONTENT_VERSION
    action_keys = {action.action_key for action in unit.actions}
    assert action_keys == set(SANDRONE_ACTION_TABLE)


@pytest.mark.parametrize(
    ("action_key", "duration_frames", "hit_frame"),
    (
        pytest.param(
            SANDRONE_ACTION_TABLE["character.sandrone.normal_attack.1"].action_key,
            130,
            44,
            id="na1",
        ),
        pytest.param(
            SANDRONE_ACTION_TABLE["character.sandrone.normal_attack.2"].action_key,
            59,
            24,
            id="na2",
        ),
        pytest.param(
            SANDRONE_ACTION_TABLE["character.sandrone.normal_attack.3"].action_key,
            159,
            50,
            id="na3",
        ),
    ),
)
def test_normal_attack_frame_table_matches_measured_data(
    action_key: str,
    duration_frames: int,
    hit_frame: int,
):
    spec = SANDRONE_ACTION_TABLE[action_key]

    assert spec.duration_frames == duration_frames
    assert spec.hit_frame == hit_frame


def test_damage_specs_carry_measured_tags_and_icd():
    from genshin_sim.content.characters.snezhnaya.sandrone.impacts import (
        compile_elemental_burst_damage_specs,
        compile_elemental_skill_damage_specs,
        compile_normal_attack_damage_specs,
    )

    character_key = sandrone_helpers.SANDRONE_CHARACTER_KEY
    entries_by_key = index_talent_scalings(
        character_key,
        sandrone_helpers._minimal_sandrone_scaling_entries(),
    )
    specs = compile_normal_attack_damage_specs(character_key, entries_by_key, 1)
    specs.update(compile_elemental_skill_damage_specs(character_key, entries_by_key, 1))
    specs.update(compile_elemental_burst_damage_specs(character_key, entries_by_key, 1))

    na1 = specs[SANDRONE_NORMAL_ATTACK_1_IMPACT_KEY]
    assert na1.main_attack_tag == "普通攻击1"
    assert na1.icd_tag_key == "普通攻击"
    assert na1.icd_sequence_key == "默认"
    assert na1.strike_type == StrikeType.BLUNT
    assert na1.range_type == "近战"
    assert na1.area is not None
    assert na1.area.shape == "攻击盒"
    assert na1.area.length == 4.3
    assert na1.area.width == 2.5
    assert na1.area.local_offset_xz == Vector3(0.0, 1.1, 0.5)

    na2 = specs[SANDRONE_NORMAL_ATTACK_2_IMPACT_KEY]
    assert na2.area is not None
    assert na2.area.shape == "圆柱"
    assert na2.area.radius == 2.7

    prism = specs[SANDRONE_ELEMENTAL_SKILL_PRISM_1_IMPACT_KEY]
    assert prism.main_attack_tag == "元素战技"
    assert prism.icd_tag_key == "元素战技"
    assert prism.range_type == "远程"

    beam = specs[SANDRONE_ELEMENTAL_BURST_BEAM_IMPACT_KEY]
    assert beam.main_attack_tag == "元素爆发"
    assert beam.icd_tag_key == "元素爆发"


def test_plunge_damage_specs_use_claymore_generic_data():
    from genshin_sim.content.characters.snezhnaya.sandrone.impacts import (
        compile_plunge_damage_specs,
    )

    character_key = sandrone_helpers.SANDRONE_CHARACTER_KEY
    entries_by_key = index_talent_scalings(
        character_key,
        sandrone_helpers._minimal_sandrone_scaling_entries(),
    )
    specs = compile_plunge_damage_specs(character_key, entries_by_key, 1)

    collision = specs[SANDRONE_PLUNGE_COLLISION_IMPACT_KEY]
    assert collision.main_attack_tag == "下落攻击"
    assert collision.strike_type is StrikeType.SLASH
    assert collision.range_type == "近战"
    assert collision.elemental_amount.is_zero
    assert collision.area is not None
    assert collision.area.shape == "球"
    assert collision.area.radius == 1.0
    assert collision.area.local_offset_xz == Vector3(0.0, 0.0, 1.0)

    landing_low = specs[f"{SANDRONE_PLUNGE_LANDING_IMPACT_KEY}.low"]
    assert landing_low.strike_type is StrikeType.BLUNT
    assert landing_low.range_type == "近战"
    assert landing_low.area is not None
    assert landing_low.area.shape == "圆柱"
    assert landing_low.area.radius == 3.0
    assert landing_low.area.local_offset_xz == Vector3(0.0, -0.5, 1.0)

    landing_high = specs[f"{SANDRONE_PLUNGE_LANDING_IMPACT_KEY}.high"]
    assert landing_high.strike_type is StrikeType.BLUNT
    assert landing_high.area is not None
    assert landing_high.area.shape == "圆柱"
    assert landing_high.area.radius == 5.0


def test_burst_registers_three_bombardment_points():
    unit = _build_unit()

    bombardment_keys = {
        key
        for key in unit.impact_factories
        if key.endswith(("bombardment_1", "bombardment_2", "bombardment_3"))
    }
    assert len(bombardment_keys) == 3
    assert SANDRONE_ELEMENTAL_BURST_BOMBARDMENT_1_IMPACT_KEY in bombardment_keys


def test_cooldown_definitions_match_asset_values():
    unit = _build_unit()

    durations = {
        definition.ability_kind.value: definition.base_duration_frames
        for definition in unit.cooldown_definitions
    }
    assert durations == {"elemental_skill": 240, "elemental_burst": 900}
