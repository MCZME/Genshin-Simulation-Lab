from __future__ import annotations

import pytest

from genshin_sim.core.entity_states import CharacterRuntimeState, EntityLifecycle
from genshin_sim.core.simulation import BasicRuntimeWorld, SimulationContext, TeamRuntimeState
from genshin_sim.core.space import (
    CircleArea,
    Space,
    SpaceEntityMutationPlan,
    SpaceEntityPlanConflictError,
    SpatialEntity,
    SpatialEntityKind,
    Vector3,
)
from genshin_sim.core.space.runtime import SpaceRuntime


def _team_state(size: int = 2, *, active_slot: int = 1) -> TeamRuntimeState:
    return TeamRuntimeState(
        [
            CharacterRuntimeState(slot=slot, character_key=f"character:{slot}", level=90)
            for slot in range(1, size + 1)
        ],
        active_slot=active_slot,
    )


def test_vector3_measures_distance_on_xz_plane():
    origin = Vector3(0, 999, 0)
    target = Vector3(3, -999, 4)

    assert origin.distance_xz_to(target) == 5


def test_circle_area_contains_positions_on_xz_plane_and_ignores_y():
    area = CircleArea(center=Vector3(0, 0, 0), radius=5)

    assert area.contains(Vector3(3, 999, 4))
    assert not area.contains(Vector3(6, 0, 0))


def test_circle_area_rejects_negative_radius():
    with pytest.raises(ValueError, match="radius 必须为非负数"):
        CircleArea(center=Vector3(), radius=-1)


def test_space_queries_entities_in_radius_using_xz_plane():
    near = SpatialEntity("near", SpatialEntityKind.TARGET, position=Vector3(3, 100, 4))
    far = SpatialEntity("far", SpatialEntityKind.TARGET, position=Vector3(6, 0, 0))
    space = Space([near, far])

    assert space.entities_in_radius(Vector3(0, 0, 0), 5) == (near,)
    assert space.get_entity("near") is near
    assert space.get_entity("missing") is None


def test_space_queries_entities_in_area_preserving_insertion_order():
    first = SpatialEntity("first", SpatialEntityKind.TARGET, position=Vector3(1, 0, 0))
    second = SpatialEntity("second", SpatialEntityKind.TARGET, position=Vector3(2, 0, 0))
    space = Space([first, second])

    assert space.entities_in_area(CircleArea(center=Vector3(), radius=10)) == (first, second)


def test_space_filters_entities_by_kind():
    active = SpatialEntity(
        "player:active",
        SpatialEntityKind.ACTIVE_CHARACTER,
        position=Vector3(),
        active_slot=1,
    )
    target = SpatialEntity("target:target_1", SpatialEntityKind.TARGET, position=Vector3(1, 0, 0))
    space = Space([active, target])

    assert space.entities_in_radius(
        Vector3(),
        5,
        kinds={SpatialEntityKind.TARGET},
    ) == (target,)


def test_space_can_query_created_object_entities_by_kind():
    created = SpatialEntity(
        "created_object:foo:1",
        SpatialEntityKind.CREATED_OBJECT,
        position=Vector3(1, 0, 0),
        tags=("created_object",),
    )
    target = SpatialEntity("target:target_1", SpatialEntityKind.TARGET, position=Vector3(1, 0, 0))
    space = Space([created, target])

    assert space.entities_in_radius(
        Vector3(),
        5,
        kinds={SpatialEntityKind.CREATED_OBJECT},
    ) == (created,)


def test_space_can_query_reaction_object_entities_by_kind():
    reaction_object = SpatialEntity(
        "reaction_object:crystallize_shard:1",
        SpatialEntityKind.REACTION_OBJECT,
        position=Vector3(1, 0, 0),
        tags=("reaction_object", "crystallize_shard"),
    )
    space = Space([reaction_object])

    assert space.entities_in_radius(
        Vector3(),
        5,
        kinds={SpatialEntityKind.REACTION_OBJECT},
    ) == (reaction_object,)


def test_space_queries_ignore_entities_expired_at_current_frame():
    ctx = SimulationContext()
    created = SpatialEntity(
        "created_object:foo:1",
        SpatialEntityKind.CREATED_OBJECT,
        position=Vector3(1, 0, 0),
        lifecycle=EntityLifecycle(created_frame=1, expires_at_frame=3),
    )
    space = Space([created])

    space.update_frame(ctx, frame=1)
    assert space.entities_in_radius(Vector3(), 5) == (created,)

    space.update_frame(ctx, frame=3)
    assert space.entities_in_radius(Vector3(), 5) == ()


def test_space_rejects_duplicate_entity_ids():
    space = Space([SpatialEntity("target_1", SpatialEntityKind.TARGET, position=Vector3())])

    with pytest.raises(ValueError, match="空间实体 id 重复：target_1"):
        space.add_entity(
            SpatialEntity("target_1", SpatialEntityKind.TARGET, position=Vector3(1, 0, 0))
        )


def test_space_direct_entity_writes_advance_version_only_for_real_entity_changes():
    first = SpatialEntity("target:first", SpatialEntityKind.TARGET, position=Vector3())
    space = Space([first])

    assert space.entity_version == 1
    assert space.update_entity(first) is first
    assert space.entity_version == 1

    updated = SpatialEntity("target:first", SpatialEntityKind.TARGET, position=Vector3(1, 0, 0))
    assert space.update_entity(updated) is updated
    assert space.entity_version == 2
    assert space.remove_entity("target:first") is updated
    assert space.entity_version == 3

    space.update_frame(SimulationContext(), frame=9)
    assert space.entity_version == 3


def test_space_entity_plan_commits_create_and_remove_once_with_stable_snapshot():
    removed = SpatialEntity("target:z", SpatialEntityKind.TARGET, position=Vector3())
    space = Space([removed])
    creation = SpatialEntity(
        "reaction_object:a",
        SpatialEntityKind.REACTION_OBJECT,
        position=Vector3(1, 0, 0),
    )
    planner = space.begin_entity_mutation(operation_id="space-op:replace", frame=0)
    assert planner.remove(removed.entity_id) is removed
    assert planner.create(creation) is creation
    plan = planner.seal()

    receipt = space.commit_prevalidated_entity_plan(plan)

    assert receipt.plan is plan
    assert receipt.entity_version == 2
    assert space.entities == (creation,)
    assert space.snapshot(0).entities == (creation,)


def test_space_entity_plan_retries_before_version_validation_and_rejects_changed_operation():
    space = Space()
    creation = SpatialEntity("reaction_object:1", SpatialEntityKind.REACTION_OBJECT, Vector3())
    planner = space.begin_entity_mutation(operation_id="space-op:create", frame=0)
    planner.create(creation)
    plan = planner.seal()
    receipt = space.commit_prevalidated_entity_plan(plan)

    space.add_entity(SpatialEntity("target:later", SpatialEntityKind.TARGET, Vector3()))

    assert space.commit_prevalidated_entity_plan(plan) is receipt
    with pytest.raises(SpaceEntityPlanConflictError, match="operation_id"):
        space.commit_prevalidated_entity_plan(
            SpaceEntityMutationPlan(
                operation_id="space-op:create",
                frame=0,
                expected_entity_version=space.entity_version,
            )
        )


def test_space_entity_plan_rejects_stale_version_and_mismatched_removal_preimage():
    target = SpatialEntity("target:one", SpatialEntityKind.TARGET, Vector3())
    space = Space([target])
    planner = space.begin_entity_mutation(operation_id="space-op:stale", frame=0)
    planner.remove(target.entity_id)
    stale_plan = planner.seal()
    space.add_entity(SpatialEntity("target:other", SpatialEntityKind.TARGET, Vector3()))

    with pytest.raises(SpaceEntityPlanConflictError, match="已经过期"):
        space.commit_prevalidated_entity_plan(stale_plan)

    wrong_preimage = SpatialEntity("target:one", SpatialEntityKind.TARGET, Vector3(2, 0, 0))
    with pytest.raises(SpaceEntityPlanConflictError, match="删除前值"):
        space.commit_prevalidated_entity_plan(
            SpaceEntityMutationPlan(
                operation_id="space-op:preimage",
                frame=0,
                expected_entity_version=space.entity_version,
                removals=(wrong_preimage,),
            )
        )


def test_empty_space_entity_plan_is_idempotent_without_version_change():
    space = Space()
    plan = SpaceEntityMutationPlan("space-op:empty", frame=0, expected_entity_version=0)

    receipt = space.commit_prevalidated_entity_plan(plan)

    assert receipt.entity_version == 0
    assert space.entity_version == 0
    assert space.commit_prevalidated_entity_plan(plan) is receipt


def test_space_runtime_can_be_attached_to_simulation_context_and_runtime_world():
    ctx = SimulationContext()
    space = Space([SpatialEntity("target_1", SpatialEntityKind.TARGET, position=Vector3())])
    runtime = SpaceRuntime(space=space, team_state=_team_state())
    ctx.space_runtime = runtime
    runtime_world = BasicRuntimeWorld([runtime])

    runtime_world.update_frame(ctx, frame=1)

    assert ctx.space_runtime is runtime
    assert runtime.space is space
    assert runtime_world.is_idle()


def test_space_runtime_updates_active_character_slot_through_controlled_interface():
    runtime = SpaceRuntime(
        space=Space(
            [
                SpatialEntity(
                    "player:active",
                    SpatialEntityKind.ACTIVE_CHARACTER,
                    position=Vector3(),
                    active_slot=1,
                )
            ]
        ),
        team_state=_team_state(size=2),
    )

    runtime.team_state.switch_to(2, frame=1)
    runtime.update_active_character_slot(2)

    player = runtime.get_entity("player:active")
    assert player is not None
    assert player.active_slot == 2
