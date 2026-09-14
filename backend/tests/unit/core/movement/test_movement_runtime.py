from __future__ import annotations

from typing import cast

import pytest

from genshin_sim.core.entity_states import (
    CharacterRuntimeState,
    TargetRuntimeCollection,
    TargetRuntimeState,
)
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import (
    ImpactKind,
    ImpactRequest,
    ImpactRequestDispatcher,
)
from genshin_sim.core.movement import (
    MovementFact,
    MovementImpactRequestHandler,
    MovementRuntime,
    MovementRuntimeError,
)
from genshin_sim.core.simulation import SimulationContext, TeamRuntimeState
from genshin_sim.core.space import (
    ACTIVE_CHARACTER_ENTITY_ID,
    Space,
    SpatialEntity,
    SpatialEntityKind,
    Vector3,
)
from genshin_sim.core.space.runtime import SpaceRuntime


def _context(*, height: float) -> SimulationContext:
    ctx = SimulationContext()
    ctx.space_runtime = SpaceRuntime(
        space=Space(
            (
                SpatialEntity(
                    ACTIVE_CHARACTER_ENTITY_ID,
                    SpatialEntityKind.ACTIVE_CHARACTER,
                    position=Vector3(0.0, height, 0.0),
                    active_slot=1,
                ),
                SpatialEntity(
                    "target:target_1",
                    SpatialEntityKind.TARGET,
                    position=Vector3(0.0, 0.0, 0.0),
                ),
            )
        ),
        team_state=TeamRuntimeState(
            (CharacterRuntimeState(slot=1, character_key="character:1", level=90),)
        ),
        targets=TargetRuntimeCollection((TargetRuntimeState(target_id="target_1"),)),
    )
    return ctx


def test_movement_runtime_falls_from_rest_and_lands():
    ctx = _context(height=2.0)
    movement = MovementRuntime()
    collision_frame: int | None = None
    landing_frame: int | None = None

    for frame in range(1, 60):
        movement.update_frame(ctx, frame)
        facts = movement.facts_for(ACTIVE_CHARACTER_ENTITY_ID, frame)
        if collision_frame is None and MovementFact.COLLIDED in facts:
            collision_frame = frame
        if MovementFact.LANDED in facts:
            landing_frame = frame
            break

    assert collision_frame is not None
    assert landing_frame is not None
    assert collision_frame < landing_frame
    assert movement.motions == ()
    assert len(movement.landed_records) == 1
    assert movement.landed_records[0].entity_id == ACTIVE_CHARACTER_ENTITY_ID
    assert movement.landed_records[0].fall_height == 2.0
    assert ctx.space_runtime is not None
    entity = ctx.space_runtime.get_entity(ACTIVE_CHARACTER_ENTITY_ID)
    assert entity is not None
    assert entity.position.y == 0.0


def test_movement_runtime_publishes_facts_and_events():
    ctx = _context(height=1.5)
    movement = MovementRuntime()
    landed_events = []
    ctx.events.subscribe(EventType.MOVEMENT_LANDED, landed_events.append)

    for frame in range(1, 60):
        movement.update_frame(ctx, frame)
        if MovementFact.LANDED in movement.facts_for(ACTIVE_CHARACTER_ENTITY_ID, frame):
            break

    assert landed_events
    assert landed_events[0].event_type is EventType.MOVEMENT_LANDED


def test_movement_runtime_start_jump_enters_upward_motion():
    """起跳只置入垂直运动状态，不登记事实、不发布事件。"""

    ctx = _context(height=0.0)
    movement = MovementRuntime()
    movement.update_frame(ctx, frame=1)
    frame_events = []
    ctx.events.subscribe(EventType.MOVEMENT_LANDED, frame_events.append)

    movement.start_jump(ctx, ACTIVE_CHARACTER_ENTITY_ID, 8.0, frame=1)

    # 起跳置入的是向上初速度：内部约定负值表示向上。
    motion = next(item for item in movement.motions if item.entity_id == ACTIVE_CHARACTER_ENTITY_ID)
    assert motion.velocity_y == -8.0
    assert motion.height == 0.0
    assert movement.facts_for(ACTIVE_CHARACTER_ENTITY_ID, 1) == frozenset()
    assert frame_events == []


def test_movement_runtime_start_jump_rises_then_lands():
    ctx = _context(height=0.0)
    movement = MovementRuntime()
    movement.update_frame(ctx, frame=1)
    movement.start_jump(ctx, ACTIVE_CHARACTER_ENTITY_ID, 10.0, frame=1)
    peak_height = 0.0
    landing_frame: int | None = None

    for frame in range(2, 400):
        movement.update_frame(ctx, frame)
        assert ctx.space_runtime is not None
        entity = ctx.space_runtime.get_entity(ACTIVE_CHARACTER_ENTITY_ID)
        assert entity is not None
        peak_height = max(peak_height, entity.position.y)
        if MovementFact.LANDED in movement.facts_for(ACTIVE_CHARACTER_ENTITY_ID, frame):
            landing_frame = frame
            break

    assert peak_height > 0.0
    assert landing_frame is not None
    assert len(movement.landed_records) == 1
    assert movement.landed_records[0].fall_height == 0.0


def test_movement_runtime_start_jump_rejects_invalid_arguments():
    ctx = _context(height=0.0)
    movement = MovementRuntime()
    movement.update_frame(ctx, frame=1)

    with pytest.raises(MovementRuntimeError, match="upward_velocity 必须是正数"):
        movement.start_jump(ctx, ACTIVE_CHARACTER_ENTITY_ID, 0.0, frame=1)
    with pytest.raises(MovementRuntimeError, match="upward_velocity 必须是数字"):
        movement.start_jump(ctx, ACTIVE_CHARACTER_ENTITY_ID, cast(float, "8.0"), frame=1)
    with pytest.raises(MovementRuntimeError, match="起跳实体不存在"):
        movement.start_jump(ctx, "player:missing", 8.0, frame=1)

    movement.start_jump(ctx, ACTIVE_CHARACTER_ENTITY_ID, 8.0, frame=1)
    with pytest.raises(MovementRuntimeError, match="不能再次起跳"):
        movement.start_jump(ctx, ACTIVE_CHARACTER_ENTITY_ID, 8.0, frame=1)


def test_movement_impact_request_starts_jump():
    ctx = _context(height=0.0)
    movement = MovementRuntime()
    movement.update_frame(ctx, frame=1)
    dispatcher = ImpactRequestDispatcher(movement_handler=MovementImpactRequestHandler(movement))
    request = ImpactRequest(
        frame=1,
        kind=ImpactKind.MOVEMENT,
        impact_key="character.test.jump",
        owner_slot=1,
        params={
            "movement": {
                "entity_id": ACTIVE_CHARACTER_ENTITY_ID,
                "jump": {"upward_velocity": 8.0},
            }
        },
    )

    dispatcher.dispatch_requests(ctx, (request,))

    motion = next(item for item in movement.motions if item.entity_id == ACTIVE_CHARACTER_ENTITY_ID)
    assert motion.velocity_y == -8.0


def test_movement_impact_request_rejects_jump_with_vertical_velocity():
    """jump 与 vertical_velocity 按"参数是否出现"互斥：显式传 0 也拒绝。"""

    ctx = _context(height=2.0)
    movement = MovementRuntime()
    movement.update_frame(ctx, frame=1)
    handler = MovementImpactRequestHandler(movement)

    for velocity in (-5.0, 0.0):
        request = ImpactRequest(
            frame=1,
            kind=ImpactKind.MOVEMENT,
            impact_key="character.test.jump",
            owner_slot=1,
            params={
                "movement": {
                    "entity_id": ACTIVE_CHARACTER_ENTITY_ID,
                    "vertical_velocity": velocity,
                    "jump": {"upward_velocity": 8.0},
                }
            },
        )

        with pytest.raises(MovementRuntimeError, match="不能同时使用"):
            handler.handle(ctx, request)

    # 起跳被拒：没有实体被置入向上的初速度。
    assert all(motion.velocity_y != -8.0 for motion in movement.motions)


def test_movement_impact_request_sets_vertical_velocity():
    ctx = _context(height=2.0)
    movement = MovementRuntime()
    movement.update_frame(ctx, frame=1)
    handler = MovementImpactRequestHandler(movement)
    dispatcher = ImpactRequestDispatcher(movement_handler=handler)
    request = ImpactRequest(
        frame=2,
        kind=ImpactKind.MOVEMENT,
        impact_key="character.test.launch",
        owner_slot=1,
        params={
            "movement": {
                "entity_id": ACTIVE_CHARACTER_ENTITY_ID,
                "vertical_velocity": -5.0,
            }
        },
    )

    dispatcher.dispatch_requests(ctx, (request,))

    motion = next(item for item in movement.motions if item.entity_id == ACTIVE_CHARACTER_ENTITY_ID)
    assert motion.velocity_y == -5.0


def test_movement_impact_request_without_contract_is_ignored():
    ctx = _context(height=2.0)
    movement = MovementRuntime()
    movement.update_frame(ctx, frame=1)
    dispatcher = ImpactRequestDispatcher(movement_handler=MovementImpactRequestHandler(movement))
    request = ImpactRequest(
        frame=2,
        kind=ImpactKind.MOVEMENT,
        impact_key="character.test.bad",
        owner_slot=1,
        params={},
    )

    dispatcher.dispatch_requests(ctx, (request,))

    assert len(dispatcher.ignored_requests) == 1
    assert "movement" in dispatcher.ignored_requests[0].reason
