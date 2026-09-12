from __future__ import annotations

from typing import cast

import pytest

from genshin_sim.core.coordination.elemental_reaction import (
    ElementalInteractionError,
    ElementalStateFrameCoordinator,
    StellarSwirlVortexPlanOutcome,
    plan_stellar_swirl_vortex_occurrence,
)
from genshin_sim.core.coordination.elemental_reaction.lifecycle import (
    StellarSwirlVortexExpiryCoordinator,
)
from genshin_sim.core.coordination.elemental_reaction.spatial import (
    ReactionSpatialPlanningAdapter,
    ReactionStateBindingConflictError,
    validate_stellar_swirl_vortex_space_bindings,
)
from genshin_sim.core.elements import ElementalSourceRef, ElementalSubjectRef
from genshin_sim.core.simulation import SimulationContext
from genshin_sim.core.space import Space, SpatialEntity, SpatialEntityKind, Vector3
from genshin_sim.core.systems.aura import AuraRuntime
from genshin_sim.core.systems.aura_icd import AuraIcdRuntime
from genshin_sim.core.systems.reaction import (
    ReactionRuntime,
    ReactionStateInstanceRef,
    SpatialEntityCreationEffect,
    StellarSwirlVortexStatePlanningIntent,
    create_default_reaction_bootstrap,
)
from genshin_sim.core.systems.reaction.mechanics.stellar_swirl import (
    STELLAR_SWIRL_VORTEX_SPATIAL_PROFILE_KEY,
    STELLAR_SWIRL_VORTEX_STATE_KEY,
)
from genshin_sim.core.systems.reaction.states import STELLAR_SWIRL_VORTEX_LIFETIME_FRAMES

SOURCE = ElementalSourceRef("character:slot_1")
SOURCE_B = ElementalSourceRef("character:slot_2")
SOURCE_C = ElementalSourceRef("character:slot_3")
TARGET_1 = ElementalSubjectRef.target("target:target_1")
TARGET_2 = ElementalSubjectRef.target("target:target_2")
TARGET_3 = ElementalSubjectRef.target("target:target_3")


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
    participants: tuple[ElementalSourceRef, ...] = (SOURCE,),
) -> StellarSwirlVortexStatePlanningIntent:
    return StellarSwirlVortexStatePlanningIntent(
        intent_ref=f"{occurrence_ref}:stellar-swirl-vortex-plan",
        parent_occurrence_ref=occurrence_ref,
        instance_ref=ReactionStateInstanceRef(
            f"reaction-state:stellar-swirl-vortex:{occurrence_ref}"
        ),
        subject_ref=subject_ref,
        space_entity_ref=f"reaction_object:stellar_swirl_vortex:{occurrence_ref}",
        trigger_source_ref=participants[0],
        scope_ref="battle",
        created_frame=frame,
        expires_at_frame=frame + STELLAR_SWIRL_VORTEX_LIFETIME_FRAMES,
        reaction_participants=participants,
    )


def _spatial_effect(intent: StellarSwirlVortexStatePlanningIntent) -> SpatialEntityCreationEffect:
    return SpatialEntityCreationEffect(
        effect_ref=f"{intent.parent_occurrence_ref}:stellar-swirl-vortex-spatial-create",
        parent_occurrence_ref=intent.parent_occurrence_ref,
        space_entity_ref=intent.space_entity_ref,
        owner_key="battle",
        source_key=intent.instance_ref.value,
        tags=(STELLAR_SWIRL_VORTEX_STATE_KEY, STELLAR_SWIRL_VORTEX_SPATIAL_PROFILE_KEY),
        created_frame=intent.created_frame,
        expires_at_frame=intent.expires_at_frame,
    )


def test_plan_creates_vortex_when_none_exists() -> None:
    runtime, _, context = _fixtures((TARGET_1, Vector3(0.0, 0.0, 0.0)))
    state_planner = runtime.begin_state_batch(0, "swirl:plan:0")
    spatial_planner = ReactionSpatialPlanningAdapter(context.space_runtime.space).begin_batch(
        operation_id="swirl:plan:0",
        frame=0,
    )

    intent = _intent("occurrence:1")
    result = plan_stellar_swirl_vortex_occurrence(
        context=context,
        state_planner=state_planner,
        spatial_planner=spatial_planner,
        intent=intent,
        spatial_effect=_spatial_effect(intent),
    )

    assert result.outcome is StellarSwirlVortexPlanOutcome.CREATED
    vortex = state_planner.stellar_swirl_vortex_for(intent.instance_ref)
    assert vortex is not None
    assert vortex.level == 1
    assert vortex.scope_ref == "battle"
    assert vortex.last_reaction_source_ref == SOURCE
    assert vortex.last_reaction_occurrence_ref == "occurrence:1"
    assert len(vortex.participants) == 1
    assert vortex.participants[0].participant_ref == SOURCE
    assert vortex.participants[0].first_reaction_frame == 0
    assert len(spatial_planner.creation_receipts) == 1
    space_plan = spatial_planner.seal()
    assert space_plan.creations[0].source_key == intent.instance_ref.value

    state_plan = state_planner.seal()
    validate_stellar_swirl_vortex_space_bindings(state_plan, space_plan)


def test_plan_levels_up_vortex_in_same_batch_without_space_change() -> None:
    runtime, _, context = _fixtures(
        (TARGET_1, Vector3(0.0, 0.0, 0.0)),
        (TARGET_2, Vector3(2.0, 0.0, 0.0)),
    )
    state_planner = runtime.begin_state_batch(0, "swirl:plan:0")
    spatial_planner = ReactionSpatialPlanningAdapter(context.space_runtime.space).begin_batch(
        operation_id="swirl:plan:0",
        frame=0,
    )

    first = _intent("occurrence:1")
    plan_stellar_swirl_vortex_occurrence(
        context=context,
        state_planner=state_planner,
        spatial_planner=spatial_planner,
        intent=first,
        spatial_effect=_spatial_effect(first),
    )
    second = _intent("occurrence:2", TARGET_2, participants=(SOURCE_B,))
    result = plan_stellar_swirl_vortex_occurrence(
        context=context,
        state_planner=state_planner,
        spatial_planner=spatial_planner,
        intent=second,
        spatial_effect=_spatial_effect(second),
    )

    assert result.outcome is StellarSwirlVortexPlanOutcome.LEVELED
    vortex = state_planner.stellar_swirl_vortex_for(first.instance_ref)
    assert vortex is not None
    assert vortex.level == 2
    assert vortex.revision == 2
    # 升级不移动锚点、不刷新爆炸计时；账本按首次参与帧升序合并。
    assert vortex.created_frame == 0
    assert vortex.expires_at_frame == STELLAR_SWIRL_VORTEX_LIFETIME_FRAMES
    assert [item.participant_ref for item in vortex.participants] == [SOURCE, SOURCE_B]
    assert vortex.participants[0].first_reaction_frame == 0
    assert vortex.participants[1].first_reaction_frame == 0
    assert vortex.last_reaction_source_ref == SOURCE_B
    assert vortex.last_reaction_occurrence_ref == "occurrence:2"
    # 升级事件的空间创建声明不会进入计划。
    space_plan = spatial_planner.seal()
    assert len(space_plan.creations) == 1
    assert space_plan.creations[0].entity_id == first.space_entity_ref


def test_plan_merges_ledger_frames_across_batches() -> None:
    runtime, _, context = _fixtures((TARGET_1, Vector3(0.0, 0.0, 0.0)))
    spatial_adapter = ReactionSpatialPlanningAdapter(context.space_runtime.space)

    first = _intent("occurrence:1", participants=(SOURCE, SOURCE_B))
    state_planner = runtime.begin_state_batch(0, "swirl:plan:0")
    plan_stellar_swirl_vortex_occurrence(
        context=context,
        state_planner=state_planner,
        spatial_planner=spatial_adapter.begin_batch(operation_id="swirl:plan:0", frame=0),
        intent=first,
        spatial_effect=_spatial_effect(first),
    )
    runtime.commit_prevalidated_state_plan(state_planner.seal())
    spatial_adapter.commit_prevalidated(
        spatial_adapter.begin_batch(operation_id="swirl:seal:0", frame=0).seal()
    )
    runtime.update_frame(None, 30)
    context.space_runtime.space.update_frame(cast(SimulationContext, None), 30)

    second = _intent("occurrence:2", frame=30, participants=(SOURCE_B, SOURCE_C))
    state_planner = runtime.begin_state_batch(30, "swirl:plan:1")
    result = plan_stellar_swirl_vortex_occurrence(
        context=context,
        state_planner=state_planner,
        spatial_planner=spatial_adapter.begin_batch(operation_id="swirl:plan:1", frame=30),
        intent=second,
        spatial_effect=_spatial_effect(second),
    )

    assert result.outcome is StellarSwirlVortexPlanOutcome.LEVELED
    vortex = state_planner.stellar_swirl_vortex_for(first.instance_ref)
    assert vortex is not None
    assert [item.participant_ref for item in vortex.participants] == [SOURCE, SOURCE_B, SOURCE_C]
    # SOURCE 未参与第二次风反应：最近参与帧保持 0；SOURCE_B 刷新为 30；SOURCE_C 首次参与。
    assert vortex.participants[0].last_reaction_frame == 0
    assert vortex.participants[1].last_reaction_frame == 30
    assert vortex.participants[2].first_reaction_frame == 30


def test_plan_creates_vortex_with_ledger_trim_fallback() -> None:
    runtime, _, context = _fixtures((TARGET_1, Vector3(0.0, 0.0, 0.0)))
    state_planner = runtime.begin_state_batch(0, "swirl:plan:0")
    spatial_planner = ReactionSpatialPlanningAdapter(context.space_runtime.space).begin_batch(
        operation_id="swirl:plan:0",
        frame=0,
    )

    participants = (
        SOURCE,
        SOURCE_B,
        ElementalSourceRef("character:slot_4"),
        ElementalSourceRef("character:slot_5"),
        ElementalSourceRef("character:slot_6"),
    )
    intent = _intent("occurrence:1", participants=participants)
    result = plan_stellar_swirl_vortex_occurrence(
        context=context,
        state_planner=state_planner,
        spatial_planner=spatial_planner,
        intent=intent,
        spatial_effect=_spatial_effect(intent),
    )

    assert result.outcome is StellarSwirlVortexPlanOutcome.CREATED
    vortex = state_planner.stellar_swirl_vortex_for(intent.instance_ref)
    assert vortex is not None
    # 超出 4 名时按首次参与帧升序保留前 4（确定性兜底）。
    assert len(vortex.participants) == 4
    assert vortex.participants[0].participant_ref == SOURCE


def test_plan_explodes_committed_vortex_at_level_6() -> None:
    runtime, space, context = _fixtures((TARGET_1, Vector3(0.0, 0.0, 0.0)))
    spatial_adapter = ReactionSpatialPlanningAdapter(context.space_runtime.space)

    first = _intent("occurrence:1")
    for level in range(1, 6):
        state_planner = runtime.begin_state_batch(0, f"swirl:setup:{level}")
        spatial_planner = spatial_adapter.begin_batch(operation_id=f"swirl:setup:{level}", frame=0)
        if level == 1:
            plan_stellar_swirl_vortex_occurrence(
                context=context,
                state_planner=state_planner,
                spatial_planner=spatial_planner,
                intent=first,
                spatial_effect=_spatial_effect(first),
            )
        else:
            plan_stellar_swirl_vortex_occurrence(
                context=context,
                state_planner=state_planner,
                spatial_planner=spatial_planner,
                intent=_intent(f"occurrence:{level}"),
                spatial_effect=_spatial_effect(_intent(f"occurrence:{level}")),
            )
        runtime.commit_prevalidated_state_plan(state_planner.seal())
        spatial_adapter.commit_prevalidated(spatial_planner.seal())

    vortex = runtime.active_stellar_swirl_vortexes(scope_ref="battle")
    assert len(vortex) == 1
    assert vortex[0].level == 5

    sixth = _intent("occurrence:6")
    state_planner = runtime.begin_state_batch(0, "swirl:explode")
    spatial_planner = spatial_adapter.begin_batch(operation_id="swirl:explode", frame=0)
    result = plan_stellar_swirl_vortex_occurrence(
        context=context,
        state_planner=state_planner,
        spatial_planner=spatial_planner,
        intent=sixth,
        spatial_effect=_spatial_effect(sixth),
    )

    assert result.outcome is StellarSwirlVortexPlanOutcome.EXPLODED
    assert result.removed_vortex_instance_ref == first.instance_ref
    space_plan = spatial_planner.seal()
    assert [entity.entity_id for entity in space_plan.removals] == [first.space_entity_ref]
    state_plan = state_planner.seal()

    from genshin_sim.core.coordination.elemental_reaction.spatial import (
        validate_stellar_swirl_vortex_space_terminalizations,
    )

    validate_stellar_swirl_vortex_space_terminalizations(state_plan, space_plan)
    runtime.commit_prevalidated_state_plan(state_plan)
    spatial_adapter.commit_prevalidated(space_plan)
    assert runtime.stellar_swirl_vortex_state_for(first.instance_ref) is None
    assert space.get_entity(first.space_entity_ref) is None


def test_plan_same_batch_explode_then_next_target_creates_new_vortex() -> None:
    runtime, space, context = _fixtures(
        (TARGET_1, Vector3(0.0, 0.0, 0.0)),
        (TARGET_2, Vector3(2.0, 0.0, 0.0)),
    )
    state_planner = runtime.begin_state_batch(0, "swirl:plan:0")
    spatial_planner = ReactionSpatialPlanningAdapter(context.space_runtime.space).begin_batch(
        operation_id="swirl:plan:0",
        frame=0,
    )

    first = _intent("occurrence:1", TARGET_1)
    plan_stellar_swirl_vortex_occurrence(
        context=context,
        state_planner=state_planner,
        spatial_planner=spatial_planner,
        intent=first,
        spatial_effect=_spatial_effect(first),
    )
    outcome = None
    for index in range(2, 7):
        event = _intent(f"occurrence:{index}", TARGET_1)
        outcome = plan_stellar_swirl_vortex_occurrence(
            context=context,
            state_planner=state_planner,
            spatial_planner=spatial_planner,
            intent=event,
            spatial_effect=_spatial_effect(event),
        )
    assert outcome is not None
    assert outcome.outcome is StellarSwirlVortexPlanOutcome.EXPLODED

    # 同帧后序目标事件看到无风旋，创建等级 1 的新风旋并锚定该目标。
    seventh = _intent("occurrence:7", TARGET_2)
    outcome = plan_stellar_swirl_vortex_occurrence(
        context=context,
        state_planner=state_planner,
        spatial_planner=spatial_planner,
        intent=seventh,
        spatial_effect=_spatial_effect(seventh),
    )
    assert outcome.outcome is StellarSwirlVortexPlanOutcome.CREATED
    new_vortex = state_planner.stellar_swirl_vortex_for(seventh.instance_ref)
    assert new_vortex is not None
    assert new_vortex.level == 1
    assert new_vortex.subject_ref == TARGET_2
    assert new_vortex.created_by_occurrence_ref == "occurrence:7"
    assert new_vortex.last_reaction_source_ref == SOURCE

    state_plan = state_planner.seal()
    space_plan = spatial_planner.seal()
    # 旧风旋在本批次内创建又爆炸终结：State 无残留；仅新风旋创建空间实体。
    assert [record.instance_ref for record in state_plan.replacement_records] == [
        seventh.instance_ref
    ]
    assert [entity.entity_id for entity in space_plan.creations] == [seventh.space_entity_ref]
    assert space_plan.removals == ()
    validate_stellar_swirl_vortex_space_bindings(state_plan, space_plan)
    runtime.commit_prevalidated_state_plan(state_plan)
    spatial_adapter = ReactionSpatialPlanningAdapter(space)
    spatial_adapter.commit_prevalidated(space_plan)
    assert space.get_entity(seventh.space_entity_ref) is not None
    assert space.get_entity(first.space_entity_ref) is None


def test_frame_normalizer_expires_vortex() -> None:
    runtime, space, context = _fixtures((TARGET_1, Vector3(0.0, 0.0, 0.0)))
    spatial_adapter = ReactionSpatialPlanningAdapter(context.space_runtime.space)
    intent = _intent("occurrence:1")
    state_planner = runtime.begin_state_batch(0, "swirl:setup")
    spatial_planner = spatial_adapter.begin_batch(operation_id="swirl:setup", frame=0)
    plan_stellar_swirl_vortex_occurrence(
        context=context,
        state_planner=state_planner,
        spatial_planner=spatial_planner,
        intent=intent,
        spatial_effect=_spatial_effect(intent),
    )
    runtime.commit_prevalidated_state_plan(state_planner.seal())
    spatial_adapter.commit_prevalidated(spatial_planner.seal())

    coordinator = ElementalStateFrameCoordinator(
        AuraRuntime(),
        AuraIcdRuntime(),
        runtime,
        stellar_swirl_vortex_expiry_coordinator=StellarSwirlVortexExpiryCoordinator(
            reaction_state_port=runtime,
            spatial_planning_port=spatial_adapter,
        ),
    )
    coordinator.normalize(context, 60)
    record = coordinator.normalize(context, STELLAR_SWIRL_VORTEX_LIFETIME_FRAMES)

    assert len(record.lifecycle_works) == 1
    assert runtime.stellar_swirl_vortex_state_for(intent.instance_ref) is None
    assert space.get_entity(intent.space_entity_ref) is None


def test_frame_normalizer_requires_vortex_expiry_coordinator() -> None:
    runtime = ReactionRuntime(create_default_reaction_bootstrap().reaction_registry)
    runtime.update_frame(None, 0)
    state_planner = runtime.begin_state_batch(0, "swirl:expiry:missing")
    state_planner.create_stellar_swirl_vortex(_intent("occurrence:1"))
    runtime.commit_prevalidated_state_plan(state_planner.seal())
    coordinator = ElementalStateFrameCoordinator(AuraRuntime(), AuraIcdRuntime(), runtime)

    with pytest.raises(ElementalInteractionError, match="星辉风旋缺少生命周期协调器"):
        coordinator.normalize(None, STELLAR_SWIRL_VORTEX_LIFETIME_FRAMES)


def test_binding_validation_rejects_state_without_space_creation() -> None:
    runtime, _, context = _fixtures((TARGET_1, Vector3(0.0, 0.0, 0.0)))
    state_planner = runtime.begin_state_batch(0, "swirl:binding")
    state_planner.create_stellar_swirl_vortex(_intent("occurrence:1"))
    state_plan = state_planner.seal()
    space_plan = (
        ReactionSpatialPlanningAdapter(context.space_runtime.space)
        .begin_batch(
            operation_id="swirl:binding",
            frame=0,
        )
        .seal()
    )

    with pytest.raises(ReactionStateBindingConflictError):
        validate_stellar_swirl_vortex_space_bindings(state_plan, space_plan)
