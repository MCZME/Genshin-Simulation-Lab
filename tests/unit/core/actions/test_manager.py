from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, cast

import pytest

from genshin_sim.core.actions import (
    TEAM_SWITCH_ACTION_KEY,
    TEAM_SWITCH_TARGET_SLOT_PARAM,
    ActionAdmissionPolicy,
    ActionDecisionRejectReason,
    ActionExecutionContext,
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
    TeamActionInterpreter,
    TeamInterpreterSelector,
    TeamSwitchAction,
    TimedImpactAction,
)
from genshin_sim.core.entity_states import CharacterRuntimeState
from genshin_sim.core.events import EventType
from genshin_sim.core.simulation import (
    InputTraceCompiler,
    KeyEvent,
    KeyInputFrame,
    KeyPhase,
    SimulationContext,
    TeamRuntimeState,
)
from genshin_sim.core.space import Space, SpatialEntity, SpatialEntityKind, Vector3
from genshin_sim.core.space.runtime import SpaceRuntime


@dataclass(slots=True)
class ReleaseStartInterpreter:
    action_by_key: dict[str, str]
    views: list[InputSessionView] = field(default_factory=list)

    @property
    def supported_action_keys(self) -> tuple[str, ...]:
        return tuple(self.action_by_key.values())

    def interpret(self, context, session: InputSessionView) -> ActionInterpretationResult:
        del context
        self.views.append(session)
        if session.trigger is not ActionInterpretationTrigger.RELEASE:
            return ActionInterpretationResult.wait()
        return ActionInterpretationResult.start(
            PreparedAction(
                action_key=self.action_by_key[session.key],
                owner=session.owner,
                requested_start_frame=session.current_frame,
                source_session_id=session.session_id,
            )
        )


def _context(*, team_size: int = 2, active_slot: int = 1) -> SimulationContext:
    context = SimulationContext()
    team_state = TeamRuntimeState(
        (
            CharacterRuntimeState(slot=slot, character_key=f"character:{slot}", level=90)
            for slot in range(1, team_size + 1)
        ),
        active_slot=active_slot,
    )
    context.space_runtime = SpaceRuntime(
        space=Space(
            [
                SpatialEntity(
                    "player:active",
                    SpatialEntityKind.ACTIVE_CHARACTER,
                    position=Vector3(),
                    active_slot=active_slot,
                )
            ]
        ),
        team_state=team_state,
    )
    return context


def _manager(
    frames: list[KeyInputFrame],
    interpreter: ReleaseStartInterpreter,
    actions: tuple[TimedImpactAction, ...],
) -> ActionManager:
    registry = ActionInterpreterRegistry()
    registry.register("keyboard.e", ActiveCharacterInterpreterSelector({1: interpreter}))
    registry.register("mouse.left", ActiveCharacterInterpreterSelector({1: interpreter}))
    return ActionManager(
        input_trace=InputTraceCompiler().compile(frames),
        interpreter_registry=registry,
        action_registry=ActionRegistry(actions),
    )


def test_action_manager_starts_action_on_release_and_does_not_expose_future_release():
    interpreter = ReleaseStartInterpreter({"keyboard.e": "character.test.skill"})
    manager = _manager(
        [
            KeyInputFrame(1, (KeyEvent("keyboard.e", KeyPhase.PRESS),)),
            KeyInputFrame(3, (KeyEvent("keyboard.e", KeyPhase.RELEASE),)),
        ],
        interpreter,
        (
            TimedImpactAction(
                action_key="character.test.skill",
                duration_frames=2,
                impact_keys=("character.test.skill.hit",),
                impact_frame_offsets={"character.test.skill.hit": 1},
            ),
        ),
    )
    context = _context()

    manager.update_frame(context, 1)
    assert interpreter.views[-1].trigger is ActionInterpretationTrigger.PRESS
    assert interpreter.views[-1].release_frame is None
    assert manager.instances == ()

    manager.update_frame(context, 2)
    assert interpreter.views[-1].trigger is ActionInterpretationTrigger.HOLD
    assert interpreter.views[-1].release_frame is None

    manager.update_frame(context, 3)
    assert interpreter.views[-1].trigger is ActionInterpretationTrigger.RELEASE
    assert interpreter.views[-1].release_frame == 3
    assert manager.decisions[-1].accepted
    assert manager.instances[0].action_key == "character.test.skill"
    assert manager.instances[0].impact_points[0].scheduled_frame == 4


def test_action_manager_publishes_input_fact_and_boundary_events():
    interpreter = ReleaseStartInterpreter({"keyboard.e": "character.test.skill"})
    manager = _manager(
        [
            KeyInputFrame(1, (KeyEvent("keyboard.e", KeyPhase.PRESS),)),
            KeyInputFrame(3, (KeyEvent("keyboard.e", KeyPhase.RELEASE),)),
        ],
        interpreter,
        (TimedImpactAction(action_key="character.test.skill"),),
    )
    context = _context()

    manager.update_frame(context, 1)

    assert [event.event_type for event in context.events.frame_events] == [
        EventType.INPUT_KEY_RECEIVED,
        EventType.INPUT_SESSION_BOUNDARY_REACHED,
    ]
    assert context.events.frame_events[0].payload.to_dict() == {
        "key": "keyboard.e",
        "phase": "press",
        "order": 0,
        "session_id": 1,
    }
    assert context.events.frame_events[1].payload.to_dict() == {
        "session_id": 1,
        "key": "keyboard.e",
        "phase": "press",
        "order": 0,
        "press_frame": 1,
        "held_frames": 0,
        "physical_state": "held",
        "control_state": "listening",
        "owner_kind": "character",
        "owner_slot": 1,
        "interpreter_id": "character:1",
        "binding_scope": "active_character",
        "will_interpret": True,
        "skip_reason": None,
    }

    context.events.clear_frame_events()
    manager.update_frame(context, 2)
    context.events.clear_frame_events()
    manager.update_frame(context, 3)

    assert [event.event_type for event in context.events.frame_events] == [
        EventType.INPUT_KEY_RECEIVED,
        EventType.INPUT_SESSION_BOUNDARY_REACHED,
    ]
    assert context.events.frame_events[1].payload.to_dict() == {
        "session_id": 1,
        "key": "keyboard.e",
        "phase": "release",
        "order": 0,
        "press_frame": 1,
        "held_frames": 2,
        "physical_state": "released",
        "control_state": "listening",
        "owner_kind": "character",
        "owner_slot": 1,
        "interpreter_id": "character:1",
        "binding_scope": "active_character",
        "will_interpret": True,
        "skip_reason": None,
    }


def test_action_manager_rejects_unregistered_action():
    interpreter = ReleaseStartInterpreter({"keyboard.e": "missing.action"})
    manager = _manager(
        [
            KeyInputFrame(1, (KeyEvent("keyboard.e", KeyPhase.PRESS),)),
            KeyInputFrame(2, (KeyEvent("keyboard.e", KeyPhase.RELEASE),)),
        ],
        interpreter,
        (),
    )

    manager.update_frame(_context(), 1)
    manager.update_frame(_context(), 2)

    assert not manager.decisions[-1].accepted
    assert manager.decisions[-1].reject_reason is ActionDecisionRejectReason.UNSUPPORTED_ACTION


def test_action_manager_rejects_conflicting_named_lock():
    interpreter = ReleaseStartInterpreter(
        {
            "keyboard.e": "character.test.skill",
            "mouse.left": "character.test.attack",
        }
    )
    shared_lock = ActionAdmissionPolicy(required_locks=("character:1.control",))
    manager = _manager(
        [
            KeyInputFrame(1, (KeyEvent("keyboard.e", KeyPhase.PRESS),)),
            KeyInputFrame(2, (KeyEvent("keyboard.e", KeyPhase.RELEASE),)),
            KeyInputFrame(3, (KeyEvent("mouse.left", KeyPhase.PRESS),)),
            KeyInputFrame(4, (KeyEvent("mouse.left", KeyPhase.RELEASE),)),
        ],
        interpreter,
        (
            TimedImpactAction(
                action_key="character.test.skill",
                duration_frames=5,
                admission_policy=shared_lock,
            ),
            TimedImpactAction(
                action_key="character.test.attack",
                duration_frames=1,
                admission_policy=shared_lock,
            ),
        ),
    )
    context = _context()

    for frame in range(1, 5):
        manager.update_frame(context, frame)

    assert [decision.accepted for decision in manager.decisions] == [True, False]
    assert manager.decisions[-1].reject_reason is ActionDecisionRejectReason.LOCK_CONFLICT


def test_team_switch_is_regular_action_instance_and_updates_space_runtime():
    context = _context(team_size=2, active_slot=1)
    input_trace = InputTraceCompiler().compile(
        [
            KeyInputFrame(1, (KeyEvent("keyboard.2", KeyPhase.PRESS),)),
            KeyInputFrame(2, (KeyEvent("keyboard.2", KeyPhase.RELEASE),)),
        ]
    )
    registry = ActionInterpreterRegistry()
    registry.register("keyboard.2", TeamInterpreterSelector(TeamActionInterpreter()))
    manager = ActionManager(
        input_trace=input_trace,
        interpreter_registry=registry,
        action_registry=ActionRegistry((TeamSwitchAction(),)),
    )

    manager.update_frame(context, 1)

    assert manager.instances[0].action_key == TEAM_SWITCH_ACTION_KEY
    assert manager.instances[0].params == {TEAM_SWITCH_TARGET_SLOT_PARAM: 2}
    assert context.space_runtime is not None
    assert context.space_runtime.team_state.active_slot == 2
    player = context.space_runtime.get_entity("player:active")
    assert player is not None
    assert player.active_slot == 2
    assert manager.execution_records[0].payload["type"] == "team_switch"


def test_search_area_spec_rejects_negative_radius_or_height():
    with pytest.raises(ValueError, match="radius 必须为非负数"):
        SearchAreaSpec(shape="圆柱", radius=-1.0, height=10.0)
    with pytest.raises(ValueError, match="height 必须为非负数"):
        SearchAreaSpec(shape="圆柱", radius=15.0, height=-1.0)
    with pytest.raises(ValueError, match="shape 必须是非空字符串"):
        SearchAreaSpec(shape="", radius=15.0, height=10.0)


def test_targeting_spec_validates_search_area_and_selection_policy():
    spec = TargetingSpec(
        search_area=SearchAreaSpec(shape="圆柱", radius=15.0, height=10.0),
        selection_policy_key="分数",
    )

    assert spec.search_area is not None
    assert spec.search_area.radius == 15.0
    assert spec.search_area.height == 10.0
    assert spec.selection_policy_key == "分数"
    with pytest.raises(ValueError, match="search_area 必须是 SearchAreaSpec"):
        TargetingSpec(search_area=cast(Any, "圆柱"))
    with pytest.raises(ValueError, match="selection_policy_key"):
        TargetingSpec(selection_policy_key="")


def _action_context(
    *,
    start_frame: int,
    frame: int,
    state: Mapping[str, object],
    params: Mapping[str, object],
    space=None,
) -> ActionExecutionContext:
    context = SimulationContext()
    if space is not None:
        context.space_runtime = space
    return ActionExecutionContext(
        frame=frame,
        instance_id=1,
        owner=ActionOwnerRef.character(1),
        source_session_id=None,
        start_frame=start_frame,
        elapsed_frames=frame - start_frame,
        action_state=state,
        simulation_context=context,
        params=params,
    )
