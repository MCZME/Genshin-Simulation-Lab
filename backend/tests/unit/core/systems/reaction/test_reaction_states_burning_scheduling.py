from __future__ import annotations

from typing import cast

from genshin_sim.core.elements import (
    AuraAmount,
    Element,
    ElementalSourceRef,
    ElementalStateLinkRef,
    ElementalSubjectRef,
)
from genshin_sim.core.events import EventType, GameEvent
from genshin_sim.core.simulation import SimulationContext
from genshin_sim.core.systems.aura import (
    AuraStrength,
)
from genshin_sim.core.systems.reaction import (
    AreaAroundSubjectSelection,
    BurningCycleRootWork,
    CurrentSubjectSelection,
    GeneratedDamageImpactEffect,
    ReactionGeneratedImpact,
    ReactionGeneratedImpactBatch,
    create_default_reaction_bootstrap,
    create_default_scheduled_reaction_root_adapter_registry,
)
from genshin_sim.core.systems.reaction.mechanics.burning import (
    BURNING_PYRO_APPLICATION_AMOUNT,
    BURNING_PYRO_AURA_APPLICATION_PROFILE_KEY,
    burning_pyro_aura_application_profile,
)
from tests.helpers.reactions import burning_basis

SOURCE = ElementalSourceRef("character:slot_1")
TARGET = ElementalSubjectRef.target("target:target_1")
LINK = ElementalStateLinkRef("elemental-state-link:test")


def test_burning_state_fact_serializes_links_and_all_scheduling_fields():
    context = SimulationContext()
    runtime = create_default_reaction_bootstrap().create_runtime()
    planner = runtime.begin_state_batch(0, "burning-event")
    planner.create_burning(
        subject_ref=TARGET,
        burning_aura_link_ref=LINK,
        dendro_like_link_refs=(LINK,),
        created_by_occurrence_ref="interaction:burning:occurrence:0",
        current_effect_owner=SOURCE,
        captured_scaling_basis=burning_basis(),
        next_dendro_like_depletion_frame=300,
        next_damage_tick_frame=15,
        next_damage_tick_index=2,
        next_pyro_application_frame=15,
        next_pyro_application_index=1,
    )
    receipt = runtime.commit_prevalidated_state_plan(planner.seal())
    events: list[GameEvent] = []
    context.events.subscribe(EventType.REACTION_STATE_CHANGED, events.append)

    runtime.publish_committed_state_facts(context, receipt)

    payload = cast(dict[str, object], events[0].payload.to_dict()["after"])
    assert payload["burning_aura_link_ref"] == LINK.link_key
    assert payload["dendro_like_link_refs"] == [LINK.link_key]
    assert payload["next_dendro_like_depletion_frame"] == 300
    assert payload["next_damage_tick_frame"] == 15
    assert payload["next_pyro_application_frame"] == 15


def test_default_scheduled_registry_accepts_live_burning_cycle_root():
    runtime = create_default_reaction_bootstrap().create_runtime()
    planner = runtime.begin_state_batch(0, "burning-scheduled-adapter")
    state = planner.create_burning(
        subject_ref=TARGET,
        burning_aura_link_ref=LINK,
        dendro_like_link_refs=(LINK,),
        created_by_occurrence_ref="interaction:burning:occurrence:0",
        current_effect_owner=SOURCE,
        captured_scaling_basis=burning_basis(),
        next_dendro_like_depletion_frame=300,
        next_damage_tick_frame=15,
        next_damage_tick_index=2,
        next_pyro_application_frame=15,
        next_pyro_application_index=1,
    )
    runtime.commit_prevalidated_state_plan(planner.seal())
    root = BurningCycleRootWork(
        work_id=(
            f"reaction-state:{state.instance_ref.value}:frame:15:"
            "burning:damage:2:pyro_application:1"
        ),
        frame=15,
        root_order=0,
        state_instance_ref=state.instance_ref,
        subject_ref=TARGET,
        damage_tick_index=2,
        pyro_application_index=1,
    )

    result = create_default_scheduled_reaction_root_adapter_registry().prepare(
        root,
        runtime.state_records,
    )

    assert result.outcome == "prepared"
    assert len(result.effect_groups) == 1
    group = result.effect_groups[0]
    assert isinstance(group.target_selection, AreaAroundSubjectSelection)
    assert group.target_selection.anchor_subject_ref == TARGET
    assert group.target_selection.radius == 1.0
    assert group.target_selection.include_anchor
    assert group.cause == root.damage_cause
    effect = group.effects[0]
    assert isinstance(effect, GeneratedDamageImpactEffect)
    assert effect.parent_occurrence_ref is None
    assert effect.cause == root.damage_cause
    assert effect.transformative_base_multiplier == 0.25
    assert len(result.generated_impact_batches) == 1
    batch = result.generated_impact_batches[0]
    assert isinstance(batch, ReactionGeneratedImpactBatch)
    assert batch.parent_root_work_ref == root.work_id
    assert batch.parent_occurrence_refs == ()
    assert batch.causes == (root.pyro_cause,)
    assert batch.source_ref == state.current_effect_owner
    assert batch.captured_source_observation == state.captured_scaling_basis
    assert isinstance(batch.target_selection, CurrentSubjectSelection)
    assert batch.target_selection.subject_ref == TARGET
    impact = batch.impacts[0]
    assert isinstance(impact, ReactionGeneratedImpact)
    assert impact.element is Element.PYRO
    assert impact.elemental_amount == BURNING_PYRO_APPLICATION_AMOUNT
    assert impact.aura_application_profile_key == BURNING_PYRO_AURA_APPLICATION_PROFILE_KEY
    assert impact.damage_component is None
    assert impact.provenance.parent_occurrence_ref is None
    assert impact.provenance.cause == root.pyro_cause


def test_burning_pyro_only_root_does_not_generate_damage_effect_group():
    runtime = create_default_reaction_bootstrap().create_runtime()
    planner = runtime.begin_state_batch(0, "burning-pyro-only-scheduled-adapter")
    state = planner.create_burning(
        subject_ref=TARGET,
        burning_aura_link_ref=LINK,
        dendro_like_link_refs=(LINK,),
        created_by_occurrence_ref="interaction:burning:occurrence:0",
        current_effect_owner=SOURCE,
        captured_scaling_basis=burning_basis(),
        next_dendro_like_depletion_frame=300,
        next_damage_tick_frame=30,
        next_damage_tick_index=2,
        next_pyro_application_frame=15,
        next_pyro_application_index=1,
    )
    runtime.commit_prevalidated_state_plan(planner.seal())
    root = BurningCycleRootWork(
        work_id=(
            f"reaction-state:{state.instance_ref.value}:frame:15:"
            "burning:damage:0:pyro_application:1"
        ),
        frame=15,
        root_order=0,
        state_instance_ref=state.instance_ref,
        subject_ref=TARGET,
        pyro_application_index=1,
    )

    result = create_default_scheduled_reaction_root_adapter_registry().prepare(
        root,
        runtime.state_records,
    )

    assert result.outcome == "prepared"
    assert result.effect_groups == ()

    assert len(result.generated_impact_batches) == 1


def test_burning_periodic_pyro_profile_uses_standard_attachment_loss_and_decay():
    profile = burning_pyro_aura_application_profile()

    assert profile.profile_key == BURNING_PYRO_AURA_APPLICATION_PROFILE_KEY
    assert profile.resolve_decay_profile(
        base_strength=AuraStrength.WEAK,
        effective_raw_amount=BURNING_PYRO_APPLICATION_AMOUNT,
    ).attached_amount == AuraAmount("4/5")
