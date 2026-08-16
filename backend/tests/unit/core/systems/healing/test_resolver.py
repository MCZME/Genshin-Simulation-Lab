from __future__ import annotations

from typing import Any, cast

import pytest

from genshin_sim.core.attributes import (
    BONUS_HEALING_INCOMING,
    BONUS_HEALING_OUTGOING,
    STAT_ATK_BASE,
    STAT_ATK_TOTAL,
    STAT_HP_BASE,
    STAT_HP_MAX,
    AttributeResolver,
    AttributeSubjectRef,
    BaseAttributeContribution,
    BaseAttributeSet,
    ModifierProviderIndex,
    RuntimeSourceKind,
    RuntimeSourceRef,
    UnsupportedOwnerError,
    create_public_attribute_registry,
)
from genshin_sim.core.systems.healing import (
    HealingRequest,
    HealingResolver,
    HealingScalingTerm,
    InvalidHealingAttributeError,
    InvalidHealingResultError,
)

SOURCE_REF = AttributeSubjectRef.character("character:slot_1")
TARGET_REF = AttributeSubjectRef.character("character:slot_2")
CONFIG_SOURCE = RuntimeSourceRef(RuntimeSourceKind.CONFIG, "test.healing")


def _attribute_resolver(
    *,
    source_hp: float = 10000.0,
    source_atk: float = 500.0,
    target_hp: float = 1000.0,
    outgoing_bonus: float = 0.0,
    incoming_bonus: float = 0.0,
) -> AttributeResolver:
    registry = create_public_attribute_registry()
    return AttributeResolver(
        definitions=registry,
        base_attributes=BaseAttributeSet(
            (
                (
                    SOURCE_REF,
                    BaseAttributeContribution(STAT_HP_BASE, source_hp, CONFIG_SOURCE),
                ),
                (
                    SOURCE_REF,
                    BaseAttributeContribution(STAT_ATK_BASE, source_atk, CONFIG_SOURCE),
                ),
                (
                    SOURCE_REF,
                    BaseAttributeContribution(
                        BONUS_HEALING_OUTGOING,
                        outgoing_bonus,
                        CONFIG_SOURCE,
                    ),
                ),
                (
                    TARGET_REF,
                    BaseAttributeContribution(STAT_HP_BASE, target_hp, CONFIG_SOURCE),
                ),
                (
                    TARGET_REF,
                    BaseAttributeContribution(
                        BONUS_HEALING_INCOMING,
                        incoming_bonus,
                        CONFIG_SOURCE,
                    ),
                ),
            )
        ),
        modifier_index=ModifierProviderIndex((), registry=registry),
    )


def _request(
    *,
    scaling_terms: tuple[HealingScalingTerm, ...] | None = None,
    flat_healing: float = 0.0,
) -> HealingRequest:
    if scaling_terms is None:
        scaling_terms = (HealingScalingTerm("hp", STAT_HP_MAX, 0.1),)
    return HealingRequest(
        healing_id="healing:test:1",
        frame=8,
        source_ref=SOURCE_REF,
        target_ref=TARGET_REF,
        scaling_terms=scaling_terms,
        flat_healing=flat_healing,
        source_context=CONFIG_SOURCE,
        tags=frozenset({"test_heal"}),
    )


def test_resolver_calculates_multiple_components_flat_and_additive_bonus_multiplier():
    resolver = HealingResolver(
        _attribute_resolver(outgoing_bonus=0.2, incoming_bonus=0.3),
    )
    request = _request(
        scaling_terms=(
            HealingScalingTerm("hp", STAT_HP_MAX, 0.1),
            HealingScalingTerm("atk", STAT_ATK_TOTAL, 2.0),
        ),
        flat_healing=100,
    )

    result = resolver.resolve(request)

    component_values = [
        (component.component_key, component.value) for component in result.component_results
    ]
    assert component_values == [
        ("hp", 1000.0),
        ("atk", 1000.0),
    ]
    assert result.base_healing == 2100.0
    assert result.healing_bonus_multiplier == 1.5
    assert result.final_healing == pytest.approx(3150.0)
    assert result.source_context == CONFIG_SOURCE
    assert result.tags == frozenset({"test_heal"})


def test_resolver_audits_same_attribute_as_separate_components():
    resolver = HealingResolver(_attribute_resolver())
    result = resolver.resolve(
        _request(
            scaling_terms=(
                HealingScalingTerm("hp_primary", STAT_HP_MAX, 0.1),
                HealingScalingTerm("hp_secondary", STAT_HP_MAX, 0.05),
            )
        )
    )

    assert [component.component_key for component in result.component_results] == [
        "hp_primary",
        "hp_secondary",
    ]
    assert [component.value for component in result.component_results] == [1000.0, 500.0]
    assert result.base_healing == 1500.0


def test_resolver_wraps_base_healing_sum_overflow():
    resolver = HealingResolver(_attribute_resolver(source_hp=1e308))

    with pytest.raises(InvalidHealingResultError, match="base_healing"):
        resolver.resolve(
            _request(
                scaling_terms=(
                    HealingScalingTerm("huge_hp_primary", STAT_HP_MAX, 1.0),
                    HealingScalingTerm("huge_hp_secondary", STAT_HP_MAX, 1.0),
                )
            )
        )


def test_resolver_allows_single_negative_healing_bonus_when_total_multiplier_is_valid():
    resolver = HealingResolver(
        _attribute_resolver(outgoing_bonus=-0.5, incoming_bonus=0.2),
    )

    result = resolver.resolve(_request(flat_healing=100))

    assert result.outgoing_healing_bonus == -0.5
    assert result.incoming_healing_bonus == 0.2
    assert result.healing_bonus_multiplier == pytest.approx(0.7)
    assert result.final_healing == pytest.approx(770.0)


def test_resolver_rejects_negative_total_healing_bonus_multiplier_without_clamp():
    resolver = HealingResolver(_attribute_resolver(outgoing_bonus=-1.2))

    with pytest.raises(InvalidHealingResultError, match="healing_bonus_multiplier"):
        resolver.resolve(_request())


def test_flat_healing_enters_base_before_bonus_multiplier():
    resolver = HealingResolver(
        _attribute_resolver(outgoing_bonus=0.2, incoming_bonus=0.3),
    )

    result = resolver.resolve(_request(scaling_terms=(), flat_healing=100))

    assert result.base_healing == 100.0
    assert result.final_healing == 150.0


def test_zero_healing_request_produces_zero_result():
    result = HealingResolver(_attribute_resolver()).resolve(
        _request(scaling_terms=(), flat_healing=0)
    )

    assert result.base_healing == 0.0
    assert result.final_healing == 0.0
    assert result.component_results == ()


def test_resolver_does_not_round_formula_result():
    resolver = HealingResolver(_attribute_resolver(source_hp=3))

    result = resolver.resolve(
        _request(scaling_terms=(HealingScalingTerm("one_third_hp", STAT_HP_MAX, 1 / 3),))
    )

    assert result.final_healing == pytest.approx(1.0)


def test_resolver_wraps_attribute_owner_errors_as_healing_attribute_errors():
    # 属性契约已允许角色查询 resistance.*，原来的 owner 错误场景不复存在；
    # 用受控失败的 resolver 继续锁定“属性系统错误转换为治疗属性错误”的包装行为。
    class _FailingResolver:
        def new_session(self) -> object:
            return object()

        def resolve(self, query: object, *, options: object, session: object) -> object:
            del options, session
            raise UnsupportedOwnerError(f"owner error for {query}")

    resolver = HealingResolver(cast(Any, _FailingResolver()))

    with pytest.raises(InvalidHealingAttributeError, match="无法解析治疗属性"):
        resolver.resolve(_request())
