from __future__ import annotations

from typing import cast

import pytest

from genshin_sim.core.coordination.elemental_reaction import (
    ElementalInteractionError,
    ElementalStateFrameCoordinator,
    StellarConductAttachmentRecordingOutcome,
    plan_polestar_field_occurrence,
    record_stellar_conduct_attachment,
)
from genshin_sim.core.coordination.elemental_reaction.lifecycle import (
    PolestarFieldExpiryCoordinator,
)
from genshin_sim.core.coordination.elemental_reaction.spatial import (
    ReactionSpatialPlanningAdapter,
)
from genshin_sim.core.coordination.elemental_reaction.stellar_conduct import (
    PolestarFieldPlanOutcome,
    StellarConductPlanningError,
)
from genshin_sim.core.elements import Element, ElementalSourceRef, ElementalSubjectRef
from genshin_sim.core.simulation import SimulationContext
from genshin_sim.core.space import Space, SpatialEntity, SpatialEntityKind, Vector3
from genshin_sim.core.systems.aura import AuraRuntime
from genshin_sim.core.systems.aura_icd import AuraIcdRuntime
from genshin_sim.core.systems.reaction import (
    PolestarFieldStatePlanningIntent,
    ReactionRegistry,
    ReactionRuntime,
    ReactionStateInstanceRef,
    SpatialEntityCreationEffect,
    StellarConductAttachmentRecord,
    StellarConductCounterSettlementRootWork,
    create_default_reaction_bootstrap,
)
from genshin_sim.core.systems.reaction.mechanics.stellar_conduct.keys import (
    STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES,
    STELLAR_CONDUCT_FIELD_SPATIAL_PROFILE_KEY,
    STELLAR_CONDUCT_FIELD_STATE_KEY,
    STELLAR_CONDUCT_TEAM_SCOPE,
)
from genshin_sim.core.systems.reaction.states import STELLAR_CONDUCT_COUNTER_WINDOW_FRAMES

SOURCE = ElementalSourceRef("character:slot_1")
TARGET_1 = ElementalSubjectRef.target("target:target_1")
TARGET_2 = ElementalSubjectRef.target("target:target_2")


class _FakeEventBus:
    def __init__(self) -> None:
        self.events: list[object] = []

    def publish(self, event: object) -> None:
        self.events.append(event)


class _FakeSpaceRuntime:
    def __init__(self, space: Space) -> None:
        self.space = space

    def get_entity(self, entity_id: str) -> SpatialEntity | None:
        return self.space.get_entity(entity_id)


class _FakeContext:
    def __init__(self, space_runtime: _FakeSpaceRuntime) -> None:
        self.space_runtime = space_runtime
        self.events = _FakeEventBus()


def _target_entity(subject_ref: ElementalSubjectRef, position: Vector3) -> SpatialEntity:
    return SpatialEntity(
        entity_id=subject_ref.entity_id,
        kind=SpatialEntityKind.TARGET,
        position=position,
    )


def _fixtures(
    *targets: tuple[ElementalSubjectRef, Vector3],
) -> tuple[ReactionRuntime, Space, _FakeContext]:
    runtime = create_default_reaction_bootstrap().create_runtime()
    runtime.update_frame(None, 0)
    space = Space(tuple(_target_entity(subject, position) for subject, position in targets))
    context = _FakeContext(_FakeSpaceRuntime(space))
    return runtime, space, context


def _intent(
    occurrence_ref: str,
    subject_ref: ElementalSubjectRef = TARGET_1,
    *,
    frame: int = 0,
) -> PolestarFieldStatePlanningIntent:
    return PolestarFieldStatePlanningIntent(
        intent_ref=f"{occurrence_ref}:polestar-field-plan",
        parent_occurrence_ref=occurrence_ref,
        instance_ref=ReactionStateInstanceRef(f"reaction-state:polestar-field:{occurrence_ref}"),
        subject_ref=subject_ref,
        space_entity_ref=f"reaction_object:polestar_field:{occurrence_ref}",
        trigger_source_ref=SOURCE,
        team_ref=STELLAR_CONDUCT_TEAM_SCOPE,
        created_frame=frame,
        expires_at_frame=frame + STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES,
        excluded_attack_ref=f"impact:{occurrence_ref}",
    )


def _spatial_effect(intent: PolestarFieldStatePlanningIntent) -> SpatialEntityCreationEffect:
    return SpatialEntityCreationEffect(
        effect_ref=f"{intent.parent_occurrence_ref}:polestar-field-spatial-create",
        parent_occurrence_ref=intent.parent_occurrence_ref,
        space_entity_ref=intent.space_entity_ref,
        owner_key=STELLAR_CONDUCT_TEAM_SCOPE,
        source_key=intent.instance_ref.value,
        tags=(STELLAR_CONDUCT_FIELD_STATE_KEY, STELLAR_CONDUCT_FIELD_SPATIAL_PROFILE_KEY),
        created_frame=intent.created_frame,
        expires_at_frame=intent.expires_at_frame,
    )


def _record(
    record_ref: str,
    targets: tuple[ElementalSubjectRef, ...],
    *,
    attack_ref: str = "impact:attack",
    frame: int = 1,
) -> StellarConductAttachmentRecord:
    return StellarConductAttachmentRecord(
        record_ref=record_ref,
        attack_ref=attack_ref,
        element=Element.CRYO,
        frame=frame,
        target_refs=targets,
    )


def test_plan_creates_field_and_counter_when_none_exists() -> None:
    runtime, _, context = _fixtures((TARGET_1, Vector3(0.0, 0.0, 0.0)))
    state_planner = runtime.begin_state_batch(0, "polestar:plan:0")
    spatial_planner = ReactionSpatialPlanningAdapter(context.space_runtime.space).begin_batch(
        operation_id="polestar:plan:0",
        frame=0,
    )

    intent = _intent("occurrence:1")
    result = plan_polestar_field_occurrence(
        context=context,
        state_planner=state_planner,
        spatial_planner=spatial_planner,
        intent=intent,
        spatial_effect=_spatial_effect(intent),
    )

    assert result.outcome is PolestarFieldPlanOutcome.CREATED
    field = state_planner.polestar_field_for(intent.instance_ref)
    assert field is not None
    assert field.team_ref == STELLAR_CONDUCT_TEAM_SCOPE
    counter = state_planner.stellar_conduct_counter_for(STELLAR_CONDUCT_TEAM_SCOPE)
    assert counter is not None
    assert counter.next_settlement_frame == STELLAR_CONDUCT_COUNTER_WINDOW_FRAMES
    assert counter.excluded_attack_refs == ("impact:occurrence:1",)
    assert len(spatial_planner.creation_receipts) == 1

    space_plan = spatial_planner.seal()
    assert len(space_plan.creations) == 1
    assert space_plan.creations[0].entity_id == intent.space_entity_ref
    assert space_plan.creations[0].source_key == intent.instance_ref.value


def test_plan_refreshes_field_when_retrigger_inside_radius() -> None:
    runtime, space, context = _fixtures(
        (TARGET_1, Vector3(0.0, 0.0, 0.0)),
        (TARGET_2, Vector3(5.0, 0.0, 0.0)),
    )
    spatial_adapter = ReactionSpatialPlanningAdapter(context.space_runtime.space)
    first = _intent("occurrence:1")
    first_state_planner = runtime.begin_state_batch(0, "polestar:plan:0")
    spatial_planner = spatial_adapter.begin_batch(operation_id="polestar:plan:0", frame=0)
    plan_polestar_field_occurrence(
        context=context,
        state_planner=first_state_planner,
        spatial_planner=spatial_planner,
        intent=first,
        spatial_effect=_spatial_effect(first),
    )
    runtime.commit_prevalidated_state_plan(first_state_planner.seal())
    spatial_adapter.commit_prevalidated(spatial_planner.seal())
    runtime.update_frame(None, 30)
    space.update_frame(cast(SimulationContext, None), 30)

    second = _intent("occurrence:2", TARGET_2, frame=30)
    state_planner = runtime.begin_state_batch(30, "polestar:plan:1")
    spatial_planner = spatial_adapter.begin_batch(operation_id="polestar:plan:1", frame=30)
    result = plan_polestar_field_occurrence(
        context=context,
        state_planner=state_planner,
        spatial_planner=spatial_planner,
        intent=second,
        spatial_effect=_spatial_effect(second),
    )

    assert result.outcome is PolestarFieldPlanOutcome.REFRESHED
    refreshed = state_planner.polestar_field_for(first.instance_ref)
    assert refreshed is not None
    assert refreshed.expires_at_frame == 30 + STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES
    assert refreshed.revision == 2
    counter = state_planner.stellar_conduct_counter_for(STELLAR_CONDUCT_TEAM_SCOPE)
    assert counter is not None
    assert counter.window_start_frame == 0
    assert counter.next_settlement_frame == STELLAR_CONDUCT_COUNTER_WINDOW_FRAMES
    assert counter.excluded_attack_refs == ("impact:occurrence:1",)
    assert len(state_planner.active_polestar_fields()) == 1
    assert spatial_planner.creation_receipts == ()
    assert spatial_planner.seal().removals == ()


def test_plan_replaces_field_when_retrigger_outside_radius() -> None:
    runtime, space, context = _fixtures(
        (TARGET_1, Vector3(0.0, 0.0, 0.0)),
        (TARGET_2, Vector3(30.0, 0.0, 0.0)),
    )
    spatial_adapter = ReactionSpatialPlanningAdapter(context.space_runtime.space)
    first = _intent("occurrence:1")
    first_state_planner = runtime.begin_state_batch(0, "polestar:plan:0")
    spatial_planner = spatial_adapter.begin_batch(operation_id="polestar:plan:0", frame=0)
    plan_polestar_field_occurrence(
        context=context,
        state_planner=first_state_planner,
        spatial_planner=spatial_planner,
        intent=first,
        spatial_effect=_spatial_effect(first),
    )
    runtime.commit_prevalidated_state_plan(first_state_planner.seal())
    spatial_adapter.commit_prevalidated(spatial_planner.seal())
    runtime.update_frame(None, 30)
    space.update_frame(cast(SimulationContext, None), 30)

    second = _intent("occurrence:2", TARGET_2, frame=30)
    state_planner = runtime.begin_state_batch(30, "polestar:plan:1")
    spatial_planner = spatial_adapter.begin_batch(operation_id="polestar:plan:1", frame=30)
    result = plan_polestar_field_occurrence(
        context=context,
        state_planner=state_planner,
        spatial_planner=spatial_planner,
        intent=second,
        spatial_effect=_spatial_effect(second),
    )

    assert result.outcome is PolestarFieldPlanOutcome.REPLACED
    assert result.removed_field_instance_ref == first.instance_ref
    assert state_planner.polestar_field_for(first.instance_ref) is None
    new_field = state_planner.polestar_field_for(second.instance_ref)
    assert new_field is not None
    counter = state_planner.stellar_conduct_counter_for(STELLAR_CONDUCT_TEAM_SCOPE)
    assert counter is not None
    assert counter.window_start_frame == 0
    assert counter.excluded_attack_refs == ("impact:occurrence:2",)
    space_plan = spatial_planner.seal()
    assert [entity.entity_id for entity in space_plan.removals] == [first.space_entity_ref]
    assert [entity.entity_id for entity in space_plan.creations] == [second.space_entity_ref]


def test_plan_rejects_missing_anchor() -> None:
    runtime, _, context = _fixtures((TARGET_1, Vector3(0.0, 0.0, 0.0)))
    state_planner = runtime.begin_state_batch(0, "polestar:plan:0")
    spatial_planner = ReactionSpatialPlanningAdapter(context.space_runtime.space).begin_batch(
        operation_id="polestar:plan:0", frame=0
    )
    intent = _intent("occurrence:1", TARGET_2)

    with pytest.raises(StellarConductPlanningError, match="主体空间锚点"):
        plan_polestar_field_occurrence(
            context=context,
            state_planner=state_planner,
            spatial_planner=spatial_planner,
            intent=intent,
            spatial_effect=_spatial_effect(intent),
        )


def test_attachment_recording_dedup_exclusion_and_space_condition() -> None:
    runtime, space, context = _fixtures(
        (TARGET_1, Vector3(0.0, 0.0, 0.0)),
        (TARGET_2, Vector3(30.0, 0.0, 0.0)),
    )
    spatial_adapter = ReactionSpatialPlanningAdapter(space)
    intent = _intent("occurrence:1")
    space_planner = spatial_adapter.begin_batch(operation_id="polestar:record:0", frame=0)
    anchor = space.get_entity(TARGET_1.entity_id)
    assert anchor is not None
    space_planner.prepare_create(_spatial_effect(intent), anchor=anchor)
    spatial_adapter.commit_prevalidated(space_planner.seal())
    state_planner = runtime.begin_state_batch(0, "polestar:record:0")
    state_planner.create_polestar_field(intent)
    state_planner.create_stellar_conduct_counter(
        team_ref=STELLAR_CONDUCT_TEAM_SCOPE,
        subject_ref=TARGET_1,
        frame=0,
        excluded_attack_refs=("impact:occurrence:1",),
    )

    excluded = record_stellar_conduct_attachment(
        context=context,
        state_planner=state_planner,
        team_ref=STELLAR_CONDUCT_TEAM_SCOPE,
        record=_record("record:trigger", (TARGET_1,), attack_ref="impact:occurrence:1"),
    )
    assert excluded.outcome is StellarConductAttachmentRecordingOutcome.EXCLUDED_ATTACK
    assert not excluded.recorded

    recorded = record_stellar_conduct_attachment(
        context=context,
        state_planner=state_planner,
        team_ref=STELLAR_CONDUCT_TEAM_SCOPE,
        record=_record("record:1", (TARGET_1, TARGET_2)),
    )
    assert recorded.outcome is StellarConductAttachmentRecordingOutcome.RECORDED
    assert recorded.counter is not None
    assert recorded.counter.pending_count == 1
    assert recorded.counter.recorded_record_refs == ("record:1",)

    duplicate = record_stellar_conduct_attachment(
        context=context,
        state_planner=state_planner,
        team_ref=STELLAR_CONDUCT_TEAM_SCOPE,
        record=_record("record:1", (TARGET_1,)),
    )
    assert duplicate.outcome is StellarConductAttachmentRecordingOutcome.DUPLICATE_RECORD

    outside = record_stellar_conduct_attachment(
        context=context,
        state_planner=state_planner,
        team_ref=STELLAR_CONDUCT_TEAM_SCOPE,
        record=_record("record:2", (TARGET_2,)),
    )
    assert outside.outcome is StellarConductAttachmentRecordingOutcome.TARGETS_OUTSIDE_FIELD

    expired = record_stellar_conduct_attachment(
        context=context,
        state_planner=state_planner,
        team_ref=STELLAR_CONDUCT_TEAM_SCOPE,
        record=_record("record:3", (TARGET_1,), frame=STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES),
    )
    assert expired.outcome is StellarConductAttachmentRecordingOutcome.FIELD_EXPIRED


def test_attachment_recording_without_session_is_no_op() -> None:
    runtime, _, context = _fixtures((TARGET_1, Vector3(0.0, 0.0, 0.0)))
    state_planner = runtime.begin_state_batch(0, "polestar:record:1")

    recording = record_stellar_conduct_attachment(
        context=context,
        state_planner=state_planner,
        team_ref=STELLAR_CONDUCT_TEAM_SCOPE,
        record=_record("record:1", (TARGET_1,)),
    )
    assert recording.outcome is StellarConductAttachmentRecordingOutcome.NO_ACTIVE_SESSION
    assert recording.counter is None


def test_frame_normalizer_settles_counter_window_and_publishes_root() -> None:
    runtime = ReactionRuntime(ReactionRegistry())
    runtime.update_frame(None, 0)
    state_planner = runtime.begin_state_batch(0, "counter:setup")
    state_planner.create_stellar_conduct_counter(
        team_ref=STELLAR_CONDUCT_TEAM_SCOPE,
        subject_ref=TARGET_1,
        frame=0,
    )
    state_planner.append_stellar_conduct_attachment_record(
        team_ref=STELLAR_CONDUCT_TEAM_SCOPE,
        record=_record("record:1", (TARGET_1,)),
    )
    state_planner.append_stellar_conduct_attachment_record(
        team_ref=STELLAR_CONDUCT_TEAM_SCOPE,
        record=_record("record:2", (TARGET_1,)),
    )
    runtime.commit_prevalidated_state_plan(state_planner.seal())
    coordinator = ElementalStateFrameCoordinator(AuraRuntime(), AuraIcdRuntime(), runtime)

    record = coordinator.normalize(None, STELLAR_CONDUCT_COUNTER_WINDOW_FRAMES)

    assert len(record.scheduled_roots) == 1
    root = record.scheduled_roots[0]
    assert isinstance(root, StellarConductCounterSettlementRootWork)
    assert root.window_index == 1
    counter = runtime.stellar_conduct_counter_state_for(STELLAR_CONDUCT_TEAM_SCOPE)
    assert counter is not None
    assert counter.settled_stacks == 2
    assert counter.stacks == 2
    assert counter.pending_count == 0
    assert counter.window_index == 2
    assert counter.next_settlement_frame == 2 * STELLAR_CONDUCT_COUNTER_WINDOW_FRAMES

    coordinator.normalize(None, 2 * STELLAR_CONDUCT_COUNTER_WINDOW_FRAMES)
    counter = runtime.stellar_conduct_counter_state_for(STELLAR_CONDUCT_TEAM_SCOPE)
    assert counter is not None
    assert counter.settled_stacks == 0
    assert counter.window_index == 3


def test_frame_normalizer_expires_field_and_counter_together() -> None:
    runtime, space, context = _fixtures((TARGET_1, Vector3(0.0, 0.0, 0.0)))
    spatial_adapter = ReactionSpatialPlanningAdapter(space)
    state_planner = runtime.begin_state_batch(0, "polestar:expiry:setup")
    intent = _intent("occurrence:1")
    state_planner.create_polestar_field(intent)
    state_planner.create_stellar_conduct_counter(
        team_ref=STELLAR_CONDUCT_TEAM_SCOPE,
        subject_ref=TARGET_1,
        frame=0,
    )
    state_planner.append_stellar_conduct_attachment_record(
        team_ref=STELLAR_CONDUCT_TEAM_SCOPE,
        record=_record("record:1", (TARGET_1,)),
    )
    runtime.commit_prevalidated_state_plan(state_planner.seal())
    space_planner = spatial_adapter.begin_batch(operation_id="polestar:expiry:setup", frame=0)
    anchor = space.get_entity(TARGET_1.entity_id)
    assert anchor is not None
    space_planner.prepare_create(_spatial_effect(intent), anchor=anchor)
    spatial_adapter.commit_prevalidated(space_planner.seal())

    coordinator = ElementalStateFrameCoordinator(
        AuraRuntime(),
        AuraIcdRuntime(),
        runtime,
        polestar_field_expiry_coordinator=PolestarFieldExpiryCoordinator(
            reaction_state_port=runtime,
            spatial_planning_port=spatial_adapter,
        ),
    )

    coordinator.normalize(context, STELLAR_CONDUCT_COUNTER_WINDOW_FRAMES)
    record = coordinator.normalize(context, STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES)

    assert len(record.lifecycle_works) == 1
    assert runtime.polestar_field_state_for(intent.instance_ref) is None
    assert runtime.stellar_conduct_counter_state_for(STELLAR_CONDUCT_TEAM_SCOPE) is None
    assert space.get_entity(intent.space_entity_ref) is None


def test_frame_normalizer_requires_polestar_expiry_coordinator() -> None:
    runtime = ReactionRuntime(ReactionRegistry())
    runtime.update_frame(None, 0)
    state_planner = runtime.begin_state_batch(0, "polestar:expiry:missing")
    state_planner.create_polestar_field(_intent("occurrence:1"))
    runtime.commit_prevalidated_state_plan(state_planner.seal())
    coordinator = ElementalStateFrameCoordinator(AuraRuntime(), AuraIcdRuntime(), runtime)

    with pytest.raises(ElementalInteractionError, match="极星辉域缺少生命周期协调器"):
        coordinator.normalize(None, STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES)
