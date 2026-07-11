from __future__ import annotations

from genshin_sim.core.actions import ActionManager, ActionTimelineSpec
from genshin_sim.core.entity_states import (
    CharacterRuntimeState,
)
from genshin_sim.core.impacts import ImpactDispatcher, ImpactKind, ImpactRequest, ImpactRuntime
from genshin_sim.core.simulation import SimulationContext, TeamRuntimeState
from genshin_sim.core.space import (
    CreatedObjectRuntime,
    CreatedObjectRuntimeState,
    Space,
    SpatialEntityKind,
    Vector3,
)
from genshin_sim.core.space.runtime import SpaceRuntime


class CreateEntityImpactFactory:
    def create_impact_requests(self, request: ImpactRequest) -> tuple[ImpactRequest, ...]:
        return (
            ImpactRequest(
                frame=request.frame,
                kind=ImpactKind.CREATE_ENTITY,
                impact_key="furina.skill.create_salon_member",
                owner_slot=request.owner_slot,
                action_key=request.action_key,
                params={
                    "object_key": "furina.salon_member",
                    "duration_frames": 4,
                    "position": {"x": 1, "y": 0, "z": 2},
                    "entity_id": "created:salon_member:1",
                    "tags": ("salon_member",),
                    "object_params": {"member": "chevalmarin"},
                },
            ),
        )


class DamageTickBehavior:
    def create_tick_requests(
        self,
        state: CreatedObjectRuntimeState,
        frame: int,
    ) -> tuple[ImpactRequest, ...]:
        return (
            ImpactRequest(
                frame=frame,
                kind=ImpactKind.DAMAGE,
                impact_key=f"{state.object_key}.tick",
                owner_slot=1,
            ),
        )


def _attach_space_runtime(
    ctx: SimulationContext,
    action_manager: ActionManager,
    created_object_runtime: CreatedObjectRuntime | None = None,
) -> SpaceRuntime:
    runtime = SpaceRuntime(
        space=Space(),
        team_state=TeamRuntimeState(
            [CharacterRuntimeState(slot=1, character_key="character:1", level=90)]
        ),
        created_object_runtime=created_object_runtime,
        action_manager=action_manager,
    )
    ctx.space_runtime = runtime
    return runtime


def test_impact_runtime_dispatches_action_impact_and_creates_space_entity():
    ctx = SimulationContext()
    action_manager = ActionManager()
    space_runtime = _attach_space_runtime(ctx, action_manager)
    impact_runtime = ImpactRuntime(
        action_manager,
        ImpactDispatcher({"furina.skill": CreateEntityImpactFactory()}),
    )

    action_manager.schedule_timeline(
        ctx,
        ActionTimelineSpec(
            action_key="furina.skill",
            owner_slot=1,
            start_frame=1,
            impact_keys=("furina.skill",),
        ),
    )
    impact_runtime.update_frame(ctx, frame=1)

    assert len(impact_runtime.dispatch_records) == 1
    assert impact_runtime.created_object_records[0].entity_id == "created:salon_member:1"
    assert len(space_runtime.created_object_runtime.objects) == 1
    created = space_runtime.created_object_runtime.objects[0]
    assert created.object_key == "furina.salon_member"
    assert created.entity.owner_key == "slot:1"
    assert created.entity.source_key == "furina.skill"
    assert created.entity.position == Vector3(1, 0, 2)
    assert created.params == {"member": "chevalmarin"}
    assert space_runtime.get_entity("created:salon_member:1") is created.entity


def test_impact_runtime_skips_unregistered_default_action_impacts():
    ctx = SimulationContext()
    action_manager = ActionManager()
    space_runtime = _attach_space_runtime(ctx, action_manager)
    impact_runtime = ImpactRuntime(
        action_manager,
        ImpactDispatcher(),
    )

    action_manager.schedule_timeline(
        ctx,
        ActionTimelineSpec(
            action_key="keyboard.e",
            owner_slot=1,
            start_frame=1,
        ),
    )
    impact_runtime.update_frame(ctx, frame=1)

    assert impact_runtime.dispatch_records == ()
    assert impact_runtime.created_object_records == ()
    assert space_runtime.entities == ()


def test_impact_runtime_syncs_expired_created_object_to_space():
    ctx = SimulationContext()
    action_manager = ActionManager()
    space_runtime = _attach_space_runtime(ctx, action_manager)
    impact_runtime = ImpactRuntime(
        action_manager,
        ImpactDispatcher({"furina.skill": CreateEntityImpactFactory()}),
    )

    action_manager.schedule_timeline(
        ctx,
        ActionTimelineSpec(
            action_key="furina.skill",
            owner_slot=1,
            start_frame=1,
            impact_keys=("furina.skill",),
        ),
    )
    impact_runtime.update_frame(ctx, frame=1)
    impact_runtime.update_frame(ctx, frame=5)

    created_entity = space_runtime.get_entity("created:salon_member:1")
    assert created_entity is not None
    assert created_entity.kind is SpatialEntityKind.CREATED_OBJECT
    assert space_runtime.entities_in_radius(Vector3(1, 0, 2), 1) == ()


def test_impact_runtime_handles_created_object_tick_requests():
    ctx = SimulationContext()
    action_manager = ActionManager()
    created_object_runtime = CreatedObjectRuntime({"furina.salon_member": DamageTickBehavior()})
    space_runtime = _attach_space_runtime(ctx, action_manager, created_object_runtime)
    impact_runtime = ImpactRuntime(
        action_manager,
        ImpactDispatcher({"furina.skill": CreateEntityImpactFactory()}),
    )

    action_manager.schedule_timeline(
        ctx,
        ActionTimelineSpec(
            action_key="furina.skill",
            owner_slot=1,
            start_frame=1,
            impact_keys=("furina.skill",),
        ),
    )
    impact_runtime.update_frame(ctx, frame=1)
    created = space_runtime.created_object_runtime.objects[0]
    created.next_tick_frame = 2
    created.tick_interval_frames = None
    impact_runtime.update_frame(ctx, frame=2)

    assert space_runtime.created_object_runtime.pending_impact_requests == ()
    assert impact_runtime.ignored_requests[-1].request.impact_key == "furina.salon_member.tick"
    assert impact_runtime.ignored_requests[-1].reason == "机制系统尚未接入该影响请求类型"
