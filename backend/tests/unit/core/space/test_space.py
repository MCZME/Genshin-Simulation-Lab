from __future__ import annotations

from math import hypot
from typing import Any, cast

import pytest

from genshin_sim.core.entity_states import CharacterRuntimeState, EntityLifecycle
from genshin_sim.core.simulation import BasicRuntimeWorld, SimulationContext, TeamRuntimeState
from genshin_sim.core.space import (
    CircleArea,
    CollisionBox,
    ImpactAreaSpec,
    OrientedBoxArea,
    RayHit,
    RayQuery,
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


def test_impact_area_spec_keeps_raw_shape_and_radius():
    spec = ImpactAreaSpec(shape="球", radius=2.0, local_offset_xz=Vector3(0, 0, 0))

    assert spec.shape == "球"
    assert spec.radius == 2.0
    assert spec.local_offset_xz == Vector3(0, 0, 0)


def test_impact_area_spec_rejects_invalid_shape_or_radius():
    with pytest.raises(ValueError, match="shape 必须是非空字符串"):
        ImpactAreaSpec(shape="", radius=1.0)
    with pytest.raises(ValueError, match="radius 必须为非负数"):
        ImpactAreaSpec(shape="球", radius=-1.0)


def test_impact_area_spec_keeps_oriented_box_dimensions():
    spec = ImpactAreaSpec(shape="攻击盒", radius=0.0, length=4.3, width=2.5)

    assert spec.shape == "攻击盒"
    assert spec.length == 4.3
    assert spec.width == 2.5


def test_impact_area_spec_rejects_invalid_box_dimensions():
    with pytest.raises(ValueError, match="length 必须为非负数"):
        ImpactAreaSpec(shape="攻击盒", radius=0.0, length=-1.0, width=2.5)
    with pytest.raises(ValueError, match="width 必须为非负数"):
        ImpactAreaSpec(shape="攻击盒", radius=0.0, length=4.3, width=-1.0)
    with pytest.raises(ValueError, match="length 与 width 必须为正数"):
        ImpactAreaSpec(shape="攻击盒", radius=0.0)


def test_impact_area_spec_resolve_projects_sphere_to_circle_at_anchor():
    spec = ImpactAreaSpec(shape="球", radius=2.5)

    area = spec.resolve(Vector3(1, 7, 3), Vector3(0, 0, 1))

    assert area == CircleArea(center=Vector3(1, 7, 3), radius=2.5)


def test_impact_area_spec_resolve_keeps_local_y_offset_without_rotating_it():
    spec = ImpactAreaSpec(shape="圆柱", radius=1.0, local_offset_xz=Vector3(0, 4.5, 3))

    area = spec.resolve(Vector3(0, 1, 0), Vector3(0, 0, 1))

    assert area == CircleArea(center=Vector3(0, 5.5, 3), radius=1.0)


def test_impact_area_spec_resolve_rotates_local_offset_into_attack_frame():
    # 攻击方向 +X：本地 forward(+z) 映射到世界 +x，本地 right(+x) 映射到世界 +z。
    spec = ImpactAreaSpec(shape="球", radius=1.0, local_offset_xz=Vector3(1, 0, 2))

    area = spec.resolve(Vector3(), Vector3(1, 0, 0))

    assert area == CircleArea(center=Vector3(2, 0, 1), radius=1.0)


def test_impact_area_spec_resolve_normalizes_xz_attack_direction_for_box():
    spec = ImpactAreaSpec(shape="攻击盒", radius=0.0, length=4.0, width=2.0)

    area = spec.resolve(Vector3(1, 0, 2), Vector3(0, 5, 30))

    assert area == OrientedBoxArea(
        center=Vector3(1, 0, 2),
        facing=Vector3(0.0, 0.0, 1.0),
        length=4.0,
        width=2.0,
    )


def test_impact_area_spec_resolved_box_contains_inside_length_and_width():
    spec = ImpactAreaSpec(shape="攻击盒", radius=0.0, length=4.0, width=2.0)

    area = spec.resolve(Vector3(), Vector3(0, 0, 1))

    assert isinstance(area, OrientedBoxArea)
    assert area.contains(Vector3(0, 0, 1.9))
    assert area.contains(Vector3(0.9, 0, 0))
    assert not area.contains(Vector3(0, 0, 2.1))
    assert not area.contains(Vector3(1.1, 0, 0))


def test_impact_area_spec_resolve_rejects_zero_direction_and_unknown_shape():
    with pytest.raises(ValueError, match="不能为零向量"):
        ImpactAreaSpec(shape="球", radius=1.0).resolve(Vector3(), Vector3(0, 3, 0))
    with pytest.raises(ValueError, match="未支持的伤害 AOE 形状"):
        ImpactAreaSpec(shape="锥", radius=1.0).resolve(Vector3(), Vector3(0, 0, 1))


def test_oriented_box_area_along_ray_spans_forward_from_origin():
    area = OrientedBoxArea.along_ray(Vector3(0, 3, 0), Vector3(0, 0, 1), length=12, width=1)

    assert area == OrientedBoxArea(
        center=Vector3(0, 3, 6),
        facing=Vector3(0.0, 0.0, 1.0),
        length=12,
        width=1,
    )
    assert area.contains(Vector3(0, 0, 0))
    assert area.contains(Vector3(0, 0, 12))
    assert not area.contains(Vector3(0, 0, 12.1))
    assert not area.contains(Vector3(0, 0, -0.1))


def test_oriented_box_area_along_ray_normalizes_xz_direction_and_rejects_zero():
    area = OrientedBoxArea.along_ray(Vector3(), Vector3(3, 9, 4), length=10, width=2)

    assert area.facing == Vector3(0.6, 0.0, 0.8)

    with pytest.raises(ValueError, match="不能为零向量"):
        OrientedBoxArea.along_ray(Vector3(), Vector3(0, 5, 0), length=10, width=2)


def test_collision_box_defaults_to_cylinder_radius_half_height_one():
    box = CollisionBox()

    assert box.shape == "圆柱"
    assert box.radius == 0.5
    assert box.height == 1.0


def test_collision_box_rejects_negative_radius_or_height():
    with pytest.raises(ValueError, match="radius 必须为非负数"):
        CollisionBox(radius=-0.1)
    with pytest.raises(ValueError, match="height 必须为非负数"):
        CollisionBox(height=-1.0)
    with pytest.raises(ValueError, match="shape 必须是非空字符串"):
        CollisionBox(shape="")


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


def test_space_runtime_apply_displacement_updates_position_only():
    runtime = SpaceRuntime(
        space=Space(
            [
                SpatialEntity(
                    "target:target_1",
                    SpatialEntityKind.TARGET,
                    position=Vector3(1, 2, 3),
                )
            ]
        ),
        team_state=_team_state(),
    )

    updated = runtime.apply_displacement("target:target_1", Vector3(4, 5, 6))

    assert updated is not None
    entity = runtime.get_entity("target:target_1")
    assert entity is not None
    assert entity.position == Vector3(4, 5, 6)
    assert runtime.apply_displacement("missing", Vector3(0, 0, 0)) is None
    with pytest.raises(TypeError, match="Vector3"):
        runtime.apply_displacement("target:target_1", cast(Any, (4, 5, 6)))


def _target(
    entity_id: str,
    position: Vector3,
    *,
    radius: float = 0.5,
    lifecycle: EntityLifecycle | None = None,
    kind: SpatialEntityKind = SpatialEntityKind.TARGET,
) -> SpatialEntity:
    return SpatialEntity(
        entity_id,
        kind,
        position=position,
        lifecycle=lifecycle or EntityLifecycle(),
        collision_box=CollisionBox(radius=radius),
    )


def test_ray_query_normalizes_xz_direction_and_ignores_y():
    query = RayQuery(origin=Vector3(1, 99, 2), direction=Vector3(3, 7, 4), max_distance=12)

    assert query.direction == Vector3(0.6, 0.0, 0.8)
    assert query.origin == Vector3(1, 99, 2)
    assert query.max_distance == 12
    assert RayQuery(origin=Vector3(), direction=Vector3(0, 0, -5)).direction == Vector3(0, 0, -1)


def test_ray_query_rejects_zero_xz_direction_and_invalid_arguments():
    with pytest.raises(ValueError, match="不能为零向量"):
        RayQuery(origin=Vector3(), direction=Vector3(0, 5, 0))
    with pytest.raises(ValueError, match="max_distance 必须为 None 或非负数"):
        RayQuery(origin=Vector3(), direction=Vector3(0, 0, 1), max_distance=-1)
    with pytest.raises(ValueError, match="origin 必须是 Vector3"):
        RayQuery(origin=cast(Any, (0, 0, 0)), direction=Vector3(0, 0, 1))


def test_space_ray_hits_can_be_queried_without_max_distance():
    distant = _target("target:1", Vector3(0, 0, 30))
    space = Space([distant])

    hits = space.ray_hits(RayQuery(origin=Vector3(), direction=Vector3(0, 0, 1)))

    assert hits == (RayHit(entity=distant, forward=30.0, distance=30.0),)


def test_space_ray_hits_uses_each_entity_collision_radius_not_center_point():
    narrow = _target("target:narrow", Vector3(0.4, 0, 4), radius=0.2)
    wide = _target("target:wide", Vector3(0.4, 0, 4), radius=0.5)
    space = Space([narrow, wide])

    hits = space.ray_hits(RayQuery(origin=Vector3(), direction=Vector3(0, 0, 1)))

    assert tuple(hit.entity for hit in hits) == (wide,)
    assert hits[0].forward == 4.0
    assert hits[0].distance == pytest.approx(hypot(0.4, 4.0))


def test_space_ray_hits_includes_exact_radius_boundary_and_excludes_wider_offset():
    on_axis = _target("target:on_axis", Vector3(0, 0, 3), radius=0.0)
    off_axis = _target("target:off_axis", Vector3(0.1, 0, 3), radius=0.0)
    space = Space([on_axis, off_axis])

    hits = space.ray_hits(RayQuery(origin=Vector3(), direction=Vector3(0, 0, 1)))

    assert tuple(hit.entity for hit in hits) == (on_axis,)


def test_space_ray_hits_ignores_entities_behind_or_on_origin_plane():
    space = Space(
        [
            _target("target:behind", Vector3(0, 0, -3)),
            _target("target:on_origin", Vector3()),
            _target("target:ahead", Vector3(0, 0, 2)),
        ]
    )

    hits = space.ray_hits(RayQuery(origin=Vector3(), direction=Vector3(0, 0, 1)))

    assert tuple(hit.entity.entity_id for hit in hits) == ("target:ahead",)


def test_space_ray_hits_measures_lateral_offset_orthogonal_to_diagonal_ray():
    on_axis = _target("target:on_axis", Vector3(5, 0, 5), radius=0.0)
    off_axis = _target("target:off_axis", Vector3(5, 0, 6), radius=0.5)
    space = Space([on_axis, off_axis])

    hits = space.ray_hits(RayQuery(origin=Vector3(), direction=Vector3(1, 0, 1)))

    assert tuple(hit.entity for hit in hits) == (on_axis,)


def test_space_ray_hits_sorts_by_forward_and_keeps_registration_order_on_ties():
    far = _target("target:far", Vector3(0, 0, 5))
    tie_first = _target("target:tie_first", Vector3(0, 0, 3))
    tie_second = _target("target:tie_second", Vector3(-0.2, 0, 3))
    near = _target("target:near", Vector3(0, 0, 1))
    space = Space([far, tie_first, tie_second, near])
    query = RayQuery(origin=Vector3(), direction=Vector3(0, 0, 1))

    assert tuple(hit.entity for hit in space.ray_hits(query)) == (
        near,
        tie_first,
        tie_second,
        far,
    )

    first = space.first_ray_hit(query)

    assert first is not None
    assert first.entity is near


def test_space_first_ray_hit_returns_none_when_nothing_is_hit():
    space = Space([_target("target:behind", Vector3(0, 0, -1))])

    assert space.first_ray_hit(RayQuery(origin=Vector3(), direction=Vector3(0, 0, 1))) is None


def test_space_ray_hits_applies_inclusive_max_distance():
    inside = _target("target:inside", Vector3(0, 0, 4))
    outside = _target("target:outside", Vector3(0, 0, 4.5))
    space = Space([inside, outside])

    limited = RayQuery(origin=Vector3(), direction=Vector3(0, 0, 1), max_distance=4)

    assert tuple(hit.entity for hit in space.ray_hits(limited)) == (inside,)
    assert tuple(
        hit.entity for hit in space.ray_hits(RayQuery(origin=Vector3(), direction=Vector3(0, 0, 1)))
    ) == (inside, outside)


def test_space_ray_hits_filters_by_kind_lifecycle_and_exclusions():
    ctx = SimulationContext()
    expired = _target(
        "target:expired",
        Vector3(0, 0, 1),
        lifecycle=EntityLifecycle(created_frame=1, expires_at_frame=3),
    )
    created = _target(
        "created_object:foo:1",
        Vector3(0, 0, 2),
        kind=SpatialEntityKind.CREATED_OBJECT,
    )
    excluded = _target("target:excluded", Vector3(0, 0, 3))
    kept = _target("target:kept", Vector3(0, 0, 4))
    space = Space([expired, created, excluded, kept])
    space.update_frame(ctx, frame=3)
    query = RayQuery(origin=Vector3(), direction=Vector3(0, 0, 1))

    assert tuple(hit.entity for hit in space.ray_hits(query, kinds={SpatialEntityKind.TARGET})) == (
        excluded,
        kept,
    )
    assert tuple(
        hit.entity
        for hit in space.ray_hits(
            query,
            kinds={SpatialEntityKind.TARGET},
            exclude_entity_ids=("target:excluded",),
        )
    ) == (kept,)
    assert tuple(hit.entity for hit in space.ray_hits(query)) == (created, excluded, kept)


def test_space_ray_hits_rejects_non_ray_query():
    space = Space([_target("target:1", Vector3(0, 0, 1))])

    with pytest.raises(TypeError, match="必须是 RayQuery"):
        space.ray_hits(cast(Any, CircleArea(center=Vector3(), radius=1)))


def test_space_runtime_delegates_ray_queries():
    runtime = SpaceRuntime(
        space=Space(
            [
                _target("target:far", Vector3(0, 0, 6)),
                _target("target:near", Vector3(0, 0, 2)),
            ]
        ),
        team_state=_team_state(),
    )
    query = RayQuery(origin=Vector3(), direction=Vector3(0, 0, 1), max_distance=5)

    hits = runtime.ray_hits(query, kinds={SpatialEntityKind.TARGET})

    assert tuple(hit.entity.entity_id for hit in hits) == ("target:near",)

    first = runtime.first_ray_hit(query)

    assert first is not None
    assert first.entity.entity_id == "target:near"
    assert runtime.first_ray_hit(RayQuery(origin=Vector3(), direction=Vector3(0, 0, -1))) is None
