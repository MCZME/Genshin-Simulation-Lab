from __future__ import annotations

from genshin_sim.core.actions import (
    ActionInterpretationResult,
    ActionInterpretationTrigger,
    ActionInterpreterRegistry,
    ActionManager,
    ActionOwnerRef,
    ActionRegistry,
    ActiveCharacterInterpreterSelector,
    InputSessionView,
    PreparedAction,
    TimedImpactAction,
)
from genshin_sim.core.entity_states import CharacterRuntimeState
from genshin_sim.core.impacts import (
    ActionImpactContext,
    ImpactDispatcher,
    ImpactKind,
    ImpactRequest,
    ImpactRuntime,
)
from genshin_sim.core.simulation import (
    InputTraceCompiler,
    KeyEvent,
    KeyInputFrame,
    KeyPhase,
    SimulationContext,
    TeamRuntimeState,
)
from genshin_sim.core.space import (
    CreatedObjectRuntime,
    CreatedObjectRuntimeState,
    Space,
    SpatialEntityKind,
    Vector3,
)
from genshin_sim.core.space.runtime import SpaceRuntime


class ReleaseInterpreter:
    supported_action_keys = ("furina.skill",)

    def interpret(self, context, session: InputSessionView) -> ActionInterpretationResult:
        del context
        if session.trigger is not ActionInterpretationTrigger.RELEASE:
            return ActionInterpretationResult.wait()
        return ActionInterpretationResult.start(
            PreparedAction(
                action_key="furina.skill",
                owner=ActionOwnerRef.character(1),
                requested_start_frame=session.current_frame,
                source_session_id=session.session_id,
            )
        )


class CreateEntityImpactFactory:
    def create_requests(self, context: ActionImpactContext) -> tuple[ImpactRequest, ...]:
        return (
            ImpactRequest(
                frame=context.frame,
                kind=ImpactKind.CREATE_ENTITY,
                impact_key="furina.skill.create_salon_member",
                owner_slot=context.owner.slot,
                action_key=context.action_key,
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


def _runtime_pair(
    *,
    created_object_runtime: CreatedObjectRuntime | None = None,
) -> tuple[SimulationContext, ActionManager, ImpactRuntime]:
    ctx = SimulationContext()
    ctx.space_runtime = SpaceRuntime(
        space=Space(),
        team_state=TeamRuntimeState(
            [CharacterRuntimeState(slot=1, character_key="character:1", level=90)]
        ),
        created_object_runtime=created_object_runtime,
    )
    interpreter = ReleaseInterpreter()
    registry = ActionInterpreterRegistry()
    registry.register("keyboard.e", ActiveCharacterInterpreterSelector({1: interpreter}))
    action_manager = ActionManager(
        input_trace=InputTraceCompiler().compile(
            [
                KeyInputFrame(1, (KeyEvent("keyboard.e", KeyPhase.PRESS),)),
                KeyInputFrame(2, (KeyEvent("keyboard.e", KeyPhase.RELEASE),)),
            ]
        ),
        interpreter_registry=registry,
        action_registry=ActionRegistry(
            (
                TimedImpactAction(
                    action_key="furina.skill",
                    impact_keys=("furina.skill",),
                ),
            )
        ),
    )
    impact_runtime = ImpactRuntime(
        action_manager,
        ImpactDispatcher({"furina.skill": CreateEntityImpactFactory()}),
    )
    return ctx, action_manager, impact_runtime


def test_impact_runtime_dispatches_action_impact_and_creates_space_entity():
    ctx, action_manager, impact_runtime = _runtime_pair()

    action_manager.update_frame(ctx, frame=1)
    action_manager.update_frame(ctx, frame=2)
    impact_runtime.update_frame(ctx, frame=2)

    assert len(impact_runtime.dispatch_records) == 1
    assert impact_runtime.created_object_records[0].entity_id == "created:salon_member:1"
    assert ctx.space_runtime is not None
    assert len(ctx.space_runtime.created_object_runtime.objects) == 1
    created = ctx.space_runtime.created_object_runtime.objects[0]
    assert created.object_key == "furina.salon_member"
    assert created.entity.owner_key == "slot:1"
    assert created.entity.source_key == "furina.skill"
    assert created.entity.position == Vector3(1, 0, 2)
    assert created.params == {"member": "chevalmarin"}
    assert ctx.space_runtime.get_entity("created:salon_member:1") is created.entity


def test_impact_runtime_syncs_expired_created_object_to_space():
    ctx, action_manager, impact_runtime = _runtime_pair()

    action_manager.update_frame(ctx, frame=1)
    action_manager.update_frame(ctx, frame=2)
    impact_runtime.update_frame(ctx, frame=2)
    impact_runtime.update_frame(ctx, frame=6)

    assert ctx.space_runtime is not None
    created_entity = ctx.space_runtime.get_entity("created:salon_member:1")
    assert created_entity is not None
    assert created_entity.kind is SpatialEntityKind.CREATED_OBJECT
    assert ctx.space_runtime.entities_in_radius(Vector3(1, 0, 2), 1) == ()


def test_impact_runtime_handles_created_object_tick_requests():
    created_object_runtime = CreatedObjectRuntime({"furina.salon_member": DamageTickBehavior()})
    ctx, action_manager, impact_runtime = _runtime_pair(
        created_object_runtime=created_object_runtime
    )

    action_manager.update_frame(ctx, frame=1)
    action_manager.update_frame(ctx, frame=2)
    impact_runtime.update_frame(ctx, frame=2)
    created = created_object_runtime.objects[0]
    created.next_tick_frame = 3
    created.tick_interval_frames = None
    impact_runtime.update_frame(ctx, frame=3)

    assert created_object_runtime.pending_impact_requests == ()
    assert impact_runtime.ignored_requests[-1].request.impact_key == "furina.salon_member.tick"
    assert impact_runtime.ignored_requests[-1].reason == "机制系统尚未接入该影响请求类型"
