from __future__ import annotations

from typing import cast

import pytest

from genshin_sim.core.elements import ElementalSourceRef, ElementalSubjectRef
from genshin_sim.core.systems.reaction import (
    ReactionRegistry,
    ReactionRuntime,
    ReactionStateInstanceRef,
    ReactionStoreConflictError,
    ScheduledStateTickCause,
    ScheduledStateTickKind,
    create_default_reaction_bootstrap,
)
from genshin_sim.core.systems.reaction.gates import (
    ReactionDamageGateDecision,
    ReactionDamageGateRequest,
)
from genshin_sim.core.systems.reaction.mechanics.burning import (
    BURNING_GATE_DEFINITION_KEY,
    burning_gate_definitions,
)


def test_overloaded_gate_uses_half_open_thirty_frame_window():
    runtime = _runtime()
    first = _prepare(runtime, frame=10, definition_key="reaction_gate.overloaded.damage")
    boundary_before = _prepare(runtime, frame=39, definition_key="reaction_gate.overloaded.damage")
    next_window = _prepare(runtime, frame=40, definition_key="reaction_gate.overloaded.damage")

    assert first.decision is ReactionDamageGateDecision.ALLOWED
    assert boundary_before.decision is ReactionDamageGateDecision.BLOCKED
    assert next_window.decision is ReactionDamageGateDecision.ALLOWED
    assert runtime.gate_records[0].window_started_frame == 40
    assert runtime.gate_records[0].accepted_count == 1
    assert runtime.snapshot(40).records == runtime.gate_records


def test_superconduct_gate_allows_two_then_blocks_third_without_advancing_record():
    runtime = _runtime()
    decisions = tuple(
        _prepare(runtime, frame=0, definition_key="reaction_gate.superconduct.damage")
        for _ in range(3)
    )

    assert tuple(item.decision for item in decisions) == (
        ReactionDamageGateDecision.ALLOWED,
        ReactionDamageGateDecision.ALLOWED,
        ReactionDamageGateDecision.BLOCKED,
    )
    assert runtime.gate_records[0].accepted_count == 2
    assert runtime.gate_records[0].revision == 2


def test_shattered_gate_allows_two_then_resets_at_thirty_frame_boundary():
    runtime = create_default_reaction_bootstrap().create_runtime()
    within_window = tuple(
        _prepare(runtime, frame=10, definition_key="reaction_gate.shattered.damage")
        for _ in range(3)
    )
    next_window = _prepare(
        runtime,
        frame=40,
        definition_key="reaction_gate.shattered.damage",
    )

    assert tuple(item.decision for item in within_window) == (
        ReactionDamageGateDecision.ALLOWED,
        ReactionDamageGateDecision.ALLOWED,
        ReactionDamageGateDecision.BLOCKED,
    )
    assert next_window.decision is ReactionDamageGateDecision.ALLOWED
    assert runtime.gate_records[0].window_started_frame == 40
    assert runtime.gate_records[0].accepted_count == 1


def test_gate_plan_captures_reaction_store_version_when_batch_starts():
    runtime = _runtime()
    definition = runtime.gate_definition("reaction_gate.overloaded.damage")
    planned = runtime.begin_gate_batch(0, "gate:planned")
    planned.prepare(
        ReactionDamageGateRequest(
            gate_request_ref="gate:planned:request",
            frame=0,
            definition=definition,
            trigger_source_ref=ElementalSourceRef("character:slot_1"),
            damage_target_ref=ElementalSubjectRef.target("target:target_1"),
            parent_occurrence_ref="gate:planned:occurrence:0",
            parent_effect_ref="gate:planned:effect:0",
        )
    )
    _prepare(runtime, frame=0, definition_key="reaction_gate.superconduct.damage")

    with pytest.raises(ReactionStoreConflictError, match="已经过期"):
        runtime.commit_prevalidated_gate_plan(planned.seal())


def test_gate_records_scheduled_cause_without_a_fake_occurrence_projection():
    runtime = _runtime()
    cause = ScheduledStateTickCause(
        state_instance_ref=ReactionStateInstanceRef("reaction-state-instance:scheduled"),
        scheduled_frame=60,
        tick_kind=ScheduledStateTickKind.ELECTRO_CHARGED_PULSE,
        tick_index=1,
    )
    planner = runtime.begin_gate_batch(60, "scheduled-gate")
    resolution = planner.prepare(
        ReactionDamageGateRequest(
            gate_request_ref="scheduled-gate:request",
            frame=60,
            definition=runtime.gate_definition("reaction_gate.overloaded.damage"),
            trigger_source_ref=ElementalSourceRef("character:slot_1"),
            damage_target_ref=ElementalSubjectRef.target("target:target_1"),
            parent_occurrence_ref=None,
            parent_effect_ref="scheduled-gate:effect",
            cause=cause,
        )
    )
    runtime.commit_prevalidated_gate_plan(planner.seal())

    record = runtime.gate_records[0]
    assert resolution.parent_occurrence_ref is None
    assert resolution.cause == cause
    assert record.last_occurrence_ref is None
    assert record.cause == cause
    snapshot_records = cast(
        list[dict[str, object]],
        runtime.snapshot(60).to_dict()["gate_records"],
    )
    snapshot = snapshot_records[0]
    assert snapshot["cause"] == {
        "kind": "scheduled_state_tick",
        "cause_ref": cause.cause_ref,
        "state_instance_ref": cause.state_instance_ref.value,
        "scheduled_frame": 60,
        "tick_kind": "electro_charged_pulse",
        "tick_index": 1,
    }


def test_burning_gate_allows_eight_scheduled_damage_instances_per_window():
    runtime = ReactionRuntime(ReactionRegistry(), gate_definitions=burning_gate_definitions())
    definition = runtime.gate_definition(BURNING_GATE_DEFINITION_KEY)
    planner = runtime.begin_gate_batch(0, "burning-gate:window:0")
    resolutions = tuple(
        planner.prepare(
            ReactionDamageGateRequest(
                gate_request_ref=f"burning-gate:window:0:request:{tick_index}",
                frame=0,
                definition=definition,
                trigger_source_ref=ElementalSourceRef("character:slot_1"),
                damage_target_ref=ElementalSubjectRef.target("target:target_1"),
                parent_occurrence_ref=None,
                parent_effect_ref=f"burning-gate:window:0:effect:{tick_index}",
                cause=ScheduledStateTickCause(
                    state_instance_ref=ReactionStateInstanceRef("reaction-state-instance:burning"),
                    scheduled_frame=0,
                    tick_kind=ScheduledStateTickKind.BURNING_DAMAGE,
                    tick_index=tick_index,
                ),
            )
        )
        for tick_index in range(1, 10)
    )
    runtime.commit_prevalidated_gate_plan(planner.seal())

    assert tuple(item.decision for item in resolutions) == (
        *(ReactionDamageGateDecision.ALLOWED for _ in range(8)),
        ReactionDamageGateDecision.BLOCKED,
    )
    record = runtime.gate_records[0]
    assert record.accepted_count == 8
    assert isinstance(record.cause, ScheduledStateTickCause)
    assert record.cause.tick_index == 8

    next_window = _prepare_burning(runtime, frame=120, tick_index=9)

    assert next_window.decision is ReactionDamageGateDecision.ALLOWED
    assert runtime.gate_records[0].window_started_frame == 120
    assert runtime.gate_records[0].accepted_count == 1


def _runtime() -> ReactionRuntime:
    return create_default_reaction_bootstrap().create_runtime()


def _prepare(
    runtime: ReactionRuntime,
    *,
    frame: int,
    definition_key: str,
):
    definition = runtime.gate_definition(definition_key)
    operation_id = f"gate:{definition_key}:{frame}:{runtime.version}"
    planner = runtime.begin_gate_batch(frame, operation_id)
    request = ReactionDamageGateRequest(
        gate_request_ref=f"{operation_id}:request",
        frame=frame,
        definition=definition,
        trigger_source_ref=ElementalSourceRef("character:slot_1"),
        damage_target_ref=ElementalSubjectRef.target("target:target_1"),
        parent_occurrence_ref=f"{operation_id}:occurrence:0",
        parent_effect_ref=f"{operation_id}:effect:0",
    )
    resolution = planner.prepare(request)
    plan = planner.seal()
    runtime.validate_gate_plan(plan)
    runtime.commit_prevalidated_gate_plan(plan)
    return resolution


def _prepare_burning(runtime: ReactionRuntime, *, frame: int, tick_index: int):
    definition = runtime.gate_definition(BURNING_GATE_DEFINITION_KEY)
    operation_id = f"burning-gate:{frame}:{runtime.version}"
    planner = runtime.begin_gate_batch(frame, operation_id)
    resolution = planner.prepare(
        ReactionDamageGateRequest(
            gate_request_ref=f"{operation_id}:request",
            frame=frame,
            definition=definition,
            trigger_source_ref=ElementalSourceRef("character:slot_1"),
            damage_target_ref=ElementalSubjectRef.target("target:target_1"),
            parent_occurrence_ref=None,
            parent_effect_ref=f"{operation_id}:effect",
            cause=ScheduledStateTickCause(
                state_instance_ref=ReactionStateInstanceRef("reaction-state-instance:burning"),
                scheduled_frame=frame,
                tick_kind=ScheduledStateTickKind.BURNING_DAMAGE,
                tick_index=tick_index,
            ),
        )
    )
    runtime.commit_prevalidated_gate_plan(planner.seal())
    return resolution
