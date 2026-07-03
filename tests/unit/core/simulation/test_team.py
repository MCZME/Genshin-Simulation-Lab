from __future__ import annotations

import pytest

from genshin_sim.core.actions import ActionManager, ActionRejectReason
from genshin_sim.core.events import EventType, GameEvent
from genshin_sim.core.simulation import (
    BasicRuntimeWorld,
    BasicTeamController,
    InputFrame,
    InputState,
    KeyEvent,
    KeyEventDispatch,
    KeyPhase,
    SimulationContext,
    SimulationStopReason,
    Simulator,
    TeamRuntimeState,
    TeamSwitchStatus,
    TraceInputSystem,
)


def test_team_runtime_state_switches_with_one_based_slots():
    team_state = TeamRuntimeState(team_size=4, active_slot=1)

    switched = team_state.switch_to(3, frame=10)

    assert switched.accepted
    assert switched.status is TeamSwitchStatus.SWITCHED
    assert switched.previous_slot == 1
    assert switched.active_slot == 3
    assert team_state.active_slot == 3

    same_slot = team_state.switch_to(3, frame=11)

    assert not same_slot.accepted
    assert same_slot.status is TeamSwitchStatus.SAME_SLOT
    assert team_state.active_slot == 3

    invalid_slot = team_state.switch_to(5, frame=12)

    assert not invalid_slot.accepted
    assert invalid_slot.status is TeamSwitchStatus.INVALID_SLOT
    assert team_state.active_slot == 3


@pytest.mark.parametrize(
    ("team_size", "active_slot", "message"),
    [
        (0, 1, "team_size must be between 1 and 4"),
        (5, 1, "team_size must be between 1 and 4"),
        (2, 3, "active_slot must be within team size"),
    ],
)
def test_team_runtime_state_validates_slots(
    team_size: int,
    active_slot: int,
    message: str,
):
    with pytest.raises(ValueError, match=message):
        TeamRuntimeState(team_size=team_size, active_slot=active_slot)


def test_basic_team_controller_switches_on_number_press_and_publishes_event():
    ctx = SimulationContext()
    events: list[GameEvent] = []
    ctx.events.subscribe(EventType.AFTER_CHARACTER_SWITCH, events.append)
    controller = BasicTeamController()

    controller.handle_key_event(
        ctx,
        KeyEventDispatch(
            frame=7,
            event=KeyEvent("keyboard.2", KeyPhase.PRESS),
        ),
        InputState(),
    )

    assert controller.team_state.active_slot == 2
    assert controller.switch_results[0].status is TeamSwitchStatus.SWITCHED
    assert len(events) == 1
    assert events[0].frame == 7
    assert events[0].data == {
        "previous_slot": 1,
        "active_slot": 2,
    }


def test_basic_team_controller_ignores_number_release():
    controller = BasicTeamController(TeamRuntimeState(active_slot=1))

    controller.handle_key_event(
        SimulationContext(),
        KeyEventDispatch(
            frame=8,
            event=KeyEvent("keyboard.2", KeyPhase.RELEASE),
            held_frames=1,
        ),
        InputState(),
    )

    assert controller.team_state.active_slot == 1
    assert controller.switch_results == ()
    assert controller.action_inputs == ()


def test_basic_team_controller_records_action_button_inputs_without_interpreting_action():
    controller = BasicTeamController(TeamRuntimeState(active_slot=2))

    controller.handle_key_event(
        SimulationContext(),
        KeyEventDispatch(
            frame=10,
            event=KeyEvent("keyboard.e", KeyPhase.PRESS),
        ),
        InputState(),
    )
    controller.handle_key_event(
        SimulationContext(),
        KeyEventDispatch(
            frame=13,
            event=KeyEvent("keyboard.e", KeyPhase.RELEASE),
            held_frames=3,
        ),
        InputState(),
    )

    action_inputs = [
        (item.key, item.phase, item.active_slot, item.held_frames)
        for item in controller.action_inputs
    ]

    assert action_inputs == [
        ("keyboard.e", KeyPhase.PRESS, 2, None),
        ("keyboard.e", KeyPhase.RELEASE, 2, 3),
    ]
    assert controller.switch_results == ()


def test_basic_team_controller_rejects_action_button_during_switch_recovery():
    ctx = SimulationContext()
    action_events: list[GameEvent] = []
    input_events: list[GameEvent] = []
    ctx.events.subscribe(EventType.ACTION_DECISION, action_events.append)
    ctx.events.subscribe(EventType.INPUT_KEY_EVENT, input_events.append)
    action_manager = ActionManager()
    controller = BasicTeamController(action_manager=action_manager)
    input_system = TraceInputSystem(
        [
            InputFrame(
                1,
                (
                    KeyEvent("keyboard.2", KeyPhase.PRESS),
                    KeyEvent("keyboard.e", KeyPhase.PRESS),
                ),
            ),
            InputFrame(
                2,
                (
                    KeyEvent("keyboard.2", KeyPhase.RELEASE),
                    KeyEvent("keyboard.e", KeyPhase.RELEASE),
                ),
            ),
        ],
        controller,
    )

    result = Simulator(ctx, input_system=input_system, max_frames=10).run()

    decision = controller.action_inputs[0].decision
    assert result.stop_reason is SimulationStopReason.COMPLETED
    assert decision is not None
    assert not decision.accepted
    assert decision.reject_reason is ActionRejectReason.BUSY
    assert decision.lock is not None
    assert decision.lock.source == "character_switch"
    assert controller.action_inputs[1].decision is None
    assert [event.data["key"] for event in input_events] == [
        "keyboard.2",
        "keyboard.e",
        "keyboard.2",
        "keyboard.e",
    ]
    assert [event.data for event in action_events] == [
        {
            "key": "keyboard.e",
            "active_slot": 2,
            "accepted": False,
            "reject_reason": "busy",
            "occupied_until_frame": 2,
            "lock_source": "character_switch",
            "target_ids": (),
        }
    ]


def test_basic_team_controller_accepts_action_button_after_switch_recovery():
    ctx = SimulationContext()
    action_events: list[GameEvent] = []
    ctx.events.subscribe(EventType.ACTION_DECISION, action_events.append)
    action_manager = ActionManager()
    controller = BasicTeamController(action_manager=action_manager)
    input_system = TraceInputSystem(
        [
            InputFrame(1, (KeyEvent("keyboard.2", KeyPhase.PRESS),)),
            InputFrame(
                2,
                (
                    KeyEvent("keyboard.2", KeyPhase.RELEASE),
                    KeyEvent("keyboard.e", KeyPhase.PRESS),
                ),
            ),
            InputFrame(3, (KeyEvent("keyboard.e", KeyPhase.RELEASE),)),
        ],
        controller,
    )

    result = Simulator(ctx, input_system=input_system, max_frames=10).run()

    decision = controller.action_inputs[0].decision
    assert result.stop_reason is SimulationStopReason.COMPLETED
    assert decision is not None
    assert decision.accepted
    assert decision.reject_reason is None
    assert decision.lock is not None
    assert decision.lock.source == "keyboard.e"
    assert [event.data["accepted"] for event in action_events] == [True]


def test_action_manager_keeps_simulator_running_until_action_lock_ends():
    ctx = SimulationContext()
    action_manager = ActionManager()
    controller = BasicTeamController(
        action_manager=action_manager,
        action_duration_frames=3,
    )
    input_system = TraceInputSystem(
        [
            InputFrame(1, (KeyEvent("keyboard.e", KeyPhase.PRESS),)),
            InputFrame(2, (KeyEvent("keyboard.e", KeyPhase.RELEASE),)),
        ],
        controller,
    )
    runtime_world = BasicRuntimeWorld([action_manager])

    result = Simulator(
        ctx,
        input_system=input_system,
        runtime_world=runtime_world,
        max_frames=10,
    ).run()

    assert result.stop_reason is SimulationStopReason.COMPLETED
    assert result.end_frame == 4
    assert action_manager.is_idle()


def test_switch_recovery_keeps_simulator_running_until_lock_ends():
    ctx = SimulationContext()
    action_manager = ActionManager()
    controller = BasicTeamController(
        action_manager=action_manager,
        switch_recovery_frames=3,
    )
    input_system = TraceInputSystem(
        [
            InputFrame(1, (KeyEvent("keyboard.2", KeyPhase.PRESS),)),
            InputFrame(2, (KeyEvent("keyboard.2", KeyPhase.RELEASE),)),
        ],
        controller,
    )
    runtime_world = BasicRuntimeWorld([action_manager])

    result = Simulator(
        ctx,
        input_system=input_system,
        runtime_world=runtime_world,
        max_frames=10,
    ).run()

    assert result.stop_reason is SimulationStopReason.COMPLETED
    assert result.end_frame == 4
    assert action_manager.is_idle()


def test_basic_team_controller_rejects_switch_to_missing_slot():
    ctx = SimulationContext()
    events: list[GameEvent] = []
    ctx.events.subscribe(EventType.AFTER_CHARACTER_SWITCH, events.append)
    controller = BasicTeamController(TeamRuntimeState(team_size=2))

    controller.handle_key_event(
        ctx,
        KeyEventDispatch(
            frame=9,
            event=KeyEvent("keyboard.3", KeyPhase.PRESS),
        ),
        InputState(),
    )

    result = controller.switch_results[0]
    assert not result.accepted
    assert result.status is TeamSwitchStatus.INVALID_SLOT
    assert controller.team_state.active_slot == 1
    assert events == []


def test_trace_input_system_can_drive_basic_team_controller():
    ctx = SimulationContext()
    controller = BasicTeamController()
    input_system = TraceInputSystem(
        [
            InputFrame(1, (KeyEvent("keyboard.2", KeyPhase.PRESS),)),
            InputFrame(2, (KeyEvent("keyboard.2", KeyPhase.RELEASE),)),
        ],
        controller,
    )

    result = Simulator(ctx, input_system=input_system, max_frames=10).run()

    assert result.stop_reason is SimulationStopReason.COMPLETED
    assert result.end_frame == 2
    assert controller.team_state.active_slot == 2
    assert [switch.status for switch in controller.switch_results] == [
        TeamSwitchStatus.SWITCHED,
    ]
