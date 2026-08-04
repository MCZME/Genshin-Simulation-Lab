from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from genshin_sim.core.coordination.elemental_reaction import (
    BurningStateLinkBatchCoordinator,
    ElementalStateFrameCoordinator,
    ElementalStateLinkConflictError,
    FrozenStateLinkBatchCoordinator,
    validate_burning_state_links,
    validate_frozen_state_links,
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
from genshin_sim.core.events import EventType, GameEvent
from genshin_sim.core.simulation import SimulationContext
from genshin_sim.core.systems.aura import (
    AuraApplicationRequest,
    AuraDecayMode,
    AuraRuntime,
    AuraStateLinkMutationRequest,
    AuraStrength,
    BurningAuraApplicationRequest,
    FrozenAuraApplicationRequest,
)
from genshin_sim.core.systems.aura_icd import AuraIcdRuntime
from genshin_sim.core.systems.reaction import (
    AreaAroundSubjectSelection,
    BurningCycleRootWork,
    BurningState,
    CapturedTransformativeScalingBasis,
    CrystallizeShardLifecycleState,
    CrystallizeShardState,
    CrystallizeShardStateCreationIntent,
    CrystallizeSourceObservation,
    CurrentSubjectSelection,
    ElectroChargedTickRootWork,
    FreezeRecoveryState,
    GeneratedDamageImpactEffect,
    ReactionGeneratedImpact,
    ReactionGeneratedImpactBatch,
    ReactionRegistry,
    ReactionRuntime,
    ReactionStateInstanceRef,
    ReactionStateScopeKey,
    ReactionStateSlot,
    ReactionStateSlotKey,
    ReactionStoreConflictError,
    ReactionStoreMutationPlan,
    ScheduledStateTickCause,
    ScheduledStateTickKind,
    create_default_reaction_bootstrap,
    create_default_scheduled_reaction_root_adapter_registry,
)
from genshin_sim.core.systems.reaction.gates import ReactionDamageGateRequest
from genshin_sim.core.systems.reaction.mechanics.burning import (
    BURNING_PYRO_APPLICATION_AMOUNT,
    BURNING_PYRO_AURA_APPLICATION_PROFILE_KEY,
    burning_pyro_aura_application_profile,
)
from genshin_sim.core.systems.reaction.mechanics.crystallize import crystallize_definition
from genshin_sim.core.systems.reaction.mechanics.crystallize.formulas import (
    capture_crystallize_shield_basis,
)

SOURCE = ElementalSourceRef("character:slot_1")
TARGET = ElementalSubjectRef.target("target:target_1")
LINK = ElementalStateLinkRef("elemental-state-link:test")


def _burning_basis(
    source_ref: ElementalSourceRef = SOURCE,
    *,
    captured_frame: int = 0,
) -> CapturedTransformativeScalingBasis:
    return CapturedTransformativeScalingBasis(
        basis_ref=f"basis:burning:{source_ref.source_key}:{captured_frame}",
        captured_frame=captured_frame,
        source_ref=source_ref,
        source_kind=TransformativeReactionSourceKind.CHARACTER,
        source_level=90,
        elemental_mastery=120.0,
        reaction_bonus=0.0,
        reaction_profile_key="reaction_profile.burning.incoming_pyro_on_dendro",
        damage_profile_key="damage_profile.reaction.burning",
        level_multiplier_table_key="character",
        level_multiplier=1446.853,
        source_observation_ref=f"observation:burning:{source_ref.source_key}:{captured_frame}",
        source_owner_slot=1,
    )


def test_burning_cycle_root_derives_independent_damage_and_pyro_causes():
    instance_ref = ReactionStateInstanceRef("reaction-state-instance:burning")
    root = BurningCycleRootWork(
        work_id=(
            "reaction-state:reaction-state-instance:burning:frame:15:"
            "burning:damage:2:pyro_application:1"
        ),
        frame=15,
        root_order=0,
        state_instance_ref=instance_ref,
        subject_ref=TARGET,
        damage_tick_index=2,
        pyro_application_index=1,
    )

    assert root.state_slot is ReactionStateSlot.BURNING
    assert tuple(cause.tick_kind for cause in root.causes) == (
        ScheduledStateTickKind.BURNING_DAMAGE,
        ScheduledStateTickKind.BURNING_PYRO_APPLICATION,
    )
    assert tuple(cause.tick_index for cause in root.causes) == (2, 1)

    with pytest.raises(ValueError, match="damage_cause 必须与 root identity 一致"):
        BurningCycleRootWork(
            work_id=(
                "reaction-state:reaction-state-instance:burning:frame:15:"
                "burning:damage:2:pyro_application:1"
            ),
            frame=15,
            root_order=0,
            state_instance_ref=instance_ref,
            subject_ref=TARGET,
            damage_tick_index=2,
            pyro_application_index=1,
            damage_cause=ScheduledStateTickCause(
                state_instance_ref=instance_ref,
                scheduled_frame=15,
                tick_kind=ScheduledStateTickKind.BURNING_DAMAGE,
                tick_index=3,
            ),
        )

    damage_only = BurningCycleRootWork(
        work_id=(
            "reaction-state:reaction-state-instance:burning:frame:30:"
            "burning:damage:3:pyro_application:0"
        ),
        frame=30,
        root_order=1,
        state_instance_ref=instance_ref,
        subject_ref=TARGET,
        damage_tick_index=3,
    )
    pyro_only = BurningCycleRootWork(
        work_id=(
            "reaction-state:reaction-state-instance:burning:frame:120:"
            "burning:damage:0:pyro_application:2"
        ),
        frame=120,
        root_order=2,
        state_instance_ref=instance_ref,
        subject_ref=TARGET,
        pyro_application_index=2,
    )

    assert damage_only.scheduled_tick_index == 3
    assert damage_only.causes == (damage_only.damage_cause,)
    assert pyro_only.scheduled_tick_index == 2
    assert pyro_only.causes == (pyro_only.pyro_cause,)


def test_burning_state_tracks_shared_link_source_and_independent_cycle_cursors():
    runtime = create_default_reaction_bootstrap().create_runtime()
    planner = runtime.begin_state_batch(0, "burning-create")
    created = planner.create_burning(
        subject_ref=TARGET,
        burning_aura_link_ref=LINK,
        dendro_like_link_refs=(LINK,),
        created_by_occurrence_ref="interaction:burning:occurrence:0",
        current_effect_owner=SOURCE,
        captured_scaling_basis=_burning_basis(),
        next_dendro_like_depletion_frame=300,
        next_damage_tick_frame=15,
        next_damage_tick_index=2,
        next_pyro_application_frame=15,
        next_pyro_application_index=1,
    )
    runtime.commit_prevalidated_state_plan(planner.seal())

    assert isinstance(created, BurningState)
    assert created.slot_key == ReactionStateSlotKey(TARGET, ReactionStateSlot.BURNING)
    assert created.next_required_frame == 15
    assert runtime.burning_state_for(TARGET) == created
    assert runtime.next_required_frame() == 15
    snapshot = cast(list[dict[str, object]], runtime.snapshot(0).to_dict()["state_records"])
    assert snapshot == [
        {
            "slot": "burning",
            "scope_key": "shared",
            "subject": {"kind": "target", "entity_id": "target:target_1"},
            "instance_ref": created.instance_ref.value,
            "next_required_frame": 15,
            "burning_aura_link_ref": LINK.link_key,
            "dendro_like_link_refs": [LINK.link_key],
            "created_frame": 0,
            "created_by_occurrence_ref": "interaction:burning:occurrence:0",
            "current_effect_owner": SOURCE.to_dict(),
            "captured_scaling_basis": {
                "basis_ref": _burning_basis().basis_ref,
                "captured_frame": 0,
                "source_ref": SOURCE.to_dict(),
                "source_kind": "character",
                "source_level": 90,
                "elemental_mastery": 120.0,
                "reaction_bonus": 0.0,
                "reaction_profile_key": "reaction_profile.burning.incoming_pyro_on_dendro",
                "damage_profile_key": "damage_profile.reaction.burning",
                "level_multiplier_table_key": "character",
                "level_multiplier": 1446.853,
                "source_observation_ref": "observation:burning:character:slot_1:0",
                "source_owner_slot": 1,
            },
            "next_dendro_like_depletion_frame": 300,
            "next_damage_tick_frame": 15,
            "next_damage_tick_index": 2,
            "next_pyro_application_frame": 15,
            "next_pyro_application_index": 1,
            "revision": 1,
        }
    ]


def test_burning_state_depletion_frame_is_a_runtime_required_frame():
    runtime = create_default_reaction_bootstrap().create_runtime()
    planner = runtime.begin_state_batch(0, "burning-depletion-frame")
    planner.create_burning(
        subject_ref=TARGET,
        burning_aura_link_ref=LINK,
        dendro_like_link_refs=(LINK,),
        created_by_occurrence_ref="interaction:burning:occurrence:0",
        current_effect_owner=SOURCE,
        captured_scaling_basis=_burning_basis(),
        next_dendro_like_depletion_frame=10,
        next_damage_tick_frame=15,
        next_damage_tick_index=2,
        next_pyro_application_frame=15,
        next_pyro_application_index=1,
    )
    runtime.commit_prevalidated_state_plan(planner.seal())

    assert runtime.next_required_frame() == 10
    with pytest.raises(ValueError, match="不能跨过 ReactionState 必需处理帧"):
        runtime.update_frame(None, 11)


def test_burning_state_source_refresh_preserves_identity_and_cannot_reset_cursors():
    runtime = create_default_reaction_bootstrap().create_runtime()
    create = runtime.begin_state_batch(0, "burning-create")
    created = create.create_burning(
        subject_ref=TARGET,
        burning_aura_link_ref=LINK,
        dendro_like_link_refs=(LINK,),
        created_by_occurrence_ref="interaction:burning:occurrence:0",
        current_effect_owner=SOURCE,
        captured_scaling_basis=_burning_basis(),
        next_dendro_like_depletion_frame=300,
        next_damage_tick_frame=15,
        next_damage_tick_index=2,
        next_pyro_application_frame=15,
        next_pyro_application_index=1,
    )
    runtime.commit_prevalidated_state_plan(create.seal())

    refreshed_source = ElementalSourceRef("character:slot_2")
    refresh = runtime.begin_state_batch(0, "burning-refresh")
    refreshed = refresh.replace_burning(
        replace(
            created,
            current_effect_owner=refreshed_source,
            captured_scaling_basis=_burning_basis(refreshed_source),
            revision=created.revision + 1,
        )
    )
    runtime.commit_prevalidated_state_plan(refresh.seal())

    assert refreshed.instance_ref == created.instance_ref
    assert refreshed.burning_aura_link_ref == created.burning_aura_link_ref
    assert refreshed.dendro_like_link_refs == created.dendro_like_link_refs
    assert refreshed.next_dendro_like_depletion_frame == created.next_dendro_like_depletion_frame
    assert refreshed.next_damage_tick_frame == created.next_damage_tick_frame
    assert refreshed.next_damage_tick_index == created.next_damage_tick_index
    assert refreshed.next_pyro_application_frame == created.next_pyro_application_frame
    assert refreshed.next_pyro_application_index == created.next_pyro_application_index
    assert refreshed.current_effect_owner == refreshed_source

    invalid_refresh = runtime.begin_state_batch(0, "burning-invalid-refresh")
    with pytest.raises(ValueError, match="不能回退周期 cursor"):
        invalid_refresh.replace_burning(
            replace(
                refreshed,
                next_damage_tick_frame=16,
                next_damage_tick_index=1,
                revision=refreshed.revision + 1,
            )
        )


def test_burning_state_link_validator_requires_burning_and_dendro_complete_projection():
    aura_runtime = AuraRuntime()
    aura_runtime.apply(
        AuraApplicationRequest(
            "aura:dendro",
            "aura:dendro:application",
            "impact:dendro",
            0,
            0,
            SOURCE,
            TARGET,
            Element.DENDRO,
            AuraStrength.WEAK,
        )
    )
    reaction_runtime = create_default_reaction_bootstrap().create_runtime()
    aura_planner = aura_runtime.begin_batch(0, "burning-link")
    aura_planner.mutate_state_links(
        AuraStateLinkMutationRequest(
            "aura:dendro:burning-link",
            0,
            0,
            TARGET,
            AuraKind.DENDRO,
            add_link_refs=(LINK,),
            decay_mode=AuraDecayMode.REACTION_MANAGED,
        )
    )
    aura_planner.apply_burning(
        BurningAuraApplicationRequest(
            "aura:burning",
            "aura:burning:application",
            "impact:burning",
            0,
            1,
            SOURCE,
            TARGET,
            LINK,
            AuraAmount(2),
        )
    )
    state_planner = reaction_runtime.begin_state_batch(0, "burning-link")
    state = state_planner.create_burning(
        subject_ref=TARGET,
        burning_aura_link_ref=LINK,
        dendro_like_link_refs=(LINK,),
        created_by_occurrence_ref="interaction:burning:occurrence:0",
        current_effect_owner=SOURCE,
        captured_scaling_basis=_burning_basis(),
        next_dendro_like_depletion_frame=300,
        next_damage_tick_frame=15,
        next_damage_tick_index=2,
        next_pyro_application_frame=15,
        next_pyro_application_index=1,
    )
    receipt = BurningStateLinkBatchCoordinator(
        aura_runtime,
        reaction_runtime,
    ).commit_prevalidated(aura_planner.seal(), state_planner.seal())

    validate_burning_state_links(
        aura_runtime.snapshot().targets,
        reaction_runtime.state_snapshot(0).records,
    )
    assert receipt.reaction_state_receipt.plan.replacement_records == (state,)

    extra_link = ElementalStateLinkRef("elemental-state-link:extra")
    extra_link_plan = aura_runtime.begin_batch(0, "burning-extra-link")
    extra_link_plan.mutate_state_links(
        AuraStateLinkMutationRequest(
            "aura:dendro:extra-link",
            0,
            0,
            TARGET,
            AuraKind.DENDRO,
            add_link_refs=(extra_link,),
        )
    )
    aura_runtime.commit_prevalidated(extra_link_plan.seal())

    with pytest.raises(
        ElementalStateLinkConflictError,
        match="BurningState 的类草 Link 与 Aura 不一致",
    ):
        validate_burning_state_links(
            aura_runtime.snapshot().targets,
            reaction_runtime.state_snapshot(0).records,
        )


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
        captured_scaling_basis=_burning_basis(),
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
        captured_scaling_basis=_burning_basis(),
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
        captured_scaling_basis=_burning_basis(),
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


def test_electro_charged_root_derives_a_validated_scheduled_cause():
    instance_ref = ReactionStateInstanceRef("reaction-state-instance:electro")
    root = ElectroChargedTickRootWork(
        work_id="reaction-state:reaction-state-instance:electro:frame:60:tick:1",
        frame=60,
        root_order=0,
        state_instance_ref=instance_ref,
        subject_ref=TARGET,
        tick_index=1,
    )

    assert root.state_slot is ReactionStateSlot.ELECTRO_CHARGED
    assert root.cause is not None
    assert root.cause.tick_kind is ScheduledStateTickKind.ELECTRO_CHARGED_PULSE
    assert root.cause.scheduled_frame == 60
    assert root.cause_ref == root.cause.cause_ref

    with pytest.raises(ValueError, match="必须与 root identity 一致"):
        ElectroChargedTickRootWork(
            work_id="reaction-state:reaction-state-instance:electro:frame:60:tick:1",
            frame=60,
            root_order=0,
            state_instance_ref=instance_ref,
            subject_ref=TARGET,
            tick_index=1,
            cause=ScheduledStateTickCause(
                state_instance_ref=instance_ref,
                scheduled_frame=60,
                tick_kind=ScheduledStateTickKind.BURNING_DAMAGE,
                tick_index=1,
            ),
        )

    with pytest.raises(ValueError, match="work_id 必须由 state instance"):
        ElectroChargedTickRootWork(
            work_id="reaction-state:other:frame:60:tick:1",
            frame=60,
            root_order=0,
            state_instance_ref=instance_ref,
            subject_ref=TARGET,
            tick_index=1,
        )


def test_state_plan_create_replace_remove_preserves_instance_and_allocates_after_removal():
    runtime = create_default_reaction_bootstrap().create_runtime()

    create = runtime.begin_state_batch(0, "create")
    created = create.create_frozen(
        subject_ref=TARGET,
        state_link_ref=LINK,
        next_required_frame=30,
    )
    runtime.commit_prevalidated_state_plan(create.seal())

    replace = runtime.begin_state_batch(0, "replace")
    replaced = replace.replace_frozen(
        type(created)(
            created.instance_ref,
            created.subject_ref,
            created.state_link_ref,
            created.created_frame,
            60,
        )
    )
    runtime.commit_prevalidated_state_plan(replace.seal())

    remove = runtime.begin_state_batch(0, "remove")
    remove.remove_frozen(subject_ref=TARGET, expected_instance_ref=replaced.instance_ref)
    runtime.commit_prevalidated_state_plan(remove.seal())

    recreate = runtime.begin_state_batch(0, "recreate")
    recreated = recreate.create_frozen(subject_ref=TARGET, state_link_ref=LINK)
    runtime.commit_prevalidated_state_plan(recreate.seal())

    assert replaced.instance_ref == created.instance_ref
    assert recreated.instance_ref.value == "reaction-state-instance:2"
    assert runtime.frozen_state_for(TARGET) == recreated
    assert runtime.snapshot(0).state_records == (recreated,)
    snapshot_records = cast(list[dict[str, object]], runtime.snapshot(0).to_dict()["state_records"])
    assert snapshot_records[0]["state_link_ref"] == LINK.link_key
    assert snapshot_records[0]["scope_key"] == "shared"


def test_reaction_state_slot_keys_default_to_shared_scope_and_keep_explicit_scopes_distinct():
    shared = ReactionStateSlotKey(TARGET, ReactionStateSlot.FROZEN)
    explicit_shared = ReactionStateSlotKey(
        TARGET,
        ReactionStateSlot.FROZEN,
        ReactionStateScopeKey("shared"),
    )
    shard_scope = ReactionStateSlotKey(
        TARGET,
        ReactionStateSlot.FROZEN,
        ReactionStateScopeKey("reaction-state:crystallize-shard:occurrence:0"),
    )

    assert shared == explicit_shared
    assert shared != shard_scope


def test_crystallize_shard_state_uses_its_deterministic_scope_and_runtime_index():
    runtime = ReactionRuntime(ReactionRegistry((crystallize_definition(),)))
    occurrence_ref = "interaction:crystallize:occurrence:0"
    instance_ref = ReactionStateInstanceRef(f"reaction-state:crystallize-shard:{occurrence_ref}")
    intent = CrystallizeShardStateCreationIntent(
        "intent:crystallize",
        occurrence_ref,
        instance_ref,
        TARGET,
        f"reaction_object:crystallize_shard:{occurrence_ref}",
        Element.PYRO,
        SOURCE,
        capture_crystallize_shield_basis(
            CrystallizeSourceObservation(SOURCE, 90, 0),
            captured_frame=0,
        ),
        0,
        900,
    )
    planner = runtime.begin_state_batch(0, "crystallize")
    shard = planner.create_crystallize_shard(intent)
    receipt = runtime.commit_prevalidated_state_plan(planner.seal())

    assert isinstance(shard, CrystallizeShardState)
    assert shard.slot_key.scope_key == ReactionStateScopeKey(instance_ref.value)
    assert shard.next_required_frame == 900
    assert runtime.crystallize_shard_state_for(instance_ref) == shard
    assert runtime.next_required_frame() == 900
    assert receipt.version == 1
    snapshot = cast(list[dict[str, object]], runtime.snapshot(0).to_dict()["state_records"])
    assert snapshot[0]["space_entity_ref"] == shard.space_entity_ref
    assert snapshot[0]["lifecycle_state"] == "active"


def test_crystallize_shard_state_rejects_identity_not_derived_from_its_occurrence():
    occurrence_ref = "interaction:crystallize:occurrence:0"
    basis = capture_crystallize_shield_basis(
        CrystallizeSourceObservation(SOURCE, 90, 0),
        captured_frame=0,
    )

    with pytest.raises(ValueError, match="instance_ref 必须由 occurrence_ref 确定性派生"):
        CrystallizeShardState(
            ReactionStateInstanceRef("reaction-state:crystallize-shard:other"),
            TARGET,
            f"reaction_object:crystallize_shard:{occurrence_ref}",
            Element.PYRO,
            occurrence_ref,
            SOURCE,
            basis,
            0,
            900,
        )

    with pytest.raises(ValueError, match="space_entity_ref 必须由 occurrence_ref 确定性派生"):
        CrystallizeShardState(
            ReactionStateInstanceRef(f"reaction-state:crystallize-shard:{occurrence_ref}"),
            TARGET,
            "reaction_object:crystallize_shard:other",
            Element.PYRO,
            occurrence_ref,
            SOURCE,
            basis,
            0,
            900,
        )


def test_crystallize_shard_state_terminalization_keeps_a_tombstone_outside_required_frame():
    runtime = ReactionRuntime(ReactionRegistry((crystallize_definition(),)))
    occurrence_ref = "interaction:crystallize:occurrence:terminal"
    instance_ref = ReactionStateInstanceRef(f"reaction-state:crystallize-shard:{occurrence_ref}")
    intent = CrystallizeShardStateCreationIntent(
        "intent:crystallize:terminal",
        occurrence_ref,
        instance_ref,
        TARGET,
        f"reaction_object:crystallize_shard:{occurrence_ref}",
        Element.PYRO,
        SOURCE,
        capture_crystallize_shield_basis(
            CrystallizeSourceObservation(SOURCE, 90, 0),
            captured_frame=0,
        ),
        0,
        900,
    )
    create = runtime.begin_state_batch(0, "crystallize:terminal:create")
    shard = create.create_crystallize_shard(intent)
    runtime.commit_prevalidated_state_plan(create.seal())
    runtime.update_frame(None, 1)

    terminalize = runtime.begin_state_batch(1, "crystallize:terminal:pick")
    picked = terminalize.terminalize_crystallize_shard(
        instance_ref=instance_ref,
        lifecycle_state=CrystallizeShardLifecycleState.PICKED,
    )
    runtime.commit_prevalidated_state_plan(terminalize.seal())

    assert picked.lifecycle_state is CrystallizeShardLifecycleState.PICKED
    assert picked.terminal_frame == 1
    assert picked.revision == shard.revision + 1
    assert picked.next_required_frame is None
    assert runtime.crystallize_shard_state_for(instance_ref) == picked
    assert runtime.is_idle()

    retry = runtime.begin_state_batch(1, "crystallize:terminal:retry")
    with pytest.raises(ValueError, match="已经处于终态"):
        retry.terminalize_crystallize_shard(
            instance_ref=instance_ref,
            lifecycle_state=CrystallizeShardLifecycleState.PICKED,
        )


def test_uncommitted_state_plan_does_not_consume_instance_sequence_and_stale_plan_fails():
    runtime = create_default_reaction_bootstrap().create_runtime()
    discarded = runtime.begin_state_batch(0, "discarded")
    discarded.create_frozen(subject_ref=TARGET, state_link_ref=LINK)

    create = runtime.begin_state_batch(0, "create")
    created = create.create_frozen(subject_ref=TARGET, state_link_ref=LINK)
    runtime.commit_prevalidated_state_plan(create.seal())
    assert created.instance_ref.value == "reaction-state-instance:1"

    stale = runtime.begin_state_batch(0, "stale")
    stale.replace_frozen(
        type(created)(
            created.instance_ref,
            created.subject_ref,
            created.state_link_ref,
            created.created_frame,
            20,
        )
    )
    winner = runtime.begin_state_batch(0, "winner")
    winner.remove_frozen(subject_ref=TARGET)
    runtime.commit_prevalidated_state_plan(winner.seal())

    with pytest.raises(ReactionStoreConflictError, match="已经过期"):
        runtime.commit_prevalidated_state_plan(stale.seal())


def test_composite_gate_and_state_plan_commits_with_one_shared_version_increment():
    runtime = create_default_reaction_bootstrap().create_runtime()
    state_planner = runtime.begin_state_batch(0, "composite-state")
    state_planner.create_frozen(subject_ref=TARGET, state_link_ref=LINK)
    gate_planner = runtime.begin_gate_batch(0, "composite-gate")
    gate_planner.prepare(
        ReactionDamageGateRequest(
            gate_request_ref="composite:gate-request",
            frame=0,
            definition=runtime.gate_definition("reaction_gate.overloaded.damage"),
            trigger_source_ref=SOURCE,
            damage_target_ref=TARGET,
            parent_occurrence_ref="composite:occurrence",
            parent_effect_ref="composite:effect",
        )
    )

    receipt = runtime.commit_prevalidated_store_mutation_plan(
        ReactionStoreMutationPlan(gate_planner.seal(), state_planner.seal())
    )

    assert receipt.version == 1
    assert runtime.version == 1
    assert len(runtime.gate_records) == 1
    assert runtime.frozen_state_for(TARGET) is not None


def test_freeze_recovery_state_is_not_an_active_frozen_state_or_link_participant():
    runtime = create_default_reaction_bootstrap().create_runtime()
    runtime.update_frame(None, 20)
    planner = runtime.begin_state_batch(20, "recovery")
    recovery = planner.create_freeze_recovery(
        subject_ref=TARGET,
        decay_rate=0.6,
    )
    runtime.commit_prevalidated_state_plan(planner.seal())

    assert isinstance(recovery, FreezeRecoveryState)
    assert recovery.next_required_frame is None
    assert runtime.frozen_state_for(TARGET) is None
    assert runtime.freeze_recovery_state_for(TARGET) == recovery
    assert runtime.is_idle()
    snapshot_record = cast(
        list[dict[str, object]], runtime.snapshot(20).to_dict()["state_records"]
    )[0]
    assert snapshot_record["slot"] == "freeze_recovery"
    assert "state_link_ref" not in snapshot_record


def test_frozen_state_tracks_decay_rate_and_its_update_frame():
    runtime = create_default_reaction_bootstrap().create_runtime()
    runtime.update_frame(None, 12)
    planner = runtime.begin_state_batch(12, "frozen-rate")
    frozen = planner.create_frozen(
        subject_ref=TARGET,
        state_link_ref=LINK,
        next_required_frame=36,
    )
    runtime.commit_prevalidated_state_plan(planner.seal())

    runtime.update_frame(None, 18)
    replacement = runtime.begin_state_batch(18, "frozen-rate-refresh")
    refreshed = replacement.replace_frozen(
        type(frozen)(
            frozen.instance_ref,
            frozen.subject_ref,
            frozen.state_link_ref,
            frozen.created_frame,
            42,
            0.5,
            18,
        )
    )
    runtime.commit_prevalidated_state_plan(replacement.seal())

    assert frozen.decay_rate == 0.4
    assert frozen.decay_rate_updated_frame == 12
    assert refreshed.decay_rate == 0.5
    assert refreshed.decay_rate_updated_frame == 18


def test_creating_a_new_frozen_state_consumes_prior_recovery_history():
    runtime = create_default_reaction_bootstrap().create_runtime()
    recovery_plan = runtime.begin_state_batch(0, "recovery")
    recovery_plan.create_freeze_recovery(subject_ref=TARGET, decay_rate=0.6)
    runtime.commit_prevalidated_state_plan(recovery_plan.seal())

    frozen_plan = runtime.begin_state_batch(0, "refreeze")
    frozen = frozen_plan.create_frozen(subject_ref=TARGET, state_link_ref=LINK)
    runtime.commit_prevalidated_state_plan(frozen_plan.seal())

    assert runtime.frozen_state_for(TARGET) == frozen
    assert runtime.freeze_recovery_state_for(TARGET) is None
    assert runtime.state_records == (frozen,)


def test_frozen_aura_and_state_link_must_be_one_to_one_and_same_subject():
    aura_runtime = AuraRuntime()
    aura_runtime.apply(
        AuraApplicationRequest(
            "aura:hydro",
            "aura:hydro:application",
            "impact:hydro",
            0,
            0,
            SOURCE,
            TARGET,
            Element.HYDRO,
            AuraStrength.WEAK,
        )
    )
    reaction_runtime = create_default_reaction_bootstrap().create_runtime()
    state_planner = reaction_runtime.begin_state_batch(0, "frozen")
    state_planner.create_frozen(subject_ref=TARGET, state_link_ref=LINK)
    aura_planner = aura_runtime.begin_batch(0, "frozen")
    frozen = aura_planner.apply_frozen(
        FrozenAuraApplicationRequest(
            "aura:frozen",
            "aura:frozen:application",
            "impact:frozen",
            0,
            1,
            SOURCE,
            TARGET,
            LINK,
            AuraAmount(2),
        )
    )
    receipt = FrozenStateLinkBatchCoordinator(aura_runtime, reaction_runtime).commit_prevalidated(
        aura_planner.seal(),
        state_planner.seal(),
    )

    validate_frozen_state_links(
        aura_runtime.snapshot().targets,
        reaction_runtime.state_snapshot(0).records,
    )
    assert frozen.after is not None
    assert frozen.after.current_amount == AuraAmount(2)
    assert receipt.aura_receipt.version == aura_runtime.version
    assert receipt.reaction_state_receipt.version == reaction_runtime.version

    remove_state = reaction_runtime.begin_state_batch(0, "remove")
    remove_state.remove_frozen(subject_ref=TARGET)
    reaction_runtime.commit_prevalidated_state_plan(remove_state.seal())

    with pytest.raises(ElementalStateLinkConflictError, match="悬空 Link"):
        validate_frozen_state_links(
            aura_runtime.snapshot().targets,
            reaction_runtime.state_snapshot(0).records,
        )


def test_frozen_aura_refresh_uses_larger_current_or_new_amount():
    runtime = AuraRuntime()

    first = runtime.begin_batch(0, "frozen:first")
    first.apply_frozen(
        FrozenAuraApplicationRequest(
            "aura:frozen:first",
            "application:frozen:first",
            "impact:frozen:first",
            0,
            0,
            SOURCE,
            TARGET,
            LINK,
            AuraAmount(4),
        )
    )
    runtime.commit_prevalidated(first.seal())

    lower = runtime.begin_batch(0, "frozen:lower")
    lower_result = lower.apply_frozen(
        FrozenAuraApplicationRequest(
            "aura:frozen:lower",
            "application:frozen:lower",
            "impact:frozen:lower",
            0,
            0,
            SOURCE,
            TARGET,
            LINK,
            AuraAmount(2),
        )
    )
    runtime.commit_prevalidated(lower.seal())

    higher = runtime.begin_batch(0, "frozen:higher")
    higher_result = higher.apply_frozen(
        FrozenAuraApplicationRequest(
            "aura:frozen:higher",
            "application:frozen:higher",
            "impact:frozen:higher",
            0,
            0,
            SOURCE,
            TARGET,
            LINK,
            AuraAmount(6),
        )
    )
    runtime.commit_prevalidated(higher.seal())

    assert lower_result.after is not None
    assert lower_result.after.current_amount == AuraAmount(4)
    assert higher_result.after is not None
    assert higher_result.after.current_amount == AuraAmount(6)


def test_frozen_aura_refresh_can_replace_raw_amount_with_decay_projection():
    runtime = AuraRuntime()
    initial = runtime.begin_batch(0, "frozen:initial")
    initial.apply_frozen(
        FrozenAuraApplicationRequest(
            "aura:frozen:initial",
            "application:frozen:initial",
            "impact:frozen:initial",
            0,
            0,
            SOURCE,
            TARGET,
            LINK,
            AuraAmount(4),
        )
    )
    runtime.commit_prevalidated(initial.seal())

    refreshed = runtime.begin_batch(0, "frozen:projected")
    result = refreshed.apply_frozen(
        FrozenAuraApplicationRequest(
            "aura:frozen:projected",
            "application:frozen:projected",
            "impact:frozen:projected",
            0,
            0,
            SOURCE,
            TARGET,
            LINK,
            AuraAmount("71/20"),
            replace_existing_amount=True,
        )
    )
    runtime.commit_prevalidated(refreshed.seal())

    assert result.after is not None
    assert result.after.current_amount == AuraAmount("71/20")


def test_elemental_state_frame_coordinator_does_not_cross_reaction_required_frame():
    reaction_runtime = create_default_reaction_bootstrap().create_runtime()
    aura_runtime = AuraRuntime()
    state_planner = reaction_runtime.begin_state_batch(0, "required-frame")
    state_planner.create_frozen(
        subject_ref=TARGET,
        state_link_ref=LINK,
        next_required_frame=10,
    )
    aura_planner = aura_runtime.begin_batch(0, "required-frame")
    aura_planner.apply_frozen(
        FrozenAuraApplicationRequest(
            "aura:frozen:required-frame",
            "application:frozen:required-frame",
            "impact:frozen:required-frame",
            0,
            0,
            SOURCE,
            TARGET,
            LINK,
            AuraAmount(2),
        )
    )
    FrozenStateLinkBatchCoordinator(aura_runtime, reaction_runtime).commit_prevalidated(
        aura_planner.seal(),
        state_planner.seal(),
    )
    coordinator = ElementalStateFrameCoordinator(
        aura_runtime,
        AuraIcdRuntime(),
        reaction_runtime,
    )

    record = coordinator.normalize(None, 10)

    assert record.reaction_version == reaction_runtime.version
    assert record.next_required_frame is None
    assert reaction_runtime.frozen_state_for(TARGET) is None
    assert reaction_runtime.freeze_recovery_state_for(TARGET) is not None
    coordinator.normalize(None, 11)


def test_reaction_state_fact_is_published_after_commit_and_blocks_reentrant_write():
    context = SimulationContext()
    runtime = create_default_reaction_bootstrap().create_runtime()
    planner = runtime.begin_state_batch(0, "event")
    planner.create_frozen(subject_ref=TARGET, state_link_ref=LINK)
    receipt = runtime.commit_prevalidated_state_plan(planner.seal())
    events = []
    reentrant_errors = []

    def reenter(_: object) -> None:
        with pytest.raises(ReactionStoreConflictError) as exc_info:
            runtime.begin_state_batch(0, "reentrant")
        reentrant_errors.append(str(exc_info.value))

    context.events.subscribe(EventType.REACTION_STATE_CHANGED, events.append)
    context.events.subscribe(EventType.REACTION_STATE_CHANGED, reenter)

    runtime.publish_committed_state_facts(context, receipt)

    assert [event.event_type for event in events] == [EventType.REACTION_STATE_CHANGED]
    assert events[0].payload.to_dict()["after"] is not None
    assert reentrant_errors == ["元素结算事实发布期间不允许修改 Reaction"]
