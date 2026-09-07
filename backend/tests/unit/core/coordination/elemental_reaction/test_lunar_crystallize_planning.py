from __future__ import annotations

from typing import cast

from genshin_sim.core.coordination.elemental_reaction.lifecycle import (
    LunarCageExpiryCoordinator,
)
from genshin_sim.core.coordination.elemental_reaction.lunar_crystallize import (
    plan_lunar_crystallize_occurrence,
)
from genshin_sim.core.coordination.elemental_reaction.spatial import (
    ReactionSpatialPlanningAdapter,
)
from genshin_sim.core.elements import ElementalSourceRef, ElementalSubjectRef
from genshin_sim.core.simulation.context import SimulationContext
from genshin_sim.core.space import Space, SpatialEntity, SpatialEntityKind, Vector3
from genshin_sim.core.systems.reaction import (
    LunarCrystallizeStatePlanningIntent,
    ReactionRuntime,
    ReactionStateInstanceRef,
    ReactionStateLifecycleOperation,
    ReactionStateLifecycleWork,
    create_default_reaction_bootstrap,
)
from genshin_sim.core.systems.reaction.mechanics.lunar_crystallize.keys import (
    LUNAR_CAGE_TEAM_SCOPE,
)
from genshin_sim.core.systems.reaction.models import CurrentSubjectSelection

SOURCE = ElementalSourceRef("character:slot_1")
TARGET_1 = ElementalSubjectRef.target("target:target_1")
TARGET_2 = ElementalSubjectRef.target("target:target_2")
TARGET_3 = ElementalSubjectRef.target("target:target_3")
TARGET_4 = ElementalSubjectRef.target("target:target_4")


class _FakeSpaceRuntime:
    def __init__(self, space: Space) -> None:
        self.space = space

    def get_entity(self, entity_id: str) -> SpatialEntity | None:
        return self.space.get_entity(entity_id)


class _FakeContext:
    def __init__(self, space_runtime: _FakeSpaceRuntime) -> None:
        self.space_runtime = space_runtime


def _target_entity(subject_ref: ElementalSubjectRef, position: Vector3) -> SpatialEntity:
    return SpatialEntity(
        entity_id=subject_ref.entity_id,
        kind=SpatialEntityKind.TARGET,
        position=position,
    )


def _intent(
    occurrence_ref: str,
    subject_ref: ElementalSubjectRef,
    *,
    frame: int,
    order: int,
) -> LunarCrystallizeStatePlanningIntent:
    cage_instance_refs = tuple(
        ReactionStateInstanceRef(f"reaction-state:lunar-cage:{occurrence_ref}:{index}")
        for index in range(3)
    )
    cage_space_entity_refs = tuple(
        f"reaction_object:lunar_cage:{occurrence_ref}:{index}" for index in range(3)
    )
    return LunarCrystallizeStatePlanningIntent(
        intent_ref=f"{occurrence_ref}:plan",
        parent_occurrence_ref=occurrence_ref,
        subject_ref=subject_ref,
        team_ref=LUNAR_CAGE_TEAM_SCOPE,
        trigger_source_ref=SOURCE,
        participant_refs=(SOURCE,),
        created_frame=frame,
        order=order,
        cage_instance_refs=cage_instance_refs,
        cage_space_entity_refs=cage_space_entity_refs,
    )


def _fixtures() -> tuple[ReactionRuntime, Space, _FakeContext]:
    runtime = create_default_reaction_bootstrap().create_runtime()
    runtime.update_frame(None, 0)
    space = Space(
        (
            _target_entity(TARGET_1, Vector3(0.0, 0.0, 0.0)),
            _target_entity(TARGET_2, Vector3(20.0, 0.0, 0.0)),
            _target_entity(TARGET_3, Vector3(10.0, 0.0, 0.0)),
            _target_entity(TARGET_4, Vector3(4.0, 0.0, 0.0)),
        )
    )
    context = _FakeContext(_FakeSpaceRuntime(space))
    return runtime, space, context


def _plan(
    runtime: ReactionRuntime,
    space: Space,
    context: _FakeContext,
    intent: LunarCrystallizeStatePlanningIntent,
    *,
    attacked_target_refs: tuple[ElementalSubjectRef, ...],
):
    state_planner = runtime.begin_state_batch(intent.created_frame, intent.intent_ref)
    spatial_planner = ReactionSpatialPlanningAdapter(space).begin_batch(
        operation_id=intent.intent_ref,
        frame=intent.created_frame,
    )
    result = plan_lunar_crystallize_occurrence(
        context=context,
        state_planner=state_planner,
        spatial_planner=spatial_planner,
        intent=intent,
        attacked_target_refs=attacked_target_refs,
    )
    state_plan = state_planner.seal()
    space_plan = spatial_planner.seal()
    runtime.validate_state_plan(state_plan)
    spatial_adapter = ReactionSpatialPlanningAdapter(space)
    spatial_adapter.validate(space_plan)
    runtime.commit_prevalidated_state_plan(state_plan)
    spatial_adapter.commit_prevalidated(space_plan)
    return result


def test_first_three_occurrences_generate_cages_then_fire_harmony() -> None:
    runtime, space, context = _fixtures()

    first = _plan(
        runtime,
        space,
        context,
        _intent("occurrence:1", TARGET_1, frame=0, order=0),
        attacked_target_refs=(TARGET_1,),
    )
    assert first.generated_cages
    assert not first.fired_harmony
    assert len(runtime.active_lunar_cages(team_ref=LUNAR_CAGE_TEAM_SCOPE)) == 3
    accumulator = runtime.lunar_crystallize_accumulator_for(LUNAR_CAGE_TEAM_SCOPE)
    assert accumulator is not None
    assert len(accumulator.pending_records) == 1

    second = _plan(
        runtime,
        space,
        context,
        _intent("occurrence:2", TARGET_1, frame=0, order=1),
        attacked_target_refs=(TARGET_1,),
    )
    assert not second.generated_cages
    assert not second.fired_harmony
    assert len(runtime.active_lunar_cages(team_ref=LUNAR_CAGE_TEAM_SCOPE)) == 3
    accumulator = runtime.lunar_crystallize_accumulator_for(LUNAR_CAGE_TEAM_SCOPE)
    assert accumulator is not None
    assert len(accumulator.pending_records) == 2

    third = _plan(
        runtime,
        space,
        context,
        _intent("occurrence:3", TARGET_1, frame=0, order=2),
        attacked_target_refs=(TARGET_1,),
    )
    assert not third.generated_cages
    assert third.fired_harmony
    assert len(third.harmony_effect_groups) == 1
    group = third.harmony_effect_groups[0]
    assert len(group.effects) == 3
    assert group.parent_occurrence_ref == "occurrence:3"
    assert runtime.lunar_crystallize_accumulator_for(LUNAR_CAGE_TEAM_SCOPE) is None
    cages = runtime.active_lunar_cages(team_ref=LUNAR_CAGE_TEAM_SCOPE)
    assert len(cages) == 3
    assert all(cage.next_attack_frame == 21 for cage in cages)
    assert all(cage.last_harmony_frame == 0 for cage in cages)
    assert all(cage.attack_index == 1 for cage in cages)
    assert all(cage.expires_at_frame == 540 for cage in cages)


def test_cooldown_overflows_to_four_layers_and_delays_harmony() -> None:
    runtime, space, context = _fixtures()

    for order in range(3):
        result = _plan(
            runtime,
            space,
            context,
            _intent(f"occurrence:{order + 1}", TARGET_1, frame=0, order=order),
            attacked_target_refs=(TARGET_1,),
        )
        assert result.fired_harmony is (order == 2)

    for order in range(3, 8):
        result = _plan(
            runtime,
            space,
            context,
            _intent(f"occurrence:{order + 1}", TARGET_1, frame=0, order=order),
            attacked_target_refs=(TARGET_1,),
        )
        assert not result.fired_harmony
    accumulator = runtime.lunar_crystallize_accumulator_for(LUNAR_CAGE_TEAM_SCOPE)
    assert accumulator is not None
    assert len(accumulator.pending_records) == 4
    assert accumulator.pending_records[0].occurrence_ref == "occurrence:5"

    runtime.update_frame(None, 30)
    space.update_frame(cast(SimulationContext, None), 30)
    delayed = _plan(
        runtime,
        space,
        context,
        _intent("occurrence:9", TARGET_1, frame=30, order=8),
        attacked_target_refs=(TARGET_1,),
    )
    assert delayed.fired_harmony
    accumulator = runtime.lunar_crystallize_accumulator_for(LUNAR_CAGE_TEAM_SCOPE)
    assert accumulator is not None
    assert [item.occurrence_ref for item in accumulator.pending_records] == ["occurrence:9"]
    cages = runtime.active_lunar_cages(team_ref=LUNAR_CAGE_TEAM_SCOPE)
    assert all(cage.next_attack_frame == 51 for cage in cages)


def test_generation_at_new_anchor_replaces_old_cage_set() -> None:
    runtime, space, context = _fixtures()
    _plan(
        runtime,
        space,
        context,
        _intent("occurrence:1", TARGET_1, frame=0, order=0),
        attacked_target_refs=(TARGET_1,),
    )
    old_refs = tuple(
        cage.instance_ref for cage in runtime.active_lunar_cages(team_ref=LUNAR_CAGE_TEAM_SCOPE)
    )

    result = _plan(
        runtime,
        space,
        context,
        _intent("occurrence:2", TARGET_2, frame=0, order=1),
        attacked_target_refs=(TARGET_2,),
    )
    assert result.generated_cages
    new_refs = tuple(
        cage.instance_ref for cage in runtime.active_lunar_cages(team_ref=LUNAR_CAGE_TEAM_SCOPE)
    )
    assert len(new_refs) == 3
    assert not (set(old_refs) & set(new_refs))


def test_harmony_can_hit_attacked_target_different_from_trigger() -> None:
    runtime, space, context = _fixtures()
    for order in range(2):
        _plan(
            runtime,
            space,
            context,
            _intent(f"occurrence:{order + 1}", TARGET_1, frame=0, order=order),
            attacked_target_refs=(TARGET_1,),
        )
    third = _plan(
        runtime,
        space,
        context,
        _intent("occurrence:3", TARGET_3, frame=0, order=2),
        attacked_target_refs=(TARGET_3, TARGET_1),
    )
    assert third.fired_harmony
    selection = third.harmony_effect_groups[0].target_selection
    assert isinstance(selection, CurrentSubjectSelection)
    assert selection.subject_ref == TARGET_1


def test_lunar_cage_expiry_removes_state_and_space_entity() -> None:
    runtime, space, context = _fixtures()
    _plan(
        runtime,
        space,
        context,
        _intent("occurrence:1", TARGET_1, frame=0, order=0),
        attacked_target_refs=(TARGET_1,),
    )
    cages = runtime.active_lunar_cages(team_ref=LUNAR_CAGE_TEAM_SCOPE)
    works = tuple(
        ReactionStateLifecycleWork(
            work_ref=f"reaction-state:{cage.instance_ref.value}:frame:540:expire",
            frame=540,
            state_instance_ref=cage.instance_ref,
            state_slot=cage.slot_key.slot,
            scope_key=cage.slot_key.scope_key,
            operation=ReactionStateLifecycleOperation.EXPIRE,
            cause_ref=f"reaction-state:{cage.instance_ref.value}:frame:540:expire",
        )
        for cage in cages
    )
    runtime.update_frame(None, 540)
    space.update_frame(cast(SimulationContext, None), 540)
    coordinator = LunarCageExpiryCoordinator(
        reaction_state_port=runtime,
        spatial_planning_port=ReactionSpatialPlanningAdapter(space),
    )
    expired = coordinator.expire(None, frame=540, works=works)
    assert len(expired) == 3
    assert runtime.active_lunar_cages(team_ref=LUNAR_CAGE_TEAM_SCOPE) == ()
    assert all(space.get_entity(cage.space_entity_ref) is None for cage in cages)
