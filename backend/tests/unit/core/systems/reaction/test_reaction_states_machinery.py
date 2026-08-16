from __future__ import annotations

from typing import cast

import pytest

from genshin_sim.core.coordination.elemental_reaction import (
    ElementalStateFrameCoordinator,
    FrozenStateLinkBatchCoordinator,
)
from genshin_sim.core.elements import (
    AuraAmount,
    ElementalSourceRef,
    ElementalStateLinkRef,
    ElementalSubjectRef,
)
from genshin_sim.core.events import EventType
from genshin_sim.core.simulation import SimulationContext
from genshin_sim.core.systems.aura import (
    AuraRuntime,
    FrozenAuraApplicationRequest,
)
from genshin_sim.core.systems.aura_icd import AuraIcdRuntime
from genshin_sim.core.systems.reaction import (
    ElectroChargedTickRootWork,
    ReactionStateInstanceRef,
    ReactionStateScopeKey,
    ReactionStateSlot,
    ReactionStateSlotKey,
    ReactionStoreConflictError,
    ReactionStoreMutationPlan,
    ScheduledStateTickCause,
    ScheduledStateTickKind,
    create_default_reaction_bootstrap,
)
from genshin_sim.core.systems.reaction.gates import ReactionDamageGateRequest

SOURCE = ElementalSourceRef("character:slot_1")
TARGET = ElementalSubjectRef.target("target:target_1")
LINK = ElementalStateLinkRef("elemental-state-link:test")


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
