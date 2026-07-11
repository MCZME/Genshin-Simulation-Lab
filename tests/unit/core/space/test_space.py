from __future__ import annotations

import pytest

from genshin_sim.core.actions import (
    TEAM_SWITCH_ACTION_KEY,
    TEAM_SWITCH_TARGET_SLOT_PARAM,
    ActionManager,
    ActionTimelineSpec,
)
from genshin_sim.core.entity_states import CharacterRuntimeState, EntityLifecycle
from genshin_sim.core.simulation import BasicRuntimeWorld, SimulationContext, TeamRuntimeState
from genshin_sim.core.space import (
    CircleArea,
    Space,
    SpatialEntity,
    SpatialEntityKind,
    Vector3,
)
from genshin_sim.core.space.runtime import SpaceRuntime, TeamSwitchActionConsumer


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


def test_space_runtime_can_be_attached_to_simulation_context_and_runtime_world():
    ctx = SimulationContext()
    space = Space([SpatialEntity("target_1", SpatialEntityKind.TARGET, position=Vector3())])
    manager = ActionManager()
    runtime = SpaceRuntime(space=space, team_state=_team_state(), action_manager=manager)
    ctx.space_runtime = runtime
    runtime_world = BasicRuntimeWorld([runtime])

    runtime_world.update_frame(ctx, frame=1)

    assert ctx.space_runtime is runtime
    assert runtime.space is space
    assert runtime_world.is_idle()


def test_space_runtime_consumes_team_switch_action():
    ctx = SimulationContext()
    space = Space(
        [
            SpatialEntity(
                "player:active",
                SpatialEntityKind.ACTIVE_CHARACTER,
                position=Vector3(),
                active_slot=1,
            )
        ]
    )
    team_state = _team_state(size=2)
    manager = ActionManager()
    consumer = TeamSwitchActionConsumer()
    runtime = SpaceRuntime(
        space=space,
        team_state=team_state,
        action_manager=manager,
        consumers={("player:active", TEAM_SWITCH_ACTION_KEY): consumer},
    )
    ctx.space_runtime = runtime

    decision = manager.schedule_timeline(
        ctx,
        ActionTimelineSpec(
            action_key=TEAM_SWITCH_ACTION_KEY,
            source_key="keyboard.2",
            owner_slot=1,
            start_frame=1,
            actor_entity_id="player:active",
            params={TEAM_SWITCH_TARGET_SLOT_PARAM: 2},
        ),
    )
    runtime.update_frame(ctx, frame=1)

    player = runtime.get_entity("player:active")
    assert decision.instance is not None
    assert team_state.active_slot == 2
    assert player is not None
    assert player.active_slot == 2
    assert consumer.results[0].accepted
    assert manager.consumption_records[0].instance_id == decision.instance.instance_id
    assert manager.consumption_records[0].status == "switched"


def test_space_runtime_records_invalid_team_switch_as_consumed():
    ctx = SimulationContext()
    team_state = _team_state(size=1)
    manager = ActionManager()
    runtime = SpaceRuntime(
        space=Space(),
        team_state=team_state,
        action_manager=manager,
        consumers={("player:active", TEAM_SWITCH_ACTION_KEY): TeamSwitchActionConsumer()},
    )
    ctx.space_runtime = runtime

    manager.schedule_timeline(
        ctx,
        ActionTimelineSpec(
            action_key=TEAM_SWITCH_ACTION_KEY,
            source_key="keyboard.2",
            owner_slot=1,
            start_frame=1,
            actor_entity_id="player:active",
            params={TEAM_SWITCH_TARGET_SLOT_PARAM: 2},
        ),
    )
    runtime.update_frame(ctx, frame=1)

    assert team_state.active_slot == 1
    assert manager.consumption_records[0].status == "invalid_slot"
    assert runtime.is_idle()
