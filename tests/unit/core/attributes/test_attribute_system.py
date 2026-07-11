from __future__ import annotations

import math
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from genshin_sim.core.attributes import (
    STAT_ATK_BASE,
    STAT_ATK_TOTAL,
    STAT_CRIT_RATE,
    STAT_HP_BASE,
    STAT_HP_MAX,
    AttributeDefinition,
    AttributeDefinitionRegistry,
    AttributeKey,
    AttributeQuery,
    AttributeQueryContext,
    AttributeResolutionSession,
    AttributeResolveOptions,
    AttributeSubjectKind,
    AttributeSubjectRef,
    AttributeValidationError,
    BaseAttributeContribution,
    BaseAttributeSet,
    CircularDependencyError,
    ConflictingOverrideError,
    InvalidModifierStageError,
    MissingAttributeValueError,
    MissingQueryTargetError,
    MissingValuePolicy,
    ModifierProviderIndex,
    ModifierProviderSpec,
    ModifierStackingGroupDefinition,
    ModifierStackingPolicy,
    ModifierStage,
    ModifierTerm,
    OverridePolicy,
    ProviderAttributeRead,
    ProviderAttributeSubjectScope,
    ProviderDependencyViolationError,
    RuntimeSourceKind,
    RuntimeSourceRef,
    StaticModifierProvider,
    TraceLevel,
    UnsupportedOwnerError,
    create_public_attribute_registry,
)
from genshin_sim.core.attributes.definitions import AttributeVisibility
from genshin_sim.core.attributes.resolver import AttributeResolver

CHARACTER = AttributeSubjectRef.character("character:slot_1")
TARGET = AttributeSubjectRef.target("target:target_1")
ASSET_SOURCE = RuntimeSourceRef(RuntimeSourceKind.ASSET, "asset:test")
CONFIG_SOURCE = RuntimeSourceRef(RuntimeSourceKind.CONFIG, "config:test")


def _base(
    subject_ref: AttributeSubjectRef,
    attribute_key: AttributeKey,
    value: float,
) -> tuple[AttributeSubjectRef, BaseAttributeContribution]:
    return (
        subject_ref,
        BaseAttributeContribution(attribute_key, value, ASSET_SOURCE),
    )


def _term(
    target_key: AttributeKey,
    stage: ModifierStage,
    value: float,
    *,
    provider_key: str = "provider:test",
    group: str | None = None,
) -> ModifierTerm:
    return ModifierTerm(
        target_key=target_key,
        stage=stage,
        value=value,
        provider_key=provider_key,
        source_ref=CONFIG_SOURCE,
        stacking_group=group,
    )


def _static_provider(
    provider_key: str,
    terms: tuple[ModifierTerm, ...],
    *,
    private_namespace: str | None = None,
) -> StaticModifierProvider:
    normalized_terms = tuple(
        ModifierTerm(
            target_key=term.target_key,
            stage=term.stage,
            value=term.value,
            provider_key=provider_key,
            source_ref=term.source_ref,
            stacking_group=term.stacking_group,
            audit_tags=term.audit_tags,
        )
        for term in terms
    )
    return StaticModifierProvider(
        ModifierProviderSpec(
            provider_key=provider_key,
            writes=frozenset(term.target_key for term in normalized_terms),
            private_namespace=private_namespace,
        ),
        normalized_terms,
    )


def _resolver(
    *,
    base: tuple[tuple[AttributeSubjectRef, BaseAttributeContribution], ...] = (),
    providers: tuple[Any, ...] = (),
    registry: AttributeDefinitionRegistry | None = None,
) -> AttributeResolver:
    registry = registry or create_public_attribute_registry()
    return AttributeResolver(
        definitions=registry,
        base_attributes=BaseAttributeSet(base),
        modifier_index=ModifierProviderIndex(providers, registry=registry),
    )


def _set_runtime_attribute(obj: object, name: str, value: object) -> None:
    setattr(obj, name, value)


def test_attribute_key_and_definition_validation():
    with pytest.raises(AttributeValidationError):
        AttributeKey("atk")

    registry = AttributeDefinitionRegistry()
    definition = AttributeDefinition(
        AttributeKey("character.test.value"),
        frozenset({AttributeSubjectKind.CHARACTER}),
        "additive",
        visibility=AttributeVisibility.CONTENT_PRIVATE,
        namespace_owner="character.test",
    )
    registry.register(definition)
    assert registry.get(definition.key) is definition

    with pytest.raises(AttributeValidationError, match="重复属性定义"):
        registry.register(definition)
    with pytest.raises(AttributeValidationError, match="私有属性"):
        AttributeDefinition(
            AttributeKey("other.test.value"),
            frozenset({AttributeSubjectKind.CHARACTER}),
            "additive",
            visibility=AttributeVisibility.CONTENT_PRIVATE,
            namespace_owner="character.test",
        )


def test_character_and_target_subject_support_is_validated():
    resolver = _resolver(base=(_base(TARGET, STAT_HP_BASE, 10.0),))

    hp = resolver.resolve(AttributeQuery(TARGET, STAT_HP_MAX, frame=1))
    assert hp.final_value == 10.0

    with pytest.raises(UnsupportedOwnerError):
        resolver.resolve(AttributeQuery(TARGET, STAT_ATK_TOTAL, frame=1))


def test_missing_value_policy_uses_default_or_raises():
    default_key = AttributeKey("character.test.default_value")
    required_key = AttributeKey("character.test.required_value")
    registry = AttributeDefinitionRegistry(
        (
            AttributeDefinition(
                default_key,
                frozenset({AttributeSubjectKind.CHARACTER}),
                "additive",
                default_value=2.5,
                visibility=AttributeVisibility.CONTENT_PRIVATE,
                namespace_owner="character.test",
            ),
            AttributeDefinition(
                required_key,
                frozenset({AttributeSubjectKind.CHARACTER}),
                "additive",
                missing_value_policy=MissingValuePolicy.ERROR,
                visibility=AttributeVisibility.CONTENT_PRIVATE,
                namespace_owner="character.test",
            ),
        )
    )
    resolver = _resolver(registry=registry)

    assert resolver.resolve(AttributeQuery(CHARACTER, default_key, frame=1)).final_value == 2.5
    with pytest.raises(MissingAttributeValueError):
        resolver.resolve(AttributeQuery(CHARACTER, required_key, frame=1))


def test_base_sum_total_stat_and_additive_policies():
    provider = _static_provider(
        "provider:stats",
        (
            _term(STAT_ATK_BASE, ModifierStage.BASE_ADD, 10.0),
            _term(STAT_ATK_TOTAL, ModifierStage.PERCENT_ADD, 0.2),
            _term(STAT_ATK_TOTAL, ModifierStage.FLAT_ADD, 100.0),
            _term(STAT_ATK_TOTAL, ModifierStage.FINAL_MULTIPLIER, 0.5),
            _term(STAT_ATK_TOTAL, ModifierStage.FINAL_MULTIPLIER, 0.1),
            _term(STAT_CRIT_RATE, ModifierStage.FLAT_ADD, 0.2),
        ),
    )
    resolver = _resolver(
        base=(
            _base(CHARACTER, STAT_ATK_BASE, 1000.0),
            _base(CHARACTER, STAT_ATK_BASE, 500.0),
            _base(CHARACTER, STAT_CRIT_RATE, 0.05),
        ),
        providers=(provider,),
    )

    assert resolver.resolve(AttributeQuery(CHARACTER, STAT_ATK_BASE, frame=1)).final_value == 1510
    assert (
        resolver.resolve(AttributeQuery(CHARACTER, STAT_ATK_TOTAL, frame=1)).final_value
        == 3154.8
    )
    assert resolver.resolve(AttributeQuery(CHARACTER, STAT_CRIT_RATE, frame=1)).final_value == 0.25


def test_stacking_group_highest_and_lowest_rejects_losers():
    registry = create_public_attribute_registry()
    registry.register_stacking_group(
        ModifierStackingGroupDefinition(
            "crit.highest",
            STAT_CRIT_RATE,
            ModifierStage.FLAT_ADD,
            ModifierStackingPolicy.HIGHEST,
        )
    )
    registry.register_stacking_group(
        ModifierStackingGroupDefinition(
            "crit.lowest",
            STAT_CRIT_RATE,
            ModifierStage.FLAT_ADD,
            ModifierStackingPolicy.LOWEST,
        )
    )
    provider = _static_provider(
        "provider:stacking",
        (
            _term(STAT_CRIT_RATE, ModifierStage.FLAT_ADD, 0.1, group="crit.highest"),
            _term(STAT_CRIT_RATE, ModifierStage.FLAT_ADD, 0.2, group="crit.highest"),
            _term(STAT_CRIT_RATE, ModifierStage.FLAT_ADD, 0.3, group="crit.lowest"),
            _term(STAT_CRIT_RATE, ModifierStage.FLAT_ADD, 0.4, group="crit.lowest"),
        ),
    )

    resolution = _resolver(providers=(provider,), registry=registry).resolve(
        AttributeQuery(CHARACTER, STAT_CRIT_RATE, frame=1)
    )

    assert resolution.final_value == pytest.approx(0.5)
    assert [term.value for term in resolution.rejected_terms] == [0.1, 0.4]


def test_override_forbidden_single_and_conflict():
    forbidden_provider = _static_provider(
        "provider:override.forbidden",
        (_term(STAT_CRIT_RATE, ModifierStage.OVERRIDE, 0.8),),
    )
    with pytest.raises(InvalidModifierStageError):
        _resolver(providers=(forbidden_provider,)).resolve(
            AttributeQuery(CHARACTER, STAT_CRIT_RATE, frame=1)
        )

    private_key = AttributeKey("character.test.override_value")
    registry = create_public_attribute_registry()
    registry.register(
        AttributeDefinition(
            private_key,
            frozenset({AttributeSubjectKind.CHARACTER}),
            "additive",
            lower_bound=0.0,
            upper_bound=1.0,
            override_policy=OverridePolicy.SINGLE,
            visibility=AttributeVisibility.CONTENT_PRIVATE,
            namespace_owner="character.test",
        )
    )
    single_provider = _static_provider(
        "provider:override.single",
        (
            ModifierTerm(
                private_key,
                ModifierStage.OVERRIDE,
                2.0,
                "provider:override.single",
                CONFIG_SOURCE,
            ),
        ),
        private_namespace="character.test",
    )
    assert (
        _resolver(providers=(single_provider,), registry=registry)
        .resolve(AttributeQuery(CHARACTER, private_key, frame=1))
        .final_value
        == 1.0
    )

    conflict_provider = _static_provider(
        "provider:override.conflict",
        (
            ModifierTerm(private_key, ModifierStage.OVERRIDE, 0.2, "x", CONFIG_SOURCE),
            ModifierTerm(private_key, ModifierStage.OVERRIDE, 0.4, "x", CONFIG_SOURCE),
        ),
        private_namespace="character.test",
    )
    with pytest.raises(ConflictingOverrideError):
        _resolver(providers=(conflict_provider,), registry=registry).resolve(
            AttributeQuery(CHARACTER, private_key, frame=1)
        )


def test_provider_writes_and_reads_are_validated():
    class BadWriteProvider:
        provider_spec = ModifierProviderSpec(
            provider_key="provider:bad_write",
            writes=frozenset({STAT_CRIT_RATE}),
        )

        def contribute(self, query: AttributeQuery, session: AttributeResolutionSession):
            del query, session
            return (
                _term(
                    STAT_HP_BASE,
                    ModifierStage.BASE_ADD,
                    1.0,
                    provider_key=self.provider_spec.provider_key,
                ),
            )

    with pytest.raises(ProviderDependencyViolationError, match="未声明写入"):
        _resolver(providers=(BadWriteProvider(),)).resolve(
            AttributeQuery(CHARACTER, STAT_CRIT_RATE, frame=1)
        )

    class BadReadProvider:
        provider_spec = ModifierProviderSpec(
            provider_key="provider:bad_read",
            writes=frozenset({STAT_CRIT_RATE}),
        )

        def contribute(self, query: AttributeQuery, session: AttributeResolutionSession):
            session.resolve_dependency(
                AttributeQuery(query.subject_ref, STAT_HP_MAX, query.frame, query.context)
            )
            return ()

    with pytest.raises(ProviderDependencyViolationError, match="未声明读取"):
        _resolver(providers=(BadReadProvider(),)).resolve(
            AttributeQuery(CHARACTER, STAT_CRIT_RATE, frame=1)
        )


def test_same_subject_cycles_are_rejected_and_cross_subject_dependency_is_legal():
    key_a = AttributeKey("character.test.a")
    key_b = AttributeKey("character.test.b")
    cyclic_registry = AttributeDefinitionRegistry(
        (
            AttributeDefinition(
                key_a,
                frozenset({AttributeSubjectKind.CHARACTER}),
                "additive",
                dependencies=(key_b,),
                visibility=AttributeVisibility.CONTENT_PRIVATE,
                namespace_owner="character.test",
            ),
            AttributeDefinition(
                key_b,
                frozenset({AttributeSubjectKind.CHARACTER}),
                "additive",
                dependencies=(key_a,),
                visibility=AttributeVisibility.CONTENT_PRIVATE,
                namespace_owner="character.test",
            ),
        )
    )
    with pytest.raises(ProviderDependencyViolationError, match="同主体循环"):
        ModifierProviderIndex((), registry=cyclic_registry)

    class OwnerHpProvider:
        provider_spec = ModifierProviderSpec(
            provider_key="provider:owner_hp",
            reads=(
                ProviderAttributeRead(
                    STAT_HP_MAX,
                    ProviderAttributeSubjectScope.PROVIDER_OWNER,
                ),
            ),
            writes=frozenset({STAT_HP_MAX}),
            owner_ref=CHARACTER,
        )

        def contribute(self, query: AttributeQuery, session: AttributeResolutionSession):
            if query.subject_ref == self.provider_spec.owner_ref:
                return ()
            dependency = session.resolve_provider_owner(
                query,
                CHARACTER,
                provider_key=self.provider_spec.provider_key,
            )
            return (
                _term(
                    STAT_HP_MAX,
                    ModifierStage.FLAT_ADD,
                    dependency.final_value * 0.1,
                    provider_key=self.provider_spec.provider_key,
                ),
            )

    resolver = _resolver(
        base=(
            _base(CHARACTER, STAT_HP_BASE, 1000.0),
            _base(TARGET, STAT_HP_BASE, 2000.0),
        ),
        providers=(OwnerHpProvider(),),
    )
    assert resolver.resolve(AttributeQuery(TARGET, STAT_HP_MAX, frame=1)).final_value == 2100.0


def test_runtime_cycle_detection_uses_full_subject_identity():
    class RuntimeCycleProvider:
        provider_spec = ModifierProviderSpec(
            provider_key="provider:runtime_cycle",
            reads=(
                ProviderAttributeRead(
                    STAT_HP_MAX,
                    ProviderAttributeSubjectScope.PROVIDER_OWNER,
                ),
            ),
            writes=frozenset({STAT_HP_MAX}),
            owner_ref=CHARACTER,
        )

        def contribute(self, query: AttributeQuery, session: AttributeResolutionSession):
            del query
            return (
                _term(
                    STAT_HP_MAX,
                    ModifierStage.FLAT_ADD,
                    session.resolve_provider_owner(
                        AttributeQuery(CHARACTER, STAT_HP_MAX, 1),
                        CHARACTER,
                        provider_key=self.provider_spec.provider_key,
                    ).final_value,
                    provider_key=self.provider_spec.provider_key,
                ),
            )

    resolver = _resolver(
        base=(_base(CHARACTER, STAT_HP_BASE, 1000.0),),
        providers=(RuntimeCycleProvider(),),
    )
    with pytest.raises(CircularDependencyError):
        resolver.resolve(AttributeQuery(CHARACTER, STAT_HP_MAX, frame=1))


def test_session_memo_is_not_cross_top_level_cache():
    class CountingProvider:
        def __init__(self) -> None:
            self.calls = 0
            self.provider_spec = ModifierProviderSpec(
                provider_key="provider:counting",
                writes=frozenset({STAT_CRIT_RATE}),
            )

        def contribute(self, query: AttributeQuery, session: AttributeResolutionSession):
            del query, session
            self.calls += 1
            return ()

    provider = CountingProvider()
    resolver = _resolver(providers=(provider,))
    query = AttributeQuery(CHARACTER, STAT_CRIT_RATE, frame=1)
    session = resolver.new_session()

    first = resolver.resolve(query, session=session)
    second = resolver.resolve(query, session=session)
    assert first is second
    assert provider.calls == 1

    resolver.resolve(query)
    assert provider.calls == 2


def test_trace_level_controls_resolution_details():
    registry = create_public_attribute_registry()
    registry.register_stacking_group(
        ModifierStackingGroupDefinition(
            "crit.trace",
            STAT_CRIT_RATE,
            ModifierStage.FLAT_ADD,
            ModifierStackingPolicy.HIGHEST,
        )
    )
    resolver = _resolver(
        base=(_base(CHARACTER, STAT_HP_BASE, 100.0),),
        providers=(
            _static_provider(
                "provider:trace",
                (
                    _term(STAT_CRIT_RATE, ModifierStage.FLAT_ADD, 0.1, group="crit.trace"),
                    _term(STAT_CRIT_RATE, ModifierStage.FLAT_ADD, 0.2, group="crit.trace"),
                ),
            ),
        ),
        registry=registry,
    )
    query = AttributeQuery(CHARACTER, STAT_CRIT_RATE, frame=1)

    none = resolver.resolve(
        query,
        options=AttributeResolveOptions(trace_level=TraceLevel.NONE),
    )
    applied = resolver.resolve(
        query,
        options=AttributeResolveOptions(trace_level=TraceLevel.APPLIED),
    )
    full = resolver.resolve(
        query,
        options=AttributeResolveOptions(trace_level=TraceLevel.FULL),
    )

    assert none.applied_terms == ()
    assert none.rejected_terms == ()
    assert applied.applied_terms[0].value == 0.2
    assert applied.rejected_terms == ()
    assert full.rejected_terms[0].value == 0.1


def test_snapshot_is_immutable_and_preserves_query_context():
    resolver = _resolver(base=(_base(CHARACTER, STAT_HP_BASE, 100.0),))
    context = AttributeQueryContext(
        tags=frozenset({"hydro"}),
        source_ref=CONFIG_SOURCE,
        target_ref=TARGET,
    )
    query = AttributeQuery(CHARACTER, STAT_HP_MAX, frame=10, context=context)
    snapshot = resolver.snapshot(
        snapshot_id="snapshot:1",
        queries=(query,),
    )

    assert snapshot.entries[0].value == 100.0
    assert snapshot.entries[0].context == context
    with pytest.raises(FrozenInstanceError):
        _set_runtime_attribute(snapshot, "entries", ())


def test_snapshot_rejects_mixed_subjects_or_frames():
    resolver = _resolver(base=(_base(CHARACTER, STAT_HP_BASE, 100.0),))

    with pytest.raises(AttributeValidationError, match="frame"):
        resolver.snapshot(
            snapshot_id="snapshot:mixed_frame",
            queries=(
                AttributeQuery(CHARACTER, STAT_HP_MAX, frame=1),
                AttributeQuery(CHARACTER, STAT_HP_MAX, frame=2),
            ),
        )
    with pytest.raises(AttributeValidationError, match="subject_ref"):
        resolver.snapshot(
            snapshot_id="snapshot:mixed_subject",
            queries=(
                AttributeQuery(CHARACTER, STAT_HP_MAX, frame=1),
                AttributeQuery(TARGET, STAT_HP_MAX, frame=1),
            ),
        )


def test_missing_query_target_uses_structured_attribute_error():
    session = _resolver().new_session()

    with pytest.raises(MissingQueryTargetError):
        session.resolve_query_target(AttributeQuery(CHARACTER, STAT_HP_MAX, frame=1))


def test_rejects_non_finite_values_normalizes_negative_zero_and_uses_fsum():
    with pytest.raises(AttributeValidationError):
        ModifierTerm(
            STAT_CRIT_RATE,
            ModifierStage.FLAT_ADD,
            math.nan,
            "provider:nan",
            CONFIG_SOURCE,
        )
    with pytest.raises(AttributeValidationError):
        BaseAttributeContribution(STAT_HP_BASE, math.inf, ASSET_SOURCE)

    resolver = _resolver(
        base=(
            _base(CHARACTER, STAT_HP_BASE, 1e16),
            _base(CHARACTER, STAT_HP_BASE, 1.0),
            _base(CHARACTER, STAT_HP_BASE, -1e16),
        ),
        providers=(
            _static_provider(
                "provider:negative_zero",
                (_term(STAT_CRIT_RATE, ModifierStage.FLAT_ADD, -0.0),),
            ),
        ),
    )
    assert resolver.resolve(AttributeQuery(CHARACTER, STAT_HP_BASE, frame=1)).final_value == 1.0
    zero = resolver.resolve(AttributeQuery(CHARACTER, STAT_CRIT_RATE, frame=1)).final_value
    assert zero == 0.0
    assert math.copysign(1.0, zero) == 1.0
