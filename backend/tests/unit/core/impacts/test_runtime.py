from __future__ import annotations

from typing import cast

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
    SearchAreaSpec,
    TargetingSpec,
    TimedImpactAction,
)
from genshin_sim.core.elements import Element
from genshin_sim.core.entity_states import (
    CharacterRuntimeState,
    TargetRuntimeCollection,
    TargetRuntimeState,
)
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import (
    ActionImpactContext,
    DamageImpactSpec,
    ImpactDispatcher,
    ImpactKind,
    ImpactRequest,
    ImpactRequestDispatcher,
    ImpactRuntime,
    StrikeType,
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
    ACTIVE_CHARACTER_ENTITY_ID,
    CreatedObjectRuntime,
    CreatedObjectRuntimeState,
    ImpactAreaSpec,
    Space,
    SpatialEntity,
    SpatialEntityKind,
    Vector3,
)
from genshin_sim.core.space.runtime import SpaceRuntime
from genshin_sim.core.systems.damage import DamageRequestHandler


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


class AreaDamageImpactFactory:
    def __init__(self, aoe_radius: float) -> None:
        self._aoe_radius = aoe_radius

    def create_requests(self, context: ActionImpactContext) -> tuple[ImpactRequest, ...]:
        return (
            ImpactRequest(
                frame=context.frame,
                kind=ImpactKind.DAMAGE,
                impact_key="furina.skill.hit",
                owner_slot=context.owner.slot,
                action_key=context.action_key,
                source_impact_point_id=context.impact_point_id,
                target_refs=tuple(target.target_id for target in context.target_refs),
                damage_spec=DamageImpactSpec(
                    impact_ref=f"{context.impact_point_id}:damage",
                    main_attack_tag="普通攻击1",
                    element=Element.HYDRO,
                    area=ImpactAreaSpec(shape="球", radius=self._aoe_radius),
                ),
            ),
        )


class AnchorCylinderDamageImpactFactory:
    def create_requests(self, context: ActionImpactContext) -> tuple[ImpactRequest, ...]:
        return (
            ImpactRequest(
                frame=context.frame,
                kind=ImpactKind.DAMAGE,
                impact_key="furina.skill.landing",
                owner_slot=context.owner.slot,
                action_key=context.action_key,
                source_impact_point_id=context.impact_point_id,
                anchor_entity_id=ACTIVE_CHARACTER_ENTITY_ID,
                damage_spec=DamageImpactSpec(
                    impact_ref=f"{context.impact_point_id}:damage",
                    main_attack_tag="下落攻击",
                    element=Element.HYDRO,
                    area=ImpactAreaSpec(
                        shape="圆柱",
                        radius=2.0,
                        local_offset_xz=Vector3(0.0, -0.5, 0.0),
                    ),
                ),
            ),
        )


class _RecordingElementalSettlement:
    def __init__(self) -> None:
        self.damage_requests: list[ImpactRequest] = []

    def settle_damage_impact(self, context, request: ImpactRequest) -> None:
        del context
        self.damage_requests.append(request)

    def settle_aura_impact(self, context, request: ImpactRequest) -> None:
        raise AssertionError("本测试不应处理无伤害元素施加")


class _UnusedDamageHandler:
    @staticmethod
    def has_damage_contract(request: ImpactRequest) -> bool:
        return request.damage_spec is not None


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


def _area_runtime(
    *,
    aoe_radius: float,
) -> tuple[SimulationContext, ActionManager, ImpactRuntime]:
    ctx = SimulationContext()
    ctx.space_runtime = SpaceRuntime(
        space=Space(
            (
                SpatialEntity(
                    "target:target_1",
                    SpatialEntityKind.TARGET,
                    position=Vector3(0, 0, 0),
                ),
                SpatialEntity(
                    "target:target_2",
                    SpatialEntityKind.TARGET,
                    position=Vector3(1.5, 0, 0),
                ),
            )
        ),
        team_state=TeamRuntimeState(
            [CharacterRuntimeState(slot=1, character_key="character:1", level=90)]
        ),
        targets=TargetRuntimeCollection(
            (
                TargetRuntimeState(target_id="target_1"),
                TargetRuntimeState(target_id="target_2"),
            )
        ),
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
                    duration_frames=2,
                    impact_keys=("furina.skill.hit",),
                    impact_frame_offsets={"furina.skill.hit": 1},
                    targeting=TargetingSpec(
                        search_area=SearchAreaSpec(
                            shape="圆柱",
                            radius=15.0,
                            height=10.0,
                        ),
                        selection_policy_key="分数",
                    ),
                ),
            )
        ),
    )
    impact_runtime = ImpactRuntime(
        action_manager,
        ImpactDispatcher({"furina.skill.hit": AreaDamageImpactFactory(aoe_radius)}),
    )
    return ctx, action_manager, impact_runtime


def _anchor_runtime() -> tuple[SimulationContext, ActionManager, ImpactRuntime]:
    ctx = SimulationContext()
    ctx.space_runtime = SpaceRuntime(
        space=Space(
            (
                SpatialEntity(
                    ACTIVE_CHARACTER_ENTITY_ID,
                    SpatialEntityKind.ACTIVE_CHARACTER,
                    position=Vector3(0, 0, 0),
                    active_slot=1,
                ),
                SpatialEntity(
                    "target:target_1",
                    SpatialEntityKind.TARGET,
                    position=Vector3(1, 0, 0),
                ),
                SpatialEntity(
                    "target:target_2",
                    SpatialEntityKind.TARGET,
                    position=Vector3(3, 0, 0),
                ),
            )
        ),
        team_state=TeamRuntimeState(
            [CharacterRuntimeState(slot=1, character_key="character:1", level=90)]
        ),
        targets=TargetRuntimeCollection(
            (
                TargetRuntimeState(target_id="target_1"),
                TargetRuntimeState(target_id="target_2"),
            )
        ),
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
                    duration_frames=2,
                    impact_keys=("furina.skill.landing",),
                    impact_frame_offsets={"furina.skill.landing": 1},
                ),
            )
        ),
    )
    impact_runtime = ImpactRuntime(
        action_manager,
        ImpactDispatcher({"furina.skill.landing": AnchorCylinderDamageImpactFactory()}),
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
    created_events = [
        event
        for event in ctx.events.frame_events
        if event.event_type is EventType.SPACE_ENTITY_CREATED
    ]
    assert len(created_events) == 1
    created_payload = cast(dict[str, object], created_events[0].payload.to_dict())
    created_entity = cast(dict[str, object], created_payload["entity"])
    assert created_entity["entity_id"] == "created:salon_member:1"


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
    assert impact_runtime.ignored_requests[-1].reason == "伤害请求处理器尚未接入"


def test_blunt_zero_element_damage_routes_to_elemental_settlement_for_state_reactions():
    settlement = _RecordingElementalSettlement()
    dispatcher = ImpactRequestDispatcher(
        damage_handler=cast(DamageRequestHandler, _UnusedDamageHandler()),
        elemental_settlement_coordinator=settlement,
    )
    request = ImpactRequest(
        frame=1,
        kind=ImpactKind.DAMAGE,
        impact_key="testing.blunt",
        owner_slot=1,
        request_id="impact:blunt",
        target_refs=("target_1",),
        damage_spec=DamageImpactSpec(
            impact_ref="impact:blunt",
            main_attack_tag="testing.blunt",
            element=Element.PHYSICAL,
            strike_type=StrikeType.BLUNT,
        ),
    )

    dispatcher.dispatch_requests(object(), (request,))

    assert settlement.damage_requests == [request]


def test_impact_runtime_score_selection_picks_nearest_target():
    ctx, action_manager, impact_runtime = _area_runtime(aoe_radius=0.0)

    action_manager.update_frame(ctx, frame=1)
    action_manager.update_frame(ctx, frame=2)
    impact_runtime.update_frame(ctx, frame=3)

    assert len(impact_runtime.dispatch_records) == 1
    requests = impact_runtime.dispatch_records[0].requests
    assert requests[0].target_refs == ("target_1",)


def test_impact_runtime_expands_sphere_area_around_selected_target():
    ctx, action_manager, impact_runtime = _area_runtime(aoe_radius=2.0)

    action_manager.update_frame(ctx, frame=1)
    action_manager.update_frame(ctx, frame=2)
    impact_runtime.update_frame(ctx, frame=3)

    assert len(impact_runtime.dispatch_records) == 1
    requests = impact_runtime.dispatch_records[0].requests
    assert requests[0].target_refs == ("target_1", "target_2")


def test_impact_runtime_sphere_area_keeps_only_targets_inside_radius():
    ctx, action_manager, impact_runtime = _area_runtime(aoe_radius=1.0)

    action_manager.update_frame(ctx, frame=1)
    action_manager.update_frame(ctx, frame=2)
    impact_runtime.update_frame(ctx, frame=3)

    assert len(impact_runtime.dispatch_records) == 1
    requests = impact_runtime.dispatch_records[0].requests
    assert requests[0].target_refs == ("target_1",)


def test_impact_runtime_cylinder_area_expands_around_anchor_entity():
    ctx, action_manager, impact_runtime = _anchor_runtime()

    action_manager.update_frame(ctx, frame=1)
    action_manager.update_frame(ctx, frame=2)
    impact_runtime.update_frame(ctx, frame=3)

    assert len(impact_runtime.dispatch_records) == 1
    requests = impact_runtime.dispatch_records[0].requests
    assert requests[0].target_refs == ("target_1",)
