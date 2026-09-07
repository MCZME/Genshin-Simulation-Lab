from __future__ import annotations

from genshin_sim.core.actions import (
    ActionExecutionContext,
    ActionLifecycleDirective,
    ActionOwnerRef,
    FallPlungeAction,
)
from genshin_sim.core.entity_states import (
    CharacterRuntimeState,
    TargetRuntimeCollection,
    TargetRuntimeState,
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
from genshin_sim.core.systems.movement import MovementRuntime


def test_fall_plunge_action_emits_impacts_on_movement_facts():
    ctx = SimulationContext()
    ctx.space_runtime = SpaceRuntime(
        space=Space(
            (
                SpatialEntity(
                    ACTIVE_CHARACTER_ENTITY_ID,
                    SpatialEntityKind.ACTIVE_CHARACTER,
                    position=Vector3(0.0, 2.0, 0.0),
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
    movement = MovementRuntime()
    ctx.register_system(movement)
    action = FallPlungeAction(
        action_key="character.test.plunge",
        collision_impact_key="character.test.plunge.collision",
        landing_impact_key="character.test.plunge.landing",
    )
    state = action.create_initial_state({"plunge_variant": "high"})
    emitted_keys: list[str] = []
    finished_frame: int | None = None

    for frame in range(1, 80):
        movement.update_frame(ctx, frame)
        result = action.on_update(
            ActionExecutionContext(
                frame=frame,
                instance_id=1,
                owner=ActionOwnerRef.character(1),
                source_session_id=None,
                start_frame=1,
                elapsed_frames=frame - 1,
                action_state=state,
                simulation_context=ctx,
                params={"plunge_variant": "high"},
            )
        )
        if result.next_state is not None:
            state = result.next_state
        emitted_keys.extend(impact.impact_key for impact in result.emitted_impacts)
        if result.lifecycle_directive is ActionLifecycleDirective.FINISH:
            finished_frame = frame
            break

    assert emitted_keys == [
        "character.test.plunge.collision",
        "character.test.plunge.landing",
    ]
    assert finished_frame is not None
    entity = ctx.space_runtime.get_entity(ACTIVE_CHARACTER_ENTITY_ID)
    assert entity is not None
    assert entity.position.y == 0.0
