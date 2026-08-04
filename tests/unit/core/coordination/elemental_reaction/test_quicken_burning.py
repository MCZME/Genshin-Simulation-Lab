"""激元素作为燃烧类草 Component 的闭环测试。"""

from __future__ import annotations

from fractions import Fraction

from genshin_sim.core.coordination.elemental_reaction import (
    BurningStateLinkBatchCoordinator,
    ElementalStateFrameCoordinator,
    create_default_state_planning_adapter_registry,
    validate_elemental_state_links,
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
from genshin_sim.core.systems.aura import (
    AuraContributionRef,
    AuraDecayMode,
    AuraRuntime,
    AuraStrength,
    QuickenAuraApplicationRequest,
)
from genshin_sim.core.systems.aura_icd import AuraIcdRuntime
from genshin_sim.core.systems.reaction import (
    ReactionEvaluationRequest,
    ReactionRuntime,
    TransformativeSourceObservation,
    create_default_reaction_bootstrap,
)

SOURCE = ElementalSourceRef("character:slot_1", "ability:quicken")
TARGET = ElementalSubjectRef.target("target:quicken-burning")
QUICKEN_LINK = ElementalStateLinkRef("elemental-state-link:quicken")


def test_quicken_enters_burning_and_is_consumed_as_the_only_dendro_like_component() -> None:
    aura_runtime = AuraRuntime()
    reaction_runtime = create_default_reaction_bootstrap().create_runtime()
    _establish_quicken(aura_runtime, reaction_runtime)

    request = _pyro_request(aura_runtime, reaction_runtime)
    resolution = reaction_runtime.evaluate(request)
    step = resolution.sequence.steps[0]
    assert resolution.occurrence is not None
    assert resolution.occurrence.direction_key == "incoming_pyro_on_quicken"

    aura_planner = aura_runtime.begin_batch(0, "quicken-burning")
    state_planner = reaction_runtime.begin_state_batch(0, "quicken-burning")
    create_default_state_planning_adapter_registry().plan_step(
        aura_planner=aura_planner,
        state_planner=state_planner,
        request=request,
        step=step,
        elemental_strength=AuraStrength.WEAK,
    )
    aura_plan = aura_planner.seal()
    state_plan = state_planner.seal()
    validate_elemental_state_links(
        aura_plan.replacements,
        _projected_states(reaction_runtime, state_plan),
    )
    BurningStateLinkBatchCoordinator(aura_runtime, reaction_runtime).commit_prevalidated(
        aura_plan,
        state_plan,
    )

    burning_state = reaction_runtime.burning_state_for(TARGET)
    quicken_state = reaction_runtime.quicken_state_for(TARGET)
    quicken = aura_runtime.view(TARGET).component_for(AuraKind.QUICKEN)
    assert burning_state is not None
    assert quicken_state is not None
    assert quicken is not None
    assert quicken.decay_mode is AuraDecayMode.REACTION_MANAGED
    assert quicken.state_link_refs == tuple(
        sorted(
            (QUICKEN_LINK, burning_state.burning_aura_link_ref),
            key=lambda item: item.link_key,
        )
    )
    assert burning_state.dendro_like_link_refs == quicken.state_link_refs

    coordinator = ElementalStateFrameCoordinator(
        aura_runtime,
        AuraIcdRuntime(),
        reaction_runtime,
    )
    coordinator.normalize(None, 15)
    assert aura_runtime.view(TARGET).component_for(AuraKind.QUICKEN).current_amount == AuraAmount(
        Fraction(1, 10)
    )  # type: ignore[union-attr]
    assert reaction_runtime.quicken_state_for(TARGET) is not None

    coordinator.normalize(None, 30)
    assert aura_runtime.view(TARGET).component_for(AuraKind.QUICKEN) is None
    assert aura_runtime.view(TARGET).component_for(AuraKind.BURNING) is None
    assert reaction_runtime.quicken_state_for(TARGET) is None
    assert reaction_runtime.burning_state_for(TARGET) is None


def _establish_quicken(aura_runtime: AuraRuntime, reaction_runtime: ReactionRuntime) -> None:
    aura_planner = aura_runtime.begin_batch(0, "quicken")
    aura_planner.apply_quicken(
        QuickenAuraApplicationRequest(
            request_id="aura:quicken",
            application_id="application:quicken",
            impact_ref="impact:quicken",
            frame=0,
            order=0,
            source_ref=SOURCE,
            target_ref=TARGET,
            state_link_ref=QUICKEN_LINK,
            amount=AuraAmount(Fraction(1, 5)),
            contribution_ref=AuraContributionRef("occurrence:quicken:contribution"),
        )
    )
    aura_runtime.commit_prevalidated(aura_planner.seal())
    state_planner = reaction_runtime.begin_state_batch(0, "quicken")
    state_planner.create_quicken(
        subject_ref=TARGET,
        quicken_aura_link_ref=QUICKEN_LINK,
        created_by_occurrence_ref="occurrence:quicken",
    )
    reaction_runtime.commit_prevalidated_state_plan(state_planner.seal())


def _pyro_request(
    aura_runtime: AuraRuntime,
    reaction_runtime: ReactionRuntime,
) -> ReactionEvaluationRequest:
    return ReactionEvaluationRequest(
        interaction_id="interaction:quicken-burning",
        target_impact_ref="impact:quicken-burning",
        frame=0,
        order=0,
        source_ref=SOURCE,
        subject_ref=TARGET,
        incoming_element=Element.PYRO,
        incoming_amount=AuraAmount.one(),
        observed_aura=aura_runtime.view(TARGET),
        transformative_source_observation=TransformativeSourceObservation(
            source_ref=SOURCE,
            source_kind=TransformativeReactionSourceKind.CHARACTER,
            source_level=90,
            elemental_mastery=0.0,
            level_multiplier_table_key="character",
            level_multiplier=1446.853,
            source_observation_ref="observation:quicken-burning",
            source_owner_slot=1,
        ),
        observed_quicken_state=reaction_runtime.quicken_state_for(TARGET),
    )


def _projected_states(runtime: ReactionRuntime, plan) -> tuple:
    states = {state.slot_key: state for state in runtime.state_records}
    for slot_key in plan.removed_slot_keys:
        states.pop(slot_key, None)
    for state in plan.replacement_records:
        states[state.slot_key] = state
    return tuple(states.values())
