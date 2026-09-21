# 单一关注点：星烁与通用公式共享暴伤槽位，及复合伤害的逐参与者修饰收集。
from __future__ import annotations

from typing import Any, cast

import pytest

from genshin_sim.core.attributes import (
    RESISTANCE_ELECTRO,
    STAT_ELEMENTAL_MASTERY,
    AttributeQueryContext,
    AttributeResolver,
    AttributeSubjectRef,
    BaseAttributeContribution,
    BaseAttributeSet,
    ModifierProviderIndex,
    RuntimeSourceKind,
    RuntimeSourceRef,
    TraceLevel,
    create_public_attribute_registry,
)
from genshin_sim.core.elements import Element
from genshin_sim.core.systems.damage import (
    FORMULA_KEY_STELLAR_REACTION,
    CritOutcome,
    DamageFormulaContext,
    DamageModifierStage,
    DamageQuery,
    DamageRequest,
    DamageResolver,
    FixedCriticalDecisionProvider,
    StandardCriticalZonePolicy,
    StellarReactionDamageInput,
)
from genshin_sim.core.systems.damage.formulas import StellarReactionDamageFormula
from genshin_sim.core.systems.damage.models import DamageModifierTerm
from genshin_sim.core.systems.damage.modifiers import (
    DamageModifierIndex,
    DamageModifierProviderSpec,
)
from genshin_sim.core.systems.damage.resolver import DamageResolutionSession
from genshin_sim.core.systems.damage.stellar import StellarReactionParticipantInput

SOURCE = AttributeSubjectRef.character("character:slot_1")
OTHER = AttributeSubjectRef.character("character:slot_2")
TARGET = AttributeSubjectRef.target("target:star")
SOURCE_CONTEXT = RuntimeSourceRef(RuntimeSourceKind.CONFIG, "test.stellar")

CRIT_STAGE = DamageModifierStage.CRIT_DAMAGE_ADD
BONUS_STAGE = DamageModifierStage.STELLAR_REACTION_BONUS_ADD


def _attribute_resolver() -> AttributeResolver:
    registry = create_public_attribute_registry()
    return AttributeResolver(
        definitions=registry,
        base_attributes=BaseAttributeSet(
            tuple(
                (
                    subject,
                    BaseAttributeContribution(
                        STAT_ELEMENTAL_MASTERY,
                        200.0,
                        RuntimeSourceRef(RuntimeSourceKind.CONFIG, "test.stellar"),
                    ),
                )
                for subject in (SOURCE, OTHER)
            )
            + (
                (
                    TARGET,
                    BaseAttributeContribution(
                        RESISTANCE_ELECTRO,
                        0.0,
                        RuntimeSourceRef(RuntimeSourceKind.CONFIG, "test.stellar"),
                    ),
                ),
            )
        ),
        modifier_index=ModifierProviderIndex((), registry=registry),
    )


def _query(stellar_reaction: StellarReactionDamageInput) -> DamageQuery:
    request = DamageRequest(
        request_id="request:stellar",
        frame=0,
        formula_key=FORMULA_KEY_STELLAR_REACTION,
        main_attack_tag="星超导雷",
        impact_key="impact:stellar",
        source_ref=SOURCE,
        target_ref=TARGET,
        source_level=90,
        target_level=90,
        element=Element.ELECTRO,
        source_context=SOURCE_CONTEXT,
        stellar_reaction=stellar_reaction,
    )
    tags = request.tags
    return DamageQuery(
        request=request,
        source_attribute_context=AttributeQueryContext(tags=tags, target_ref=TARGET),
        target_attribute_context=AttributeQueryContext(
            tags=tags, source_ref=SOURCE_CONTEXT, target_ref=SOURCE
        ),
    )


class _OwnerScopedProvider:
    """按伤害来源自筛的 provider：只对自己作为来源的那份伤害贡献词条。

    同时自筛公式键，用来锁住「组分查询继承整次请求的公式键」这一行为：
    若组分查询退回 ``general``，本替身会在组分收集里静默返回空。
    """

    def __init__(
        self,
        owner_ref: AttributeSubjectRef,
        stage: DamageModifierStage,
        value: float,
    ) -> None:
        self._owner_ref = owner_ref
        self._stage = stage
        self._value = value
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=f"test.{stage.value}.{owner_ref.entity_id}",
            writes=frozenset({stage}),
            owner_ref=owner_ref,
        )

    def contribute(self, query: DamageQuery, session: Any) -> tuple[DamageModifierTerm, ...]:
        del session
        if query.request.formula_key != FORMULA_KEY_STELLAR_REACTION:
            return ()
        if query.request.source_ref != self._owner_ref:
            return ()
        return (
            DamageModifierTerm(
                stage=self._stage,
                value=self._value,
                provider_key=self.provider_spec.provider_key,
                source_ref=SOURCE_CONTEXT,
            ),
        )


class _TeamWideProvider:
    """队伍级 provider：不按来源自筛、只自筛公式键，对每个组分各贡献一次。

    对应「炉火融炼之心 4 件套」的真实模式：加成对全队星烁伤害生效，
    因此同样依赖组分查询继承公式键。
    """

    def __init__(self, stage: DamageModifierStage, value: float) -> None:
        self._stage = stage
        self._value = value
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=f"test.team.{stage.value}",
            writes=frozenset({stage}),
        )

    def contribute(self, query: DamageQuery, session: Any) -> tuple[DamageModifierTerm, ...]:
        del session
        if query.request.formula_key != FORMULA_KEY_STELLAR_REACTION:
            return ()
        return (
            DamageModifierTerm(
                stage=self._stage,
                value=self._value,
                provider_key=self.provider_spec.provider_key,
                source_ref=SOURCE_CONTEXT,
            ),
        )


def test_stellar_crit_damage_stage_enters_critical_zone() -> None:
    """星烁共享的暴伤词条并入该次伤害的暴击伤害，并进入暴击乘数。"""

    attribute_resolver = _attribute_resolver()
    query = _query(
        StellarReactionDamageInput(
            mode="character_direct",
            scaling_value=100.0,
            stellar_base_multiplier=1.0,
        )
    )
    session = DamageResolutionSession(attribute_resolver, query)
    index = DamageModifierIndex((_OwnerScopedProvider(SOURCE, CRIT_STAGE, 0.5),))
    modifiers = index.collect(query, session)
    formula = StellarReactionDamageFormula(
        critical_policy=StandardCriticalZonePolicy(
            decision_provider=FixedCriticalDecisionProvider(CritOutcome.CRITICAL)
        )
    )

    resolution = formula.resolve(
        DamageFormulaContext(
            query=query,
            session=session,
            modifiers=modifiers,
            trace_level=TraceLevel.FULL,
            modifier_collector=index.collect,
        )
    )

    assert resolution.critical is not None
    assert resolution.critical.outcome is CritOutcome.CRITICAL
    # 面板暴伤为 0，共享暴伤词条 +0.5 直接进入暴击乘数。
    assert resolution.critical.crit_damage == pytest.approx(0.5)
    assert resolution.critical.multiplier == pytest.approx(1.5)


def test_stellar_crit_damage_stage_is_inert_without_critical_outcome() -> None:
    """未暴击时该词条只进审计，不改变乘数。"""

    attribute_resolver = _attribute_resolver()
    query = _query(
        StellarReactionDamageInput(
            mode="character_direct",
            scaling_value=100.0,
            stellar_base_multiplier=1.0,
        )
    )
    session = DamageResolutionSession(attribute_resolver, query)
    index = DamageModifierIndex((_OwnerScopedProvider(SOURCE, CRIT_STAGE, 0.5),))
    modifiers = index.collect(query, session)
    resolution = StellarReactionDamageFormula().resolve(
        DamageFormulaContext(
            query=query,
            session=session,
            modifiers=modifiers,
            trace_level=TraceLevel.FULL,
            modifier_collector=index.collect,
        )
    )

    assert resolution.critical is not None
    assert resolution.critical.crit_damage == pytest.approx(0.5)
    assert resolution.critical.multiplier == pytest.approx(1.0)


def _composite_input() -> StellarReactionDamageInput:
    return StellarReactionDamageInput(
        mode="reaction_composite",
        scaling_value=0.0,
        stellar_base_multiplier=1.0,
        participants=(
            StellarReactionParticipantInput(
                participant_ref=SOURCE,
                source_level=90,
                reaction_base_value=100.0,
            ),
            StellarReactionParticipantInput(
                participant_ref=OTHER,
                source_level=90,
                reaction_base_value=100.0,
            ),
        ),
    )


def test_composite_collects_modifiers_per_participant() -> None:
    """复合伤害按组分重新收集：自筛到装备者的加成只作用于它自己那份。"""

    attribute_resolver = _attribute_resolver()
    resolver = DamageResolver(
        attribute_resolver=attribute_resolver,
        modifier_index=DamageModifierIndex((_OwnerScopedProvider(SOURCE, BONUS_STAGE, 0.5),)),
    )
    baseline = DamageResolver(attribute_resolver=attribute_resolver).resolve(
        _query(_composite_input())
    )

    boosted = resolver.resolve(_query(_composite_input()))

    baseline_by_ref = {
        component.participant_ref: component.component_damage for component in _components(baseline)
    }
    boosted_by_ref = {
        component.participant_ref: component.component_damage for component in _components(boosted)
    }

    assert boosted_by_ref[SOURCE] > baseline_by_ref[SOURCE]
    assert boosted_by_ref[OTHER] == pytest.approx(baseline_by_ref[OTHER])

    # 组分收集到的修饰项进入该组分审计，与顶层 applied_terms 相互独立：
    # 复合路径的加成不写顶层账单，因此必须能在这里被读到。
    boosted_components = {item.participant_ref: item for item in _components(boosted)}
    assert boosted_components[SOURCE].modifier_terms
    assert boosted_components[OTHER].modifier_terms == ()


def test_composite_owner_scoped_bonus_follows_the_participant_not_the_trigger() -> None:
    """装备者不是最外层触发者时，加成仍落在它自己那份组分上。"""

    attribute_resolver = _attribute_resolver()
    resolver = DamageResolver(
        attribute_resolver=attribute_resolver,
        modifier_index=DamageModifierIndex((_OwnerScopedProvider(OTHER, BONUS_STAGE, 0.5),)),
    )
    baseline = DamageResolver(attribute_resolver=attribute_resolver).resolve(
        _query(_composite_input())
    )

    boosted = resolver.resolve(_query(_composite_input()))

    baseline_by_ref = {
        component.participant_ref: component.component_damage for component in _components(baseline)
    }
    boosted_by_ref = {
        component.participant_ref: component.component_damage for component in _components(boosted)
    }

    assert boosted_by_ref[OTHER] > baseline_by_ref[OTHER]
    assert boosted_by_ref[SOURCE] == pytest.approx(baseline_by_ref[SOURCE])


def test_composite_team_wide_bonus_still_applies_to_every_participant() -> None:
    """不按来源自筛的队伍级加成对每个参与者各取一次，语义不变。"""

    attribute_resolver = _attribute_resolver()
    resolver = DamageResolver(
        attribute_resolver=attribute_resolver,
        modifier_index=DamageModifierIndex((_TeamWideProvider(BONUS_STAGE, 0.5),)),
    )
    baseline = DamageResolver(attribute_resolver=attribute_resolver).resolve(
        _query(_composite_input())
    )
    boosted = resolver.resolve(_query(_composite_input()))

    baseline_by_ref = {
        component.participant_ref: component.component_damage for component in _components(baseline)
    }
    boosted_by_ref = {
        component.participant_ref: component.component_damage for component in _components(boosted)
    }

    for ref in (SOURCE, OTHER):
        assert boosted_by_ref[ref] > baseline_by_ref[ref]


def _components(result: Any) -> tuple[Any, ...]:
    stellar = result.stellar_reaction_resolution
    assert stellar is not None
    return tuple(cast(Any, stellar).components)
