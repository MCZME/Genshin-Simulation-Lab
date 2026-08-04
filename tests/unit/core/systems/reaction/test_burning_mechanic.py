from __future__ import annotations

from fractions import Fraction
from typing import cast

import pytest

from genshin_sim.core.coordination.elemental_reaction import (
    ElementalInteractionCoordinator,
    ElementalStateFrameCoordinator,
    create_default_state_planning_adapter_registry,
    validate_burning_state_links,
)
from genshin_sim.core.coordination.elemental_reaction.observers import (
    CharacterTransformativeSourceObserver,
)
from genshin_sim.core.coordination.elemental_reaction.protocols import DamageImpactPlanningPort
from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
    ElementalSourceRef,
    ElementalStateLinkRef,
    ElementalSubjectRef,
    TransformativeReactionSourceKind,
)
from genshin_sim.core.entity_states import (
    CharacterRuntimeState,
    TargetRuntimeCollection,
    TargetRuntimeState,
)
from genshin_sim.core.impacts import ElementalApplicationSpec, ImpactKind, ImpactRequest
from genshin_sim.core.simulation import SimulationContext, TeamRuntimeState
from genshin_sim.core.space import Space, SpatialEntity, SpatialEntityKind, Vector3
from genshin_sim.core.space.runtime import SpaceRuntime
from genshin_sim.core.systems.aura import (
    AuraApplicationRequest,
    AuraRuntime,
    AuraStrength,
    BurningAuraApplicationRequest,
    BurningAuraEstablishmentRequest,
)
from genshin_sim.core.systems.aura_icd import AuraIcdRuntime
from genshin_sim.core.systems.reaction import (
    AreaAroundSubjectSelection,
    BurningStateEstablishmentIntent,
    BurningStateMaintenanceIntent,
    BurningStateTerminationIntent,
    BurningStateTerminationReason,
    ReactionDefinition,
    ReactionEvaluationRequest,
    ReactionRegistry,
    ReactionRuntime,
    ReactionSelectionError,
    ReactionStateRecord,
    TransformativeSourceObservation,
)
from genshin_sim.core.systems.reaction.mechanics.burning import burning_definition
from genshin_sim.core.systems.reaction.mechanics.melt import melt_definition
from genshin_sim.core.systems.reaction.mechanics.vaporize import vaporize_definition

SOURCE = ElementalSourceRef("character:slot_1", "ability:burning")
UPDATED_SOURCE = ElementalSourceRef("character:slot_2", "ability:burning")
TARGET = ElementalSubjectRef.target("target:burning")


@pytest.mark.parametrize(
    ("first", "incoming"),
    ((Element.DENDRO, Element.PYRO), (Element.PYRO, Element.DENDRO)),
)
def test_burning_establishment_atomically_keeps_first_aura_and_creates_state(
    first: Element,
    incoming: Element,
) -> None:
    aura_runtime = AuraRuntime()
    aura_runtime.apply(_aura_request("aura:first", first, SOURCE))
    reaction_runtime = ReactionRuntime(ReactionRegistry((burning_definition(),)))
    aura_planner = aura_runtime.begin_batch(0, "burning-establishment")
    state_planner = reaction_runtime.begin_state_batch(0, "burning-establishment")
    request = _evaluation_request(
        source_ref=SOURCE,
        incoming=incoming,
        aura=aura_runtime.view(TARGET),
    )

    resolution = reaction_runtime.evaluate(request)

    assert resolution.occurrence is not None
    assert resolution.occurrence.transition.incoming_consumed.is_zero
    assert resolution.occurrence.transition.aura_consumed.is_zero
    step = resolution.sequence.steps[0]
    assert isinstance(step.state_planning_intents[0], BurningStateEstablishmentIntent)
    effect_group = resolution.occurrence.effect_groups[0]
    assert isinstance(effect_group.target_selection, AreaAroundSubjectSelection)
    assert effect_group.target_selection.radius == 1.0
    assert effect_group.target_selection.include_anchor

    create_default_state_planning_adapter_registry().plan_step(
        aura_planner=aura_planner,
        state_planner=state_planner,
        request=request,
        step=step,
        elemental_strength=AuraStrength.WEAK,
    )
    aura_plan = aura_planner.seal()
    state_plan = state_planner.seal()
    validate_burning_state_links(
        aura_plan.replacements,
        _projected_states(reaction_runtime, state_plan),
    )
    aura_runtime.commit_prevalidated(aura_plan)
    reaction_runtime.commit_prevalidated_state_plan(state_plan)

    aura = aura_runtime.view(TARGET)
    assert aura.component_for(AuraKind.BURNING).current_amount == AuraAmount(2)  # type: ignore[union-attr]
    assert aura.component_for(AuraKind.DENDRO).current_amount == AuraAmount(Fraction(4, 5))  # type: ignore[union-attr]
    if incoming is Element.PYRO:
        assert aura.component_for(AuraKind.PYRO).current_amount == AuraAmount(Fraction(4, 5))  # type: ignore[union-attr]
    state = reaction_runtime.burning_state_for(TARGET)
    assert state is not None
    assert state.next_dendro_like_depletion_frame == 120
    assert state.next_damage_tick_frame == 15
    assert state.next_pyro_application_frame == 15


def test_burning_maintenance_has_no_occurrence_and_preserves_cycle_cursors() -> None:
    aura_runtime, reaction_runtime = _established_burning()
    aura_runtime.update_frame(None, 1)
    reaction_runtime.update_frame(None, 1)
    before = reaction_runtime.burning_state_for(TARGET)
    assert before is not None
    aura_planner = aura_runtime.begin_batch(1, "burning-maintenance")
    state_planner = reaction_runtime.begin_state_batch(1, "burning-maintenance")
    request = _evaluation_request(
        source_ref=UPDATED_SOURCE,
        incoming=Element.PYRO,
        aura=aura_runtime.view(TARGET),
        frame=1,
        observed_burning_state=before,
    )

    resolution = reaction_runtime.evaluate(request)

    assert resolution.occurrence is None
    step = resolution.sequence.steps[0]
    assert isinstance(step.state_planning_intents[0], BurningStateMaintenanceIntent)
    create_default_state_planning_adapter_registry().plan_step(
        aura_planner=aura_planner,
        state_planner=state_planner,
        request=request,
        step=step,
        elemental_strength=AuraStrength.WEAK,
    )
    aura_plan = aura_planner.seal()
    state_plan = state_planner.seal()
    validate_burning_state_links(
        aura_plan.replacements,
        _projected_states(reaction_runtime, state_plan),
    )
    aura_runtime.commit_prevalidated(aura_plan)
    reaction_runtime.commit_prevalidated_state_plan(state_plan)

    after = reaction_runtime.burning_state_for(TARGET)
    assert after is not None
    assert after.instance_ref == before.instance_ref
    assert after.created_by_occurrence_ref == before.created_by_occurrence_ref
    assert after.current_effect_owner == UPDATED_SOURCE
    assert after.revision == before.revision + 1
    assert after.next_damage_tick_frame == before.next_damage_tick_frame
    assert after.next_damage_tick_index == before.next_damage_tick_index
    assert after.next_pyro_application_frame == before.next_pyro_application_frame
    assert after.next_pyro_application_index == before.next_pyro_application_index
    assert after.next_dendro_like_depletion_frame == 121


def test_dendro_maintenance_survives_ordinary_pyro_depletion() -> None:
    aura_runtime, reaction_runtime = _established_burning()
    remove_pyro = aura_runtime.begin_batch(0, "burning-remove-ordinary-pyro")
    remove_pyro.consume(
        interaction_id="burning-remove-ordinary-pyro",
        subject_ref=TARGET,
        aura_kind=AuraKind.PYRO,
        amount=AuraAmount(Fraction(4, 5)),
    )
    aura_runtime.commit_prevalidated(remove_pyro.seal())
    before = reaction_runtime.burning_state_for(TARGET)
    assert before is not None
    assert aura_runtime.view(TARGET).component_for(AuraKind.PYRO) is None

    resolution = reaction_runtime.evaluate(
        _evaluation_request(
            source_ref=UPDATED_SOURCE,
            incoming=Element.DENDRO,
            aura=aura_runtime.view(TARGET),
            observed_burning_state=before,
        )
    )

    assert resolution.occurrence is None
    step = resolution.sequence.steps[0]
    assert isinstance(step.state_planning_intents[0], BurningStateMaintenanceIntent)
    aura_planner = aura_runtime.begin_batch(0, "burning-dendro-maintenance")
    state_planner = reaction_runtime.begin_state_batch(0, "burning-dendro-maintenance")
    create_default_state_planning_adapter_registry().plan_step(
        aura_planner=aura_planner,
        state_planner=state_planner,
        request=resolution.request,
        step=step,
        elemental_strength=AuraStrength.WEAK,
    )
    aura_runtime.commit_prevalidated(aura_planner.seal())
    reaction_runtime.commit_prevalidated_state_plan(state_planner.seal())

    after = reaction_runtime.burning_state_for(TARGET)
    assert after is not None
    assert after.current_effect_owner == UPDATED_SOURCE
    assert after.revision == before.revision + 1
    assert after.next_damage_tick_frame == before.next_damage_tick_frame
    assert after.next_pyro_application_frame == before.next_pyro_application_frame


def test_periodic_pyro_observation_does_not_create_a_maintenance_intent() -> None:
    aura_runtime, reaction_runtime = _established_burning()
    state = reaction_runtime.burning_state_for(TARGET)
    assert state is not None

    resolution = reaction_runtime.evaluate(
        _evaluation_request(
            source_ref=UPDATED_SOURCE,
            incoming=Element.PYRO,
            aura=aura_runtime.view(TARGET),
            observed_burning_state=state,
            state_maintenance_allowed=False,
        )
    )

    assert resolution.occurrence is None
    assert not resolution.sequence.steps


def test_burning_establishment_request_rejects_non_fixed_burning_amount() -> None:
    incoming = _aura_request("aura:incoming", Element.PYRO, SOURCE)
    with pytest.raises(ValueError, match="固定 2 GU"):
        BurningAuraEstablishmentRequest(
            incoming,
            BurningAuraApplicationRequest(
                request_id="aura:burning",
                application_id="application:burning",
                impact_ref="impact:burning",
                frame=0,
                order=1,
                source_ref=SOURCE,
                target_ref=TARGET,
                state_link_ref=ElementalStateLinkRef("elemental-state-link:test"),
                amount=AuraAmount.one(),
            ),
        )


def test_elemental_interaction_coordinator_consumes_burning_intent_without_key_branch() -> None:
    target_id = "burning-target"
    target_entity_id = f"target:{target_id}"
    target = TargetRuntimeState(target_id, spatial_entity_id=target_entity_id)
    context = SimulationContext(
        space_runtime=SpaceRuntime(
            space=Space(
                (
                    SpatialEntity(
                        target_entity_id,
                        SpatialEntityKind.TARGET,
                        Vector3(),
                    ),
                )
            ),
            team_state=TeamRuntimeState((CharacterRuntimeState(1, "character:test", 90),)),
            targets=TargetRuntimeCollection((target,)),
        )
    )
    aura_runtime = AuraRuntime()
    icd_runtime = AuraIcdRuntime()
    reaction_runtime = ReactionRuntime(ReactionRegistry((burning_definition(),)))
    frame_coordinator = ElementalStateFrameCoordinator(
        aura_runtime,
        icd_runtime,
        reaction_runtime,
    )
    coordinator = ElementalInteractionCoordinator(
        aura_runtime=aura_runtime,
        icd_runtime=icd_runtime,
        reaction_runtime=reaction_runtime,
        damage_handler=cast(DamageImpactPlanningPort, _NoDamageHandler()),
        frame_coordinator=frame_coordinator,
        transformative_source_observer=cast(
            CharacterTransformativeSourceObserver,
            _FixedTransformativeSourceObserver(),
        ),
    )
    subject_ref = ElementalSubjectRef.target(target_entity_id)
    aura_runtime.apply(
        AuraApplicationRequest(
            request_id="aura:first-dendro",
            application_id="application:first-dendro",
            impact_ref="impact:first-dendro",
            frame=0,
            order=0,
            source_ref=SOURCE,
            target_ref=subject_ref,
            element=Element.DENDRO,
            base_strength=AuraStrength.WEAK,
        )
    )

    record = coordinator.handle_aura_impact(
        context,
        ImpactRequest(
            frame=0,
            kind=ImpactKind.APPLY_AURA,
            impact_key="test.burning.pyro",
            owner_slot=1,
            request_id="root:burning",
            target_refs=(target_id,),
            elemental_application_spec=ElementalApplicationSpec(
                impact_ref="impact:burning",
                element=Element.PYRO,
                elemental_strength=AuraStrength.WEAK,
            ),
        ),
    )

    state = reaction_runtime.burning_state_for(subject_ref)
    assert state is not None
    assert record.reaction_occurrence_refs == (state.created_by_occurrence_ref,)
    assert record.reaction_decision_steps[0].state_planning_intent_refs == (
        f"{state.created_by_occurrence_ref}:burning-establishment",
    )
    assert aura_runtime.view(subject_ref).component_for(AuraKind.BURNING) is not None


def test_cryo_parallel_consumes_burning_and_pyro_then_preserves_pyro_dendro() -> None:
    target_id = "burning-target"
    target_entity_id = f"target:{target_id}"
    target = TargetRuntimeState(target_id, spatial_entity_id=target_entity_id)
    context = SimulationContext(
        space_runtime=SpaceRuntime(
            space=Space(
                (
                    SpatialEntity(
                        target_entity_id,
                        SpatialEntityKind.TARGET,
                        Vector3(),
                    ),
                )
            ),
            team_state=TeamRuntimeState((CharacterRuntimeState(1, "character:test", 90),)),
            targets=TargetRuntimeCollection((target,)),
        )
    )
    aura_runtime = AuraRuntime()
    icd_runtime = AuraIcdRuntime()
    reaction_runtime = ReactionRuntime(ReactionRegistry((burning_definition(), melt_definition())))
    frame_coordinator = ElementalStateFrameCoordinator(
        aura_runtime,
        icd_runtime,
        reaction_runtime,
    )
    coordinator = ElementalInteractionCoordinator(
        aura_runtime=aura_runtime,
        icd_runtime=icd_runtime,
        reaction_runtime=reaction_runtime,
        damage_handler=cast(DamageImpactPlanningPort, _NoDamageHandler()),
        frame_coordinator=frame_coordinator,
        transformative_source_observer=cast(
            CharacterTransformativeSourceObserver,
            _FixedTransformativeSourceObserver(),
        ),
    )
    subject_ref = ElementalSubjectRef.target(target_entity_id)
    aura_runtime.apply(
        AuraApplicationRequest(
            request_id="aura:first-dendro",
            application_id="application:first-dendro",
            impact_ref="impact:first-dendro",
            frame=0,
            order=0,
            source_ref=SOURCE,
            target_ref=subject_ref,
            element=Element.DENDRO,
            base_strength=AuraStrength.WEAK,
        )
    )
    coordinator.handle_aura_impact(
        context,
        _aura_impact_request(
            request_id="root:burning",
            impact_ref="impact:burning",
            element=Element.PYRO,
        ),
    )
    adjust = aura_runtime.begin_batch(0, "burning-parallel-golden-case-adjust")
    adjust.consume(
        interaction_id="burning-parallel-golden-case-adjust:burning",
        subject_ref=subject_ref,
        aura_kind=AuraKind.BURNING,
        amount=AuraAmount(Fraction(3, 2)),
    )
    adjust.consume(
        interaction_id="burning-parallel-golden-case-adjust:pyro",
        subject_ref=subject_ref,
        aura_kind=AuraKind.PYRO,
        amount=AuraAmount(Fraction(1, 10)),
    )
    aura_runtime.commit_prevalidated(adjust.seal())

    record = coordinator.handle_aura_impact(
        context,
        _aura_impact_request(
            request_id="root:cryo",
            impact_ref="impact:cryo",
            element=Element.CRYO,
        ),
    )

    assert len(record.reaction_occurrence_refs) == 1
    assert record.reaction_occurrence_refs[0].endswith(":occurrence:0")
    aura = aura_runtime.view(subject_ref)
    assert aura.component_for(AuraKind.BURNING) is None
    assert aura.component_for(AuraKind.PYRO).current_amount == AuraAmount(Fraction(1, 5))  # type: ignore[union-attr]
    assert aura.component_for(AuraKind.DENDRO).current_amount == AuraAmount(Fraction(4, 5))  # type: ignore[union-attr]
    assert reaction_runtime.burning_state_for(subject_ref) is None


def test_residual_pyro_dendro_can_reestablish_burning_on_new_application() -> None:
    target_id = "burning-target"
    target_entity_id = f"target:{target_id}"
    target = TargetRuntimeState(target_id, spatial_entity_id=target_entity_id)
    context = SimulationContext(
        space_runtime=SpaceRuntime(
            space=Space(
                (
                    SpatialEntity(
                        target_entity_id,
                        SpatialEntityKind.TARGET,
                        Vector3(),
                    ),
                )
            ),
            team_state=TeamRuntimeState((CharacterRuntimeState(1, "character:test", 90),)),
            targets=TargetRuntimeCollection((target,)),
        )
    )
    aura_runtime = AuraRuntime()
    icd_runtime = AuraIcdRuntime()
    reaction_runtime = ReactionRuntime(ReactionRegistry((burning_definition(), melt_definition())))
    frame_coordinator = ElementalStateFrameCoordinator(
        aura_runtime,
        icd_runtime,
        reaction_runtime,
    )
    coordinator = ElementalInteractionCoordinator(
        aura_runtime=aura_runtime,
        icd_runtime=icd_runtime,
        reaction_runtime=reaction_runtime,
        damage_handler=cast(DamageImpactPlanningPort, _NoDamageHandler()),
        frame_coordinator=frame_coordinator,
        transformative_source_observer=cast(
            CharacterTransformativeSourceObserver,
            _FixedTransformativeSourceObserver(),
        ),
    )
    subject_ref = ElementalSubjectRef.target(target_entity_id)
    aura_runtime.apply(
        AuraApplicationRequest(
            request_id="aura:first-dendro",
            application_id="application:first-dendro",
            impact_ref="impact:first-dendro",
            frame=0,
            order=0,
            source_ref=SOURCE,
            target_ref=subject_ref,
            element=Element.DENDRO,
            base_strength=AuraStrength.WEAK,
        )
    )
    coordinator.handle_aura_impact(
        context,
        _aura_impact_request(
            request_id="root:burning",
            impact_ref="impact:burning",
            element=Element.PYRO,
        ),
    )
    adjust = aura_runtime.begin_batch(0, "burning-reestablish-adjust")
    adjust.consume(
        interaction_id="burning-reestablish-adjust:burning",
        subject_ref=subject_ref,
        aura_kind=AuraKind.BURNING,
        amount=AuraAmount(Fraction(3, 2)),
    )
    adjust.consume(
        interaction_id="burning-reestablish-adjust:pyro",
        subject_ref=subject_ref,
        aura_kind=AuraKind.PYRO,
        amount=AuraAmount(Fraction(1, 10)),
    )
    aura_runtime.commit_prevalidated(adjust.seal())
    coordinator.handle_aura_impact(
        context,
        _aura_impact_request(
            request_id="root:cryo",
            impact_ref="impact:cryo",
            element=Element.CRYO,
        ),
    )
    residual = aura_runtime.view(subject_ref)
    assert residual.component_for(AuraKind.BURNING) is None
    assert residual.component_for(AuraKind.PYRO) is not None
    assert residual.component_for(AuraKind.DENDRO) is not None
    assert reaction_runtime.burning_state_for(subject_ref) is None

    record = coordinator.handle_aura_impact(
        context,
        _aura_impact_request(
            request_id="root:reestablish",
            impact_ref="impact:reestablish",
            element=Element.PYRO,
        ),
    )

    state = reaction_runtime.burning_state_for(subject_ref)
    aura = aura_runtime.view(subject_ref)
    burning = aura.component_for(AuraKind.BURNING)
    dendro = aura.component_for(AuraKind.DENDRO)
    assert state is not None
    assert record.reaction_occurrence_refs == (state.created_by_occurrence_ref,)
    assert burning is not None
    assert burning.current_amount == AuraAmount(2)
    assert dendro is not None
    assert dendro.decay_mode.value == "reaction_managed"
    assert dendro.state_link_refs == (state.burning_aura_link_ref,)
    assert aura.component_for(AuraKind.PYRO) is not None


def test_parallel_cryo_residual_is_planned_as_dendro_cryo_coexistence() -> None:
    aura_runtime, reaction_runtime = _established_burning(reaction_definitions=(melt_definition(),))
    adjust = aura_runtime.begin_batch(0, "burning-cryo-residual-adjust")
    adjust.consume(
        interaction_id="burning-cryo-residual-adjust:burning",
        subject_ref=TARGET,
        aura_kind=AuraKind.BURNING,
        amount=AuraAmount(Fraction(9, 5)),
    )
    adjust.consume(
        interaction_id="burning-cryo-residual-adjust:pyro",
        subject_ref=TARGET,
        aura_kind=AuraKind.PYRO,
        amount=AuraAmount(Fraction(1, 2)),
    )
    aura_runtime.commit_prevalidated(adjust.seal())
    state = reaction_runtime.burning_state_for(TARGET)
    assert state is not None

    resolution = reaction_runtime.evaluate(
        _evaluation_request(
            source_ref=UPDATED_SOURCE,
            incoming=Element.CRYO,
            aura=aura_runtime.view(TARGET),
            observed_burning_state=state,
        )
    )

    occurrence = resolution.occurrence
    assert occurrence is not None
    parallel = occurrence.parallel_aura_consumption
    assert parallel is not None
    assert parallel.shared_incoming_consumed == AuraAmount(Fraction(3, 5))
    assert parallel.shared_incoming_remaining == AuraAmount(Fraction(2, 5))
    assert occurrence.persistent_incoming_aura_application is not None
    termination = resolution.sequence.steps[0].state_planning_intents[-1]
    assert isinstance(termination, BurningStateTerminationIntent)
    assert termination.reason is BurningStateTerminationReason.BURNING_DEPLETED


def test_parallel_hydro_residual_fails_before_any_aura_or_state_mutation() -> None:
    aura_runtime, reaction_runtime = _established_burning(
        reaction_definitions=(vaporize_definition(),)
    )
    adjust = aura_runtime.begin_batch(0, "burning-hydro-residual-adjust")
    adjust.consume(
        interaction_id="burning-hydro-residual-adjust:burning",
        subject_ref=TARGET,
        aura_kind=AuraKind.BURNING,
        amount=AuraAmount(Fraction(9, 5)),
    )
    aura_runtime.commit_prevalidated(adjust.seal())
    before_aura = aura_runtime.view(TARGET)
    before_state = reaction_runtime.burning_state_for(TARGET)

    with pytest.raises(ReactionSelectionError, match="剩余水雷预算"):
        reaction_runtime.evaluate(
            _evaluation_request(
                source_ref=UPDATED_SOURCE,
                incoming=Element.HYDRO,
                aura=before_aura,
                observed_burning_state=before_state,
            )
        )

    assert aura_runtime.view(TARGET) == before_aura
    assert reaction_runtime.burning_state_for(TARGET) == before_state


def _established_burning(
    *,
    reaction_definitions: tuple[ReactionDefinition, ...] = (),
) -> tuple[AuraRuntime, ReactionRuntime]:
    aura_runtime = AuraRuntime()
    aura_runtime.apply(_aura_request("aura:first", Element.DENDRO, SOURCE))
    reaction_runtime = ReactionRuntime(
        ReactionRegistry((burning_definition(), *reaction_definitions))
    )
    aura_planner = aura_runtime.begin_batch(0, "burning-establishment")
    state_planner = reaction_runtime.begin_state_batch(0, "burning-establishment")
    request = _evaluation_request(
        source_ref=SOURCE,
        incoming=Element.PYRO,
        aura=aura_runtime.view(TARGET),
    )
    resolution = reaction_runtime.evaluate(request)
    create_default_state_planning_adapter_registry().plan_step(
        aura_planner=aura_planner,
        state_planner=state_planner,
        request=request,
        step=resolution.sequence.steps[0],
        elemental_strength=AuraStrength.WEAK,
    )
    aura_plan = aura_planner.seal()
    state_plan = state_planner.seal()
    aura_runtime.commit_prevalidated(aura_plan)
    reaction_runtime.commit_prevalidated_state_plan(state_plan)
    return aura_runtime, reaction_runtime


def _aura_request(
    request_id: str,
    element: Element,
    source_ref: ElementalSourceRef,
) -> AuraApplicationRequest:
    return AuraApplicationRequest(
        request_id=request_id,
        application_id=f"{request_id}:application",
        impact_ref="impact:burning",
        frame=0,
        order=0,
        source_ref=source_ref,
        target_ref=TARGET,
        element=element,
        base_strength=AuraStrength.WEAK,
    )


def _aura_impact_request(
    *,
    request_id: str,
    impact_ref: str,
    element: Element,
) -> ImpactRequest:
    return ImpactRequest(
        frame=0,
        kind=ImpactKind.APPLY_AURA,
        impact_key=f"test.burning.{element.value}",
        owner_slot=1,
        request_id=request_id,
        target_refs=("burning-target",),
        elemental_application_spec=ElementalApplicationSpec(
            impact_ref=impact_ref,
            element=element,
            elemental_strength=AuraStrength.WEAK,
        ),
    )


def _evaluation_request(
    *,
    source_ref: ElementalSourceRef,
    incoming: Element,
    aura,
    frame: int = 0,
    observed_burning_state=None,
    state_maintenance_allowed: bool = True,
) -> ReactionEvaluationRequest:
    return ReactionEvaluationRequest(
        interaction_id=f"interaction:{source_ref.source_key}:{frame}",
        target_impact_ref="impact:burning",
        frame=frame,
        order=0,
        source_ref=source_ref,
        subject_ref=TARGET,
        incoming_element=incoming,
        incoming_amount=AuraAmount.one(),
        observed_aura=aura,
        transformative_source_observation=TransformativeSourceObservation(
            source_ref=source_ref,
            source_kind=TransformativeReactionSourceKind.CHARACTER,
            source_level=90,
            elemental_mastery=100.0,
            level_multiplier_table_key="character",
            level_multiplier=1446.853,
            source_observation_ref=f"observation:{source_ref.source_key}:{frame}",
            source_owner_slot=1,
        ),
        observed_burning_state=observed_burning_state,
        state_maintenance_allowed=state_maintenance_allowed,
    )


def _projected_states(runtime: ReactionRuntime, plan) -> tuple[ReactionStateRecord, ...]:
    states = {state.slot_key: state for state in runtime.state_records}
    for slot_key in plan.removed_slot_keys:
        states.pop(slot_key, None)
    for state in plan.replacement_records:
        states[state.slot_key] = state
    return tuple(states.values())


class _NoDamageHandler:
    def prepare_impact_request(self, *args, **kwargs):  # pragma: no cover - aura-only case
        raise AssertionError("纯 Aura 燃烧建立不应准备直接伤害")

    def commit_prepared_records(self, records):  # pragma: no cover - aura-only case
        raise AssertionError("纯 Aura 燃烧建立不应提交直接伤害")

    def publish_committed_facts(self, context, records):  # pragma: no cover - aura-only case
        raise AssertionError("纯 Aura 燃烧建立不应发布直接伤害")


class _FixedTransformativeSourceObserver:
    def observe(
        self,
        *,
        frame: int,
        source_ref: ElementalSourceRef,
        owner_slot: int,
        source_level: int,
        observation_ref: str,
    ) -> TransformativeSourceObservation:
        return TransformativeSourceObservation(
            source_ref=source_ref,
            source_kind=TransformativeReactionSourceKind.CHARACTER,
            source_level=source_level,
            elemental_mastery=0.0,
            level_multiplier_table_key="character",
            level_multiplier=1446.853,
            source_observation_ref=observation_ref,
            source_owner_slot=owner_slot,
        )
