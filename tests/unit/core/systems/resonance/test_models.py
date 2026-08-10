"""元素共鸣值对象与注册表测试。"""

from __future__ import annotations

import pytest

from genshin_sim.core.attributes import (
    STAT_ATK_TOTAL,
    ModifierStage,
)
from genshin_sim.core.elements import Element
from genshin_sim.core.systems.resonance import (
    ResonanceActivation,
    ResonanceDefinition,
    ResonanceDefinitionNotFoundError,
    ResonanceDefinitionRegistry,
    ResonanceRequirement,
    ResonanceRequirementKind,
    ResonanceStaticModifier,
    ResonanceValidationError,
    TeamElementComposition,
)


def test_element_count_requirement_validates_element_and_count():
    requirement = ResonanceRequirement.element_count(Element.PYRO)
    assert requirement.kind is ResonanceRequirementKind.ELEMENT_COUNT
    assert requirement.element is Element.PYRO
    assert requirement.count == 2

    with pytest.raises(ResonanceValidationError, match="非物理元素"):
        ResonanceRequirement.element_count(Element.PHYSICAL)
    with pytest.raises(ResonanceValidationError, match="不小于 2"):
        ResonanceRequirement.element_count(Element.PYRO, count=1)
    with pytest.raises(ResonanceValidationError, match="不能携带元素"):
        ResonanceRequirement(ResonanceRequirementKind.DISTINCT_ELEMENTS, Element.PYRO, 4)


def test_static_modifier_rejects_non_finite_value_and_bad_tags():
    modifier = ResonanceStaticModifier(
        STAT_ATK_TOTAL,
        ModifierStage.PERCENT_ADD,
        0.25,
        ("atk_percent",),
    )
    assert modifier.value == 0.25

    with pytest.raises(ResonanceValidationError, match="有限数字"):
        ResonanceStaticModifier(STAT_ATK_TOTAL, ModifierStage.PERCENT_ADD, float("nan"))
    with pytest.raises(ResonanceValidationError, match="非空字符串"):
        ResonanceStaticModifier(STAT_ATK_TOTAL, ModifierStage.PERCENT_ADD, 0.25, ("",))


def test_definition_rejects_duplicate_static_modifier_target():
    with pytest.raises(ResonanceValidationError, match="重复静态修饰"):
        ResonanceDefinition(
            "resonance.test",
            ResonanceRequirement.element_count(Element.PYRO),
            (
                ResonanceStaticModifier(STAT_ATK_TOTAL, ModifierStage.PERCENT_ADD, 0.1),
                ResonanceStaticModifier(STAT_ATK_TOTAL, ModifierStage.PERCENT_ADD, 0.2),
            ),
        )


def test_composition_filters_zero_counts_and_validates_invariants():
    composition = TeamElementComposition.from_counts(
        4,
        {Element.PYRO: 2, Element.HYDRO: 0, Element.GEO: 1},
    )
    assert composition.team_size == 4
    assert composition.element_counts == ((Element.GEO, 1), (Element.PYRO, 2))
    assert composition.element_count(Element.HYDRO) == 0
    assert composition.distinct_element_count == 2

    with pytest.raises(ResonanceValidationError, match="不能超过队伍人数"):
        TeamElementComposition.from_counts(3, {Element.PYRO: 4})
    with pytest.raises(ResonanceValidationError, match="只能包含七种元素"):
        TeamElementComposition.from_counts(4, {Element.PHYSICAL: 2})
    with pytest.raises(ResonanceValidationError, match="重复"):
        TeamElementComposition(4, ((Element.PYRO, 1), (Element.PYRO, 1)))


def test_activation_must_be_sorted_unique():
    assert ResonanceActivation(("resonance.hydro", "resonance.pyro")).active_keys == (
        "resonance.hydro",
        "resonance.pyro",
    )
    with pytest.raises(ResonanceValidationError, match="稳定排序"):
        ResonanceActivation(("resonance.pyro", "resonance.hydro"))
    with pytest.raises(ResonanceValidationError, match="重复"):
        ResonanceActivation(("resonance.pyro", "resonance.pyro"))
    assert ResonanceActivation.empty().is_empty


def test_registry_rejects_duplicates_and_missing_lookup():
    definition = ResonanceDefinition(
        "resonance.test",
        ResonanceRequirement.element_count(Element.PYRO),
    )
    registry = ResonanceDefinitionRegistry((definition,))
    assert registry.get("resonance.test") is definition
    assert registry.contains("resonance.test")
    with pytest.raises(ResonanceValidationError, match="重复共鸣定义"):
        registry.register(definition)
    with pytest.raises(ResonanceDefinitionNotFoundError, match="未知共鸣定义"):
        registry.get("resonance.missing")
