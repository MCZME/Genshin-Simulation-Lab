from __future__ import annotations

from fractions import Fraction

import pytest

from genshin_sim.core.coordination.elemental_reaction import (
    BurningStateLinkBatchCoordinator,
    BurningStateLinkConflictError,
    ElementalStateFrameCoordinator,
    create_default_state_planning_adapter_registry,
)
from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
    ElementalSourceRef,
    ElementalStateLinkRef,
    ElementalSubjectRef,
    TransformativeReactionSourceKind,
)
from genshin_sim.core.impacts import StrikeType
from genshin_sim.core.systems.aura import (
    AuraApplicationRequest,
    AuraDecayMode,
    AuraLossPolicy,
    AuraRuntime,
    AuraStateLinkMutationRequest,
    AuraStrength,
    BurningAuraApplicationRequest,
)
from genshin_sim.core.systems.aura_icd import AuraIcdRuntime
from genshin_sim.core.systems.reaction import (
    BurningCycleRootWork,
    BurningStateTerminationIntent,
    BurningStateTerminationReason,
    CapturedTransformativeScalingBasis,
    ReactionDecisionStep,
    ReactionEvaluationRequest,
    ReactionRegistry,
    ReactionRuntime,
    ReactionSourceUnavailableNotice,
    ReactionSubjectUnavailableNotice,
    ReactionTriggerContext,
)

SOURCE = ElementalSourceRef("character:slot_1", "ability:burning")
SECOND_SOURCE = ElementalSourceRef("character:slot_2", "ability:burning")
TARGET = ElementalSubjectRef.target("target:burning")
LINK = ElementalStateLinkRef("elemental-state-link:burning")


def test_burning_frame_consumes_dendro_before_due_root_and_ends_atomically() -> None:
    aura_runtime, reaction_runtime, coordinator = _prepared_burning(AuraAmount(Fraction(2, 15)))

    at_fifteen = coordinator.normalize(None, 15)

    dendro = _dendro(aura_runtime)
    assert dendro.current_amount == AuraAmount(Fraction(1, 30))
    assert at_fifteen.reaction_managed_aura_adjustment_refs == (
        "reaction-state:reaction-state-instance:1:frame:15:burning:dendro-consumption",
    )
    assert len(at_fifteen.scheduled_roots) == 1
    root = at_fifteen.scheduled_roots[0]
    assert isinstance(root, BurningCycleRootWork)
    assert root.damage_tick_index == 1
    assert root.pyro_application_index == 1

    coordinator.normalize(None, 19)
    assert _dendro(aura_runtime).current_amount == AuraAmount(Fraction(1, 150))

    at_depletion = coordinator.normalize(None, 20)

    assert reaction_runtime.burning_state_for(TARGET) is None
    assert aura_runtime.view(TARGET).component_for(AuraKind.DENDRO) is None
    assert aura_runtime.view(TARGET).component_for(AuraKind.BURNING) is None
    assert at_depletion.scheduled_roots == ()
    assert at_depletion.reaction_managed_aura_adjustment_refs == (
        "reaction-state:reaction-state-instance:1:frame:20:burning:burning-cleanup",
        "reaction-state:reaction-state-instance:1:frame:20:burning:dendro-consumption",
    )
    assert reaction_runtime.next_required_frame() is None
    coordinator.normalize(None, 21)


def test_burning_frame_consumption_is_independent_of_contribution_count() -> None:
    aura_runtime, _, coordinator = _prepared_burning(
        AuraAmount(Fraction(2, 15)),
        second_dendro_amount=AuraAmount(Fraction(1, 15)),
    )

    coordinator.normalize(None, 1)

    dendro = _dendro(aura_runtime)
    primary = dendro.contribution_for(SOURCE)
    secondary = dendro.contribution_for(SECOND_SOURCE)
    assert primary is not None
    assert secondary is not None
    assert primary.remaining_amount == AuraAmount(Fraction(19, 150))
    assert secondary.remaining_amount == AuraAmount(Fraction(9, 150))
    assert dendro.current_amount == AuraAmount(Fraction(19, 150))


def test_burning_frame_jump_matches_stepwise_dendro_consumption() -> None:
    jump_aura, _, jump_coordinator = _prepared_burning(AuraAmount(Fraction(1, 5)))
    step_aura, _, step_coordinator = _prepared_burning(AuraAmount(Fraction(1, 5)))

    jump_coordinator.normalize(None, 10)
    for frame in range(1, 11):
        step_coordinator.normalize(None, frame)

    assert _dendro(jump_aura).current_amount == AuraAmount(Fraction(2, 15))
    assert _dendro(jump_aura).current_amount == _dendro(step_aura).current_amount


def test_burning_frame_rejects_broken_link_without_committing_dendro_consumption() -> None:
    aura_runtime, reaction_runtime, coordinator = _prepared_burning(AuraAmount(Fraction(2, 15)))
    remove_burning = aura_runtime.begin_batch(0, "burning-break-link")
    remove_burning.consume(
        interaction_id="burning-break-link",
        subject_ref=TARGET,
        aura_kind=AuraKind.BURNING,
        amount=AuraAmount(2),
    )
    aura_runtime.commit_prevalidated(remove_burning.seal())
    before_dendro = _dendro(aura_runtime)
    before_state = reaction_runtime.burning_state_for(TARGET)

    with pytest.raises(BurningStateLinkConflictError, match="完整的燃元素、类草 Aura 与 Link"):
        coordinator.normalize(None, 1)

    assert _dendro(aura_runtime) == before_dendro
    assert reaction_runtime.burning_state_for(TARGET) == before_state


def test_burning_depleted_termination_restores_surviving_dendro_decay() -> None:
    aura_runtime, reaction_runtime, _ = _prepared_burning(AuraAmount(Fraction(2, 15)))
    before = reaction_runtime.burning_state_for(TARGET)
    assert before is not None
    remove_burning = aura_runtime.begin_batch(0, "burning-depleted-external")
    remove_burning.consume(
        interaction_id="burning-depleted-external",
        subject_ref=TARGET,
        aura_kind=AuraKind.BURNING,
        amount=AuraAmount(2),
    )
    aura_runtime.commit_prevalidated(remove_burning.seal())

    aura_planner = aura_runtime.begin_batch(0, "burning-depleted-terminate")
    state_planner = reaction_runtime.begin_state_batch(0, "burning-depleted-terminate")
    request = ReactionEvaluationRequest(
        interaction_id="interaction:burning-depleted",
        target_impact_ref="impact:burning-depleted",
        frame=0,
        order=0,
        source_ref=SOURCE,
        subject_ref=TARGET,
        incoming_element=None,
        incoming_amount=AuraAmount.zero(),
        observed_aura=aura_runtime.view(TARGET),
        observed_burning_state=None,
        trigger_context=ReactionTriggerContext(strike_type=StrikeType.BLUNT),
    )
    intent = BurningStateTerminationIntent(
        intent_ref="intent:burning-depleted",
        subject_ref=TARGET,
        frame=0,
        expected_state_instance_ref=before.instance_ref,
        expected_state_revision=before.revision,
        reason=BurningStateTerminationReason.BURNING_DEPLETED,
    )
    create_default_state_planning_adapter_registry().plan_step(
        aura_planner=aura_planner,
        state_planner=state_planner,
        request=request,
        step=ReactionDecisionStep(
            0,
            ("reaction.burning",),
            (),
            (),
            (),
            (intent,),
        ),
    )
    BurningStateLinkBatchCoordinator(aura_runtime, reaction_runtime).commit_prevalidated(
        aura_planner.seal(),
        state_planner.seal(),
    )

    dendro = _dendro(aura_runtime)
    assert reaction_runtime.burning_state_for(TARGET) is None
    assert dendro.state_link_refs == ()
    assert dendro.decay_mode is AuraDecayMode.STANDARD
    before_amount = dendro.current_amount
    aura_runtime.update_frame(None, 1)
    restored = _dendro(aura_runtime)
    assert restored.current_amount < before_amount


def test_subject_unavailable_notice_ends_burning_atomically_and_is_idempotent() -> None:
    aura_runtime, reaction_runtime, coordinator = _prepared_burning(AuraAmount(Fraction(2, 15)))
    notice = ReactionSubjectUnavailableNotice("notice:subject-ended", TARGET, 0)

    assert coordinator.handle_reaction_lifecycle_notice(None, notice)

    dendro = _dendro(aura_runtime)
    assert reaction_runtime.burning_state_for(TARGET) is None
    assert aura_runtime.view(TARGET).component_for(AuraKind.BURNING) is None
    assert dendro.state_link_refs == ()
    assert dendro.decay_mode is AuraDecayMode.STANDARD
    version_after_first_notice = reaction_runtime.version

    assert not coordinator.handle_reaction_lifecycle_notice(None, notice)
    assert reaction_runtime.version == version_after_first_notice


def test_source_unavailable_notice_keeps_burning_state_and_captured_basis() -> None:
    aura_runtime, reaction_runtime, coordinator = _prepared_burning(AuraAmount(Fraction(2, 15)))
    before = reaction_runtime.burning_state_for(TARGET)
    assert before is not None
    notice = ReactionSourceUnavailableNotice("notice:source-ended", SOURCE, 0)

    assert not coordinator.handle_reaction_lifecycle_notice(None, notice)

    assert reaction_runtime.burning_state_for(TARGET) == before
    assert aura_runtime.view(TARGET).component_for(AuraKind.BURNING) is not None
    assert not coordinator.handle_reaction_lifecycle_notice(None, notice)


def _prepared_burning(
    dendro_amount: AuraAmount,
    *,
    second_dendro_amount: AuraAmount | None = None,
) -> tuple[AuraRuntime, ReactionRuntime, ElementalStateFrameCoordinator]:
    aura_runtime = AuraRuntime()
    reaction_runtime = ReactionRuntime(ReactionRegistry())
    aura_planner = aura_runtime.begin_batch(0, "burning-frame-establishment")
    aura_planner.apply(_dendro_application("aura:dendro:primary", SOURCE, dendro_amount, 0))
    if second_dendro_amount is not None:
        aura_planner.apply(
            _dendro_application("aura:dendro:secondary", SECOND_SOURCE, second_dendro_amount, 1)
        )
    link_order = 2 if second_dendro_amount is not None else 1
    aura_planner.mutate_state_links(
        AuraStateLinkMutationRequest(
            request_id="aura:dendro:burning-link",
            frame=0,
            order=link_order,
            target_ref=TARGET,
            aura_kind=AuraKind.DENDRO,
            add_link_refs=(LINK,),
            decay_mode=AuraDecayMode.REACTION_MANAGED,
        )
    )
    aura_planner.apply_burning(
        BurningAuraApplicationRequest(
            request_id="aura:burning",
            application_id="aura:burning:application",
            impact_ref="impact:burning",
            frame=0,
            order=link_order + 1,
            source_ref=SOURCE,
            target_ref=TARGET,
            state_link_ref=LINK,
            amount=AuraAmount(2),
        )
    )
    state_planner = reaction_runtime.begin_state_batch(0, "burning-frame-establishment")
    projected_dendro = aura_planner.view(TARGET).component_for(AuraKind.DENDRO)
    assert projected_dendro is not None
    state_planner.create_burning(
        subject_ref=TARGET,
        burning_aura_link_ref=LINK,
        dendro_like_link_refs=(LINK,),
        created_by_occurrence_ref="interaction:burning:occurrence:0",
        current_effect_owner=SOURCE,
        captured_scaling_basis=_basis(),
        next_dendro_like_depletion_frame=_depletion_frame(projected_dendro.current_amount),
        next_damage_tick_frame=15,
        next_damage_tick_index=1,
        next_pyro_application_frame=15,
        next_pyro_application_index=1,
    )
    BurningStateLinkBatchCoordinator(aura_runtime, reaction_runtime).commit_prevalidated(
        aura_planner.seal(),
        state_planner.seal(),
    )
    return (
        aura_runtime,
        reaction_runtime,
        ElementalStateFrameCoordinator(
            aura_runtime,
            AuraIcdRuntime(),
            reaction_runtime,
        ),
    )


def _dendro_application(
    request_id: str,
    source_ref: ElementalSourceRef,
    amount: AuraAmount,
    order: int,
) -> AuraApplicationRequest:
    return AuraApplicationRequest(
        request_id=request_id,
        application_id=f"{request_id}:application",
        impact_ref="impact:burning",
        frame=0,
        order=order,
        source_ref=source_ref,
        target_ref=TARGET,
        element=Element.DENDRO,
        base_strength=AuraStrength.WEAK,
        loss_policy=AuraLossPolicy.LOSSLESS,
        effective_raw_amount=amount,
    )


def _basis() -> CapturedTransformativeScalingBasis:
    return CapturedTransformativeScalingBasis(
        basis_ref="basis:burning",
        captured_frame=0,
        source_ref=SOURCE,
        source_kind=TransformativeReactionSourceKind.CHARACTER,
        source_level=90,
        elemental_mastery=0.0,
        reaction_bonus=0.0,
        reaction_profile_key="reaction_profile.burning.incoming_pyro_on_dendro",
        damage_profile_key="damage_profile.reaction.burning",
        level_multiplier_table_key="character",
        level_multiplier=1446.853,
        source_observation_ref="observation:burning",
        source_owner_slot=1,
    )


def _depletion_frame(amount: AuraAmount) -> int:
    return int(-(-amount.value // Fraction(1, 150)))


def _dendro(runtime: AuraRuntime):
    dendro = runtime.view(TARGET).component_for(AuraKind.DENDRO)
    assert dendro is not None
    return dendro
