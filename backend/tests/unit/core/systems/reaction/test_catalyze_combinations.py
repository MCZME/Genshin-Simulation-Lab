"""激化复合候选的纯 Reaction 决议测试。"""

from __future__ import annotations

from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
    ElementalSourceRef,
    ElementalStateLinkRef,
    ElementalSubjectRef,
    TransformativeReactionSourceKind,
)
from genshin_sim.core.systems.aura import (
    AuraComponent,
    AuraContribution,
    AuraContributionRef,
    AuraInstanceRef,
    AuraStrength,
    AuraView,
    quicken_decay_profile,
)
from genshin_sim.core.systems.reaction import (
    CatalyzeCurrentImpactDamageAdjustment,
    CatalyzeImpactQualification,
    QuickenState,
    ReactionEvaluationRequest,
    ReactionRuntime,
    ReactionStateInstanceRef,
    TransformativeSourceObservation,
    create_default_reaction_bootstrap,
)

SOURCE = ElementalSourceRef("character:slot_1", "ability:catalyze")
TARGET = ElementalSubjectRef.target("target:catalyze")
QUICKEN_LINK = ElementalStateLinkRef("elemental-state-link:quicken")


def test_quicken_electro_then_dendro_orders_spread_before_quicken_coverage() -> None:
    resolution = _runtime().evaluate(
        _request(
            incoming_element=Element.DENDRO,
            incoming_amount=AuraAmount.one(),
            components=(
                _component(AuraKind.QUICKEN, AuraAmount.one(), (QUICKEN_LINK,)),
                _component(AuraKind.ELECTRO, AuraAmount.one()),
            ),
            quicken_state=_quicken_state(),
            qualification=Element.DENDRO,
        )
    )

    assert _reaction_keys(resolution) == ("reaction.spread", "reaction.quicken")
    assert isinstance(resolution.damage_adjustment, CatalyzeCurrentImpactDamageAdjustment)
    assert resolution.damage_adjustment.reaction_multiplier == 1.25
    assert resolution.sequence.steps[1].occurrences[0].transition.aura_kind is AuraKind.ELECTRO
    assert (
        resolution.sequence.steps[1]
        .state_planning_intents[0]
        .intent_ref.endswith(":quicken-coverage")
    )


def test_quicken_cryo_then_electro_records_parallel_superconduct_and_aggravate() -> None:
    resolution = _runtime().evaluate(
        _request(
            incoming_element=Element.ELECTRO,
            incoming_amount=AuraAmount.one(),
            components=(
                _component(AuraKind.QUICKEN, AuraAmount.one(), (QUICKEN_LINK,)),
                _component(AuraKind.CRYO, AuraAmount.one()),
            ),
            quicken_state=_quicken_state(),
            qualification=Element.ELECTRO,
            transformative_observation=_transformative_observation(),
        )
    )

    assert len(resolution.sequence.steps) == 1
    assert _reaction_keys(resolution) == ("reaction.superconduct", "reaction.aggravate")
    assert isinstance(resolution.damage_adjustment, CatalyzeCurrentImpactDamageAdjustment)
    assert resolution.damage_adjustment.reaction_multiplier == 1.15
    assert all(
        occurrence.transition.incoming_before == AuraAmount.one()
        for occurrence in resolution.sequence.steps[0].occurrences
    )


def test_cryo_dendro_then_electro_uses_only_remaining_budget_for_quicken() -> None:
    resolution = _runtime().evaluate(
        _request(
            incoming_element=Element.ELECTRO,
            incoming_amount=AuraAmount(2),
            components=(
                _component(AuraKind.CRYO, AuraAmount.one()),
                _component(AuraKind.DENDRO, AuraAmount.one()),
            ),
            transformative_observation=_transformative_observation(),
        )
    )

    assert _reaction_keys(resolution) == ("reaction.superconduct", "reaction.quicken")
    quicken = resolution.sequence.steps[1].occurrences[0]
    assert quicken.transition.incoming_before == AuraAmount.one()
    assert quicken.transition.incoming_consumed == AuraAmount.one()
    assert quicken.transition.aura_kind is AuraKind.DENDRO


def _runtime() -> ReactionRuntime:
    return create_default_reaction_bootstrap().create_runtime()


def _request(
    *,
    incoming_element: Element,
    incoming_amount: AuraAmount,
    components: tuple[AuraComponent, ...],
    quicken_state: QuickenState | None = None,
    qualification: Element | None = None,
    transformative_observation: TransformativeSourceObservation | None = None,
) -> ReactionEvaluationRequest:
    return ReactionEvaluationRequest(
        interaction_id="interaction:catalyze",
        target_impact_ref="impact:catalyze",
        frame=0,
        order=0,
        source_ref=SOURCE,
        subject_ref=TARGET,
        incoming_element=incoming_element,
        incoming_amount=incoming_amount,
        observed_aura=AuraView(TARGET, components),
        current_damage_element=qualification,
        transformative_source_observation=transformative_observation,
        observed_quicken_state=quicken_state,
        catalyze_impact_qualification=(
            None
            if qualification is None
            else CatalyzeImpactQualification(
                target_impact_ref="impact:catalyze",
                damage_element=qualification,
                has_positive_scaling_coefficient=True,
            )
        ),
    )


def _component(
    aura_kind: AuraKind,
    amount: AuraAmount,
    links: tuple[ElementalStateLinkRef, ...] = (),
) -> AuraComponent:
    return AuraComponent(
        instance_ref=AuraInstanceRef(f"aura-instance:{aura_kind.value}"),
        aura_kind=aura_kind,
        contributions=(
            AuraContribution(
                AuraContributionRef(f"aura-contribution:{aura_kind.value}"),
                SOURCE,
                amount,
                SOURCE,
                0,
                0,
                0,
            ),
        ),
        decay_strength=AuraStrength.WEAK,
        decay_origin=SOURCE,
        created_frame=0,
        last_applied_frame=0,
        last_changed_frame=0,
        state_link_refs=links,
        decay_profile=(quicken_decay_profile(amount) if aura_kind is AuraKind.QUICKEN else None),
    )


def _quicken_state() -> QuickenState:
    return QuickenState(
        instance_ref=ReactionStateInstanceRef("reaction-state-instance:quicken"),
        subject_ref=TARGET,
        quicken_aura_link_ref=QUICKEN_LINK,
        created_by_occurrence_ref="interaction:quicken:0",
        last_updated_by_occurrence_ref="interaction:quicken:0",
        created_frame=0,
    )


def _transformative_observation() -> TransformativeSourceObservation:
    return TransformativeSourceObservation(
        source_ref=SOURCE,
        source_kind=TransformativeReactionSourceKind.CHARACTER,
        source_level=90,
        elemental_mastery=0.0,
        level_multiplier_table_key="character",
        level_multiplier=1446.853,
        source_observation_ref="observation:catalyze",
        source_owner_slot=1,
    )


def _reaction_keys(resolution) -> tuple[str, ...]:
    return tuple(
        occurrence.reaction_key
        for step in resolution.sequence.steps
        for occurrence in step.occurrences
    )
