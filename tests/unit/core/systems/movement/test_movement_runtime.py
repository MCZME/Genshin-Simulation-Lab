from __future__ import annotations

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
from genshin_sim.core.simulation import SimulationContext, TeamRuntimeState
from genshin_sim.core.space import (
    ACTIVE_CHARACTER_ENTITY_ID,
    Space,
    SpatialEntity,
    SpatialEntityKind,
    Vector3,
)
from genshin_sim.core.space.runtime import SpaceRuntime
from genshin_sim.core.systems.movement import (
    MovementFact,
    MovementImpactRequestHandler,
    MovementRuntime,
)


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

    motion = next(
        item for item in movement.motions if item.entity_id == ACTIVE_CHARACTER_ENTITY_ID
    )
    assert motion.velocity_y == -5.0


def test_movement_impact_request_without_contract_is_ignored():
    ctx = _context(height=2.0)
    movement = MovementRuntime()
    movement.update_frame(ctx, frame=1)
    dispatcher = ImpactRequestDispatcher(
        movement_handler=MovementImpactRequestHandler(movement)
    )
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
