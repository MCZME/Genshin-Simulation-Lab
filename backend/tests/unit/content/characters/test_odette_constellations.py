"""奥黛塔 C1–C5 效果行读数、效果单元工厂与雪鹄之梦编译的单元测试。

合成数值只验证行为与组件位映射（测试规范 §3.2），锁定：

- C1/C2/C4 三行效果行的组件位映射（追加段倍率 + 华彩强化 / 每层攻击力 + 减抗 /
  均摊比例 + 冷却 + 协同攻击两档倍率）与错位时的失败；
- C3/C5 的天赋等级提升与「至多 15 级」上限核对；
- C2 效果单元产出的两个变体减抗定义与判定 hook，C4 的协同攻击 hook；
- 雪鹄之梦的爆发倍率表读数（增伤随等级 + 持续秒数折算帧）与标记 Buff 定义。
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from genshin_sim.content.characters.snezhnaya.odette.data import (
    ODETTE_C2_CONDUCT_VARIANT,
    ODETTE_C2_SWIRL_VARIANT,
    ODETTE_CONSTELLATION_C1_HANDLER_KEY,
    ODETTE_CONSTELLATION_C2_HANDLER_KEY,
    ODETTE_CONSTELLATION_C3_HANDLER_KEY,
    ODETTE_CONSTELLATION_C4_HANDLER_KEY,
    ODETTE_CONSTELLATION_C5_HANDLER_KEY,
    odette_c2_resistance_definition_key,
    odette_swan_dream_definition_key,
)
from genshin_sim.content.characters.snezhnaya.odette.dream import (
    build_swan_dream_buff_definition,
    read_swan_dream_values,
)
from genshin_sim.content.characters.snezhnaya.odette.effects import (
    create_odette_constellation_c1,
    create_odette_constellation_c2,
    create_odette_constellation_c3,
    create_odette_constellation_c4,
    create_odette_constellation_c5,
    read_c1_asset_values,
    read_c2_asset_values,
    read_c4_asset_values,
    read_talent_level_boost,
)
from genshin_sim.content.characters.snezhnaya.odette.hooks import (
    OdetteC2ResistanceHook,
    OdetteC4CoordinatedAttackHook,
    compile_coordinated_attack_channel,
)
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.generic.talents import index_talent_scalings
from genshin_sim.core.attributes import (
    RESISTANCE_ANEMO,
    RESISTANCE_CRYO,
    RESISTANCE_ELECTRO,
    AttributeSubjectKind,
    ModifierStage,
)
from genshin_sim.core.elements import AuraAmount
from genshin_sim.core.systems.buff import BuffApplicationPolicy
from genshin_sim.core.systems.reaction.mechanics.stellar_conduct.keys import (
    STELLAR_CONDUCT_CRYO_DAMAGE_TAG,
)
from genshin_sim.core.systems.reaction.mechanics.stellar_swirl.keys import (
    STELLAR_SWIRL_ICE_DAMAGE_TAG,
)
from tests.helpers import odette as odette_helpers


def _params(values: tuple[float, ...]) -> dict[str, object]:
    """按合成资产效果行的组件结构把数值序列包装成 params（JSON 兼容形态）。"""

    return {
        "components": [
            {
                "source_param": f"number_{index}",
                "kind": "numeric",
                "format": "number",
                "values": [value],
            }
            for index, value in enumerate(values, start=1)
        ]
    }


def test_c1_reads_extra_segment_ratios_and_splendor_reinforcement() -> None:
    values = read_c1_asset_values(odette_helpers.odette_effect_params("c1"))
    assert values.conduct_ratio == pytest.approx(3.0)
    assert values.swirl_ratio == pytest.approx(4.0)
    assert values.extra_stacks == 2
    assert values.layers_per_tick == 2


def test_c1_missing_splendor_reinforcement_fails() -> None:
    # 追加段倍率之后的分量缺位必须在读数时失败，而不是让华彩强化静默取 0。
    with pytest.raises(ContentUnitValidationError):
        read_c1_asset_values(_params((1.0, 3.0, 4.0)))


def test_c2_reads_atk_per_stack_and_reduction() -> None:
    values = read_c2_asset_values(odette_helpers.odette_effect_params("c2"))
    assert values.atk_per_stack == pytest.approx(0.07)
    assert values.resistance_reduction == pytest.approx(0.2)


def test_c2_missing_reduction_fails() -> None:
    with pytest.raises(ContentUnitValidationError):
        read_c2_asset_values(_params((1.0, 0.07, 1.0, 1.0)))


def test_c4_reads_share_cooldown_and_ratios() -> None:
    values = read_c4_asset_values(odette_helpers.odette_effect_params("c4"))
    assert values.share_ratio == pytest.approx(0.5)
    # 3.5 秒按 60 帧/秒折算（gcsim 帧表的 210f 与之互证）。
    assert values.cooldown_frames == 210
    assert values.conduct_ratio == pytest.approx(0.66)
    assert values.swirl_ratio == pytest.approx(0.99)


def test_c4_legacy_component_layout_fails() -> None:
    # 旧合成行省掉了冷却秒数位：上限位缺位必须失败，而不是把 0.99 当成倍率。
    with pytest.raises(ContentUnitValidationError):
        read_c4_asset_values(_params((0.5, 0.66, 0.99)))


def test_talent_level_boost_reads_boost_and_cap() -> None:
    assert read_talent_level_boost(odette_helpers.odette_effect_params("c3")) == (3, 15)
    assert read_talent_level_boost(odette_helpers.odette_effect_params("c5")) == (3, 15)


def test_talent_level_boost_rejects_cap_mismatch() -> None:
    # 「至多提升至 N 级」与天赋框架上限不一致时显式失败，不静默按框架值截断。
    with pytest.raises(ContentUnitValidationError):
        read_talent_level_boost(_params((1.0, 3.0, 18.0)))


def test_c1_effect_unit_records_compiled_values() -> None:
    unit = create_odette_constellation_c1(
        odette_helpers.odette_effect_request(
            ODETTE_CONSTELLATION_C1_HANDLER_KEY,
            effect_key="character:odette_test:constellation:c1",
            params=odette_helpers.odette_effect_params("c1"),
        )
    )
    assert unit.compiled_params["conduct_ratio"] == pytest.approx(3.0)
    assert unit.compiled_params["swirl_ratio"] == pytest.approx(4.0)
    assert unit.compiled_params["extra_stacks"] == 2
    assert unit.compiled_params["layers_per_tick"] == 2


def test_c2_effect_unit_builds_two_variant_definitions_and_hook() -> None:
    unit = create_odette_constellation_c2(
        odette_helpers.odette_effect_request(
            ODETTE_CONSTELLATION_C2_HANDLER_KEY,
            effect_key="character:odette_test:constellation:c2",
            params=odette_helpers.odette_effect_params("c2"),
        )
    )
    definitions = {definition.definition_key: definition for definition in unit.buff_definitions}
    assert set(definitions) == {
        odette_c2_resistance_definition_key(1, ODETTE_C2_CONDUCT_VARIANT),
        odette_c2_resistance_definition_key(1, ODETTE_C2_SWIRL_VARIANT),
    }
    expected_elements = {
        ODETTE_C2_CONDUCT_VARIANT: (RESISTANCE_CRYO, RESISTANCE_ELECTRO),
        ODETTE_C2_SWIRL_VARIANT: (RESISTANCE_CRYO, RESISTANCE_ANEMO),
    }
    for variant, elements in expected_elements.items():
        definition = definitions[odette_c2_resistance_definition_key(1, variant)]
        assert definition.target_kinds == frozenset({AttributeSubjectKind.TARGET})
        assert definition.application_policy is BuffApplicationPolicy.REFRESH
        assert tuple(template.target_key for template in definition.attribute_modifiers) == elements
        assert all(
            template.stage is ModifierStage.FLAT_ADD for template in definition.attribute_modifiers
        )
    assert len(unit.event_hooks) == 1
    assert isinstance(unit.event_hooks[0], OdetteC2ResistanceHook)


def test_c3_and_c5_effect_units_contribute_talent_boosts() -> None:
    c3 = create_odette_constellation_c3(
        odette_helpers.odette_effect_request(
            ODETTE_CONSTELLATION_C3_HANDLER_KEY,
            effect_key="character:odette_test:constellation:c3",
            params=odette_helpers.odette_effect_params("c3"),
        )
    )
    c5 = create_odette_constellation_c5(
        odette_helpers.odette_effect_request(
            ODETTE_CONSTELLATION_C5_HANDLER_KEY,
            effect_key="character:odette_test:constellation:c5",
            params=odette_helpers.odette_effect_params("c5"),
        )
    )
    assert dict(c3.talent_level_boosts) == {"elemental_skill": 3}
    assert dict(c5.talent_level_boosts) == {"elemental_burst": 3}


def test_c4_effect_unit_hook_uses_row_cooldown_and_delay() -> None:
    unit = create_odette_constellation_c4(
        odette_helpers.odette_effect_request(
            ODETTE_CONSTELLATION_C4_HANDLER_KEY,
            effect_key="character:odette_test:constellation:c4",
            params=odette_helpers.odette_effect_params("c4"),
        )
    )
    hook = unit.event_hooks[0]
    assert isinstance(hook, OdetteC4CoordinatedAttackHook)
    assert hook.cooldown_frames == 210
    assert hook.delay_frames == 5
    assert set(hook.subscriptions) == {"DAMAGE_RESOLVED", "FRAME_STARTED"}


def test_coordinated_attack_channel_carries_variant_tags_and_ratios() -> None:
    channel = compile_coordinated_attack_channel(conduct_ratio=0.66, swirl_ratio=0.99)
    assert channel.conduct_spec.main_attack_tag == STELLAR_CONDUCT_CRYO_DAMAGE_TAG
    assert channel.swirl_spec.main_attack_tag == STELLAR_SWIRL_ICE_DAMAGE_TAG
    for spec in (channel.conduct_spec, channel.swirl_spec):
        # 星变体直伤：不附着（元素量 0）、单体（无 AOE）、无普通倍率。
        assert spec.elemental_amount == AuraAmount.zero()
        assert spec.area is None
        assert spec.scaling_terms == ()
    assert channel.conduct_ratio == pytest.approx(0.66)
    assert channel.swirl_ratio == pytest.approx(0.99)


def _burst_entries(*, bonus: float, duration: float):
    return index_talent_scalings(
        odette_helpers.ODETTE_CHARACTER_KEY,
        odette_helpers.minimal_odette_scaling_entries(
            ratio_overrides={
                "swan_dream_bonus": bonus,
                "swan_dream_duration": duration,
            }
        ),
    )


def test_swan_dream_values_read_from_burst_talent_table() -> None:
    entries = _burst_entries(bonus=0.25, duration=4.0)
    values = read_swan_dream_values(odette_helpers.ODETTE_CHARACTER_KEY, entries, 1)
    assert values.stellar_bonus == pytest.approx(0.25)
    # 4 秒按 60 帧/秒折算。
    assert values.duration_frames == 240


def test_swan_dream_requires_burst_entries() -> None:
    entries = {
        key: entry
        for key, entry in _burst_entries(bonus=0.25, duration=4.0).items()
        if key[2] != "雪鹄之梦持续时间"
    }
    with pytest.raises(ContentUnitValidationError):
        read_swan_dream_values(odette_helpers.ODETTE_CHARACTER_KEY, entries, 1)


def test_swan_dream_buff_definition_is_self_marker() -> None:
    definition = build_swan_dream_buff_definition(
        1,
        handler_key=odette_helpers.ODETTE_CHARACTER_HANDLER_KEY,
        display_name="雪鹄之梦",
    )
    assert definition.definition_key == odette_swan_dream_definition_key(1)
    assert definition.conflict_key == definition.definition_key
    assert definition.target_kinds == frozenset({AttributeSubjectKind.CHARACTER})
    assert definition.application_policy is BuffApplicationPolicy.REFRESH
    assert definition.marker_only is True


def test_effect_params_helper_rejects_unknown_row() -> None:
    with pytest.raises(AssertionError):
        odette_helpers.odette_effect_params("c99")


def test_effect_request_helper_defaults_to_c1_row() -> None:
    request = odette_helpers.odette_effect_request(
        ODETTE_CONSTELLATION_C1_HANDLER_KEY,
        effect_key="character:odette_test:constellation:c1",
    )
    params: Mapping[str, object] = request.params
    assert params["name"] == "合成命座1"
