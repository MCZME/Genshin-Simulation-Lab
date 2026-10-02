# 单一关注点：伤害事实（会话容器 + 请求级）的声明、注册、作用域叠加、越权与装配校验。
from __future__ import annotations

from typing import cast

import pytest

from genshin_sim.core.attributes import (
    BONUS_DAMAGE_HYDRO,
    RESISTANCE_HYDRO,
    STAT_CRIT_DAMAGE,
    STAT_HP_MAX,
    AttributeQueryContext,
    AttributeResolver,
    AttributeSubjectRef,
    BaseAttributeContribution,
    BaseAttributeSet,
    ModifierProviderIndex,
    RuntimeSourceKind,
    RuntimeSourceRef,
    create_public_attribute_registry,
)
from genshin_sim.core.elements import Element
from genshin_sim.core.impacts.models import ImpactKind, ImpactRequest
from genshin_sim.core.systems.damage import (
    ConflictingDamageFactError,
    DamageFactIndex,
    DamageFactSpec,
    DamageFactValue,
    DamageModifierIndex,
    DamageModifierProviderSpec,
    DamageModifierStage,
    DamageModifierTerm,
    DamageProviderViolationError,
    DamageQuery,
    DamageRequest,
    DamageResolutionScope,
    DamageResolver,
    DamageScalingTerm,
    DamageValidationError,
)
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_GENERAL

SOURCE = AttributeSubjectRef.character("character:slot_1")
TARGET = AttributeSubjectRef.target("target:target_1")
CONFIG_SOURCE = RuntimeSourceRef(RuntimeSourceKind.CONFIG, "test.config")
CONTENT_SOURCE = RuntimeSourceRef(RuntimeSourceKind.CONTENT, "test.provider")

FACT_KEY = "test.facts.ray_index"
PROVIDER_KEY = "test.provider"


class _StateStore:
    """测试用底层状态 store：事实真值的唯一持有者（模拟角色状态/领域 store）。"""

    def __init__(self) -> None:
        self.values: dict[str, object] = {}


class _ForwardingFactContainer:
    """会话容器的规定形态：无状态转发视图，read_fact 直读 store，不自存变量。"""

    def __init__(self, provider_key: str, names: tuple[str, ...], store: _StateStore) -> None:
        self.fact_spec = DamageFactSpec(
            provider_key=provider_key,
            facts=frozenset(f"{provider_key}.{name}" for name in names),
        )
        self._store = store

    def read_fact(self, key: str) -> DamageFactValue | None:
        return cast("DamageFactValue | None", self._store.values.get(key))


class _FactReadingProvider:
    """只有当事实超过阈值时才产出修饰项的测试 provider。"""

    def __init__(self, *, reads_facts: frozenset[str], threshold: float) -> None:
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=PROVIDER_KEY,
            writes=frozenset({DamageModifierStage.DAMAGE_BONUS_ADD}),
            reads_facts=reads_facts,
        )
        self._threshold = threshold

    def contribute(
        self, query: DamageQuery, scope: DamageResolutionScope
    ) -> tuple[DamageModifierTerm, ...]:
        del query
        value = scope.read_fact(FACT_KEY)
        if value is None or float(value) <= self._threshold:
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.DAMAGE_BONUS_ADD,
                value=0.2,
                provider_key=PROVIDER_KEY,
                source_ref=CONTENT_SOURCE,
            ),
        )


def _attribute_resolver() -> AttributeResolver:
    contributions = (
        (SOURCE, BaseAttributeContribution(STAT_HP_MAX, 1000.0, CONFIG_SOURCE)),
        (SOURCE, BaseAttributeContribution(BONUS_DAMAGE_HYDRO, 0.2, CONFIG_SOURCE)),
        (SOURCE, BaseAttributeContribution(STAT_CRIT_DAMAGE, 0.5, CONFIG_SOURCE)),
        (TARGET, BaseAttributeContribution(RESISTANCE_HYDRO, 0.1, CONFIG_SOURCE)),
    )
    registry = create_public_attribute_registry()
    return AttributeResolver(
        definitions=registry,
        base_attributes=BaseAttributeSet(contributions),
        modifier_index=ModifierProviderIndex((), registry=registry),
    )


def _query(request_facts: dict[str, DamageFactValue] | None = None) -> DamageQuery:
    return DamageQuery(
        request=DamageRequest(
            request_id="damage:test:1",
            frame=10,
            formula_key=FORMULA_KEY_GENERAL,
            main_attack_tag="test.damage",
            impact_key="test.damage",
            source_ref=SOURCE,
            target_ref=TARGET,
            source_level=90,
            target_level=90,
            element=Element.HYDRO,
            scaling_terms=(DamageScalingTerm("hp", STAT_HP_MAX, 1.0),),
            request_facts=request_facts or {},
            can_crit=False,
            source_context=CONFIG_SOURCE,
        ),
        source_attribute_context=AttributeQueryContext(target_ref=TARGET),
        target_attribute_context=AttributeQueryContext(target_ref=SOURCE),
    )


def _scope(
    fact_index: DamageFactIndex | None = None,
    request_facts: dict[str, DamageFactValue] | None = None,
) -> DamageResolutionScope:
    return DamageResolutionScope(
        _attribute_resolver(),
        _query(request_facts),
        fact_index=fact_index if fact_index is not None else DamageFactIndex(),
    )


def test_fact_spec_requires_namespaced_keys():
    with pytest.raises(DamageValidationError, match="命名空间下"):
        DamageFactSpec(provider_key="test.facts", facts=frozenset({"other.key"}))


def test_fact_spec_rejects_empty_facts():
    with pytest.raises(DamageValidationError, match="facts 不能为空"):
        DamageFactSpec(provider_key="test.facts", facts=frozenset())


def test_fact_index_rejects_duplicate_provider_key():
    store = _StateStore()
    first = _ForwardingFactContainer("test.facts", ("ray_index",), store)
    second = _ForwardingFactContainer("test.facts", ("power",), store)
    with pytest.raises(ConflictingDamageFactError, match="重复伤害事实容器"):
        DamageFactIndex((first, second))


def test_fact_index_read_returns_none_for_unknown_key():
    index = DamageFactIndex(
        (_ForwardingFactContainer("test.facts", ("ray_index",), _StateStore()),)
    )
    assert index.read("test.unknown.key") is None
    assert index.provides("test.unknown.key") is False
    assert index.fact_keys == (FACT_KEY,)


def test_fact_index_rejects_unsupported_value_type():
    store = _StateStore()
    store.values[FACT_KEY] = (1, 2)
    index = DamageFactIndex((_ForwardingFactContainer("test.facts", ("ray_index",), store),))
    with pytest.raises(DamageValidationError, match="取值类型不受支持"):
        index.read(FACT_KEY)


def test_fact_index_rejects_non_finite_value():
    store = _StateStore()
    store.values[FACT_KEY] = float("inf")
    index = DamageFactIndex((_ForwardingFactContainer("test.facts", ("ray_index",), store),))
    with pytest.raises(DamageValidationError, match="必须是有限数"):
        index.read(FACT_KEY)


def test_damage_request_rejects_unsupported_request_fact_value():
    with pytest.raises(DamageValidationError, match="取值类型不受支持"):
        _query(cast("dict[str, DamageFactValue]", {FACT_KEY: (1, 2)}))


def test_damage_request_rejects_empty_request_fact_key():
    with pytest.raises(DamageValidationError, match="request fact key"):
        _query({"": 1})


def test_impact_request_rejects_unsupported_request_fact_value():
    with pytest.raises(ValueError, match="取值类型不受支持"):
        ImpactRequest(
            frame=1,
            kind=ImpactKind.DAMAGE,
            impact_key="test.damage",
            request_facts=cast("dict[str, DamageFactValue]", {FACT_KEY: object()}),
        )


def test_read_fact_requires_active_provider():
    scope = _scope()

    with pytest.raises(DamageProviderViolationError, match="只有活动 damage provider"):
        scope.read_fact(FACT_KEY)


def test_read_fact_rejects_undeclared_key():
    scope = _scope(request_facts={FACT_KEY: 1.0})
    scope.begin_provider(
        DamageModifierProviderSpec(
            provider_key=PROVIDER_KEY,
            writes=frozenset({DamageModifierStage.DAMAGE_BONUS_ADD}),
        )
    )

    with pytest.raises(DamageProviderViolationError, match="未声明读取伤害事实"):
        scope.read_fact(FACT_KEY)


def test_read_fact_returns_none_when_neither_scope_holds_key():
    scope = _scope(DamageFactIndex())
    scope.begin_provider(
        DamageModifierProviderSpec(
            provider_key=PROVIDER_KEY,
            writes=frozenset({DamageModifierStage.DAMAGE_BONUS_ADD}),
            reads_facts=frozenset({FACT_KEY}),
        )
    )

    assert scope.read_fact(FACT_KEY) is None


def test_request_fact_takes_precedence_over_session_container():
    store = _StateStore()
    store.values[FACT_KEY] = 7
    scope = _scope(
        DamageFactIndex((_ForwardingFactContainer("test.facts", ("ray_index",), store),)),
        request_facts={FACT_KEY: 2},
    )
    scope.begin_provider(
        DamageModifierProviderSpec(
            provider_key=PROVIDER_KEY,
            writes=frozenset({DamageModifierStage.DAMAGE_BONUS_ADD}),
            reads_facts=frozenset({FACT_KEY}),
        )
    )

    # 请求级事实是发射时绑定的身份值，必须盖过会话级的当下取值。
    assert scope.read_fact(FACT_KEY) == 2


def test_request_fact_visible_without_session_container():
    scope = _scope(request_facts={FACT_KEY: 3})
    scope.begin_provider(
        DamageModifierProviderSpec(
            provider_key=PROVIDER_KEY,
            writes=frozenset({DamageModifierStage.DAMAGE_BONUS_ADD}),
            reads_facts=frozenset({FACT_KEY}),
        )
    )

    assert scope.read_fact(FACT_KEY) == 3


def test_session_container_falls_back_when_request_does_not_hold_key():
    store = _StateStore()
    store.values[FACT_KEY] = 5
    scope = _scope(
        DamageFactIndex((_ForwardingFactContainer("test.facts", ("ray_index",), store),)),
        request_facts={FACT_KEY: 2},
    )
    scope.begin_provider(
        DamageModifierProviderSpec(
            provider_key=PROVIDER_KEY,
            writes=frozenset({DamageModifierStage.DAMAGE_BONUS_ADD}),
            reads_facts=frozenset({FACT_KEY}),
        )
    )
    request_only = scope.read_fact(FACT_KEY)

    empty_scope = _scope(
        DamageFactIndex((_ForwardingFactContainer("test.facts", ("ray_index",), store),)),
    )
    empty_scope.begin_provider(
        DamageModifierProviderSpec(
            provider_key=PROVIDER_KEY,
            writes=frozenset({DamageModifierStage.DAMAGE_BONUS_ADD}),
            reads_facts=frozenset({FACT_KEY}),
        )
    )

    assert request_only == 2
    assert empty_scope.read_fact(FACT_KEY) == 5


def test_resolver_accepts_provider_reading_declared_request_fact():
    provider = _FactReadingProvider(reads_facts=frozenset({FACT_KEY}), threshold=0.5)

    resolver = DamageResolver(
        _attribute_resolver(),
        modifier_index=DamageModifierIndex((provider,)),
        fact_index=DamageFactIndex(),
        request_fact_keys=frozenset({FACT_KEY}),
    )

    assert resolver.request_fact_keys == frozenset({FACT_KEY})


def test_resolver_rejects_provider_reading_unregistered_fact():
    provider = _FactReadingProvider(reads_facts=frozenset({"test.missing.key"}), threshold=0.5)

    with pytest.raises(DamageValidationError, match="没有容器提供"):
        DamageResolver(
            _attribute_resolver(),
            modifier_index=DamageModifierIndex((provider,)),
            fact_index=DamageFactIndex(),
        )


def test_resolver_rejects_request_fact_key_colliding_with_session_container():
    store = _StateStore()
    provider = _FactReadingProvider(reads_facts=frozenset({FACT_KEY}), threshold=0.5)

    with pytest.raises(DamageValidationError, match="作用域语义"):
        DamageResolver(
            _attribute_resolver(),
            modifier_index=DamageModifierIndex((provider,)),
            fact_index=DamageFactIndex(
                (_ForwardingFactContainer("test.facts", ("ray_index",), store),)
            ),
            request_fact_keys=frozenset({FACT_KEY}),
        )


def test_provider_gates_term_on_request_fact_and_audits_it():
    provider = _FactReadingProvider(reads_facts=frozenset({FACT_KEY}), threshold=0.5)
    resolver = DamageResolver(
        _attribute_resolver(),
        modifier_index=DamageModifierIndex((provider,)),
        fact_index=DamageFactIndex(),
        request_fact_keys=frozenset({FACT_KEY}),
    )

    baseline = resolver.resolve(_query())
    # 请求未携带事实时 provider 不产出任何词条（账单里仍会有公式自身的面板读取词条）。
    assert PROVIDER_KEY not in {term.provider_key for term in baseline.applied_terms}
    assert baseline.request_facts == {}

    boosted = resolver.resolve(_query({FACT_KEY: 1.0}))

    assert (boosted.damage_bonus_multiplier - baseline.damage_bonus_multiplier) == pytest.approx(
        0.2
    )
    provider_terms = [term for term in boosted.applied_terms if term.provider_key == PROVIDER_KEY]
    assert [term.value for term in provider_terms] == [0.2]
    # 请求级事实随结果进入审计，复现不依赖结算后回读任何容器。
    assert boosted.request_facts == {FACT_KEY: 1.0}
    assert boosted.to_audit_dict()["request_facts"] == {FACT_KEY: 1.0}


def test_provider_gates_term_on_session_fact():
    store = _StateStore()
    container = _ForwardingFactContainer("test.facts", ("ray_index",), store)
    provider = _FactReadingProvider(reads_facts=frozenset({FACT_KEY}), threshold=0.5)
    resolver = DamageResolver(
        _attribute_resolver(),
        modifier_index=DamageModifierIndex((provider,)),
        fact_index=DamageFactIndex((container,)),
    )

    baseline = resolver.resolve(_query())
    store.values[FACT_KEY] = 1.0
    boosted = resolver.resolve(_query())

    assert (boosted.damage_bonus_multiplier - baseline.damage_bonus_multiplier) == pytest.approx(
        0.2
    )
    # 会话级取值不进入请求级审计快照。
    assert boosted.request_facts == {}
