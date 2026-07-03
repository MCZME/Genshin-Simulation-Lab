from __future__ import annotations

import pytest

from genshin_sim.core.events import EventType, GameEvent
from genshin_sim.core.simulation import (
    InputFrame,
    InputState,
    InputTraceError,
    KeyEvent,
    KeyEventDispatch,
    KeyPhase,
    SimulationContext,
    TraceInputSystem,
)


class RecordingTeamController:
    def __init__(self) -> None:
        self.received: list[tuple[int, str, KeyPhase, int | None, frozenset[str]]] = []

    def handle_key_event(
        self,
        context: SimulationContext,
        dispatch: KeyEventDispatch,
        state: InputState,
    ) -> None:
        assert context.current_frame == dispatch.frame
        self.received.append(
            (
                dispatch.frame,
                dispatch.event.key,
                dispatch.event.phase,
                dispatch.held_frames,
                state.pressed_keys,
            )
        )


def test_trace_input_system_dispatches_events_for_current_frame_in_order():
    ctx = SimulationContext()
    controller = RecordingTeamController()
    input_system = TraceInputSystem(
        [
            InputFrame(
                frame=1,
                events=(
                    KeyEvent("keyboard.e", KeyPhase.PRESS),
                    KeyEvent("mouse.left", KeyPhase.PRESS),
                ),
            ),
            InputFrame(
                frame=3,
                events=(
                    KeyEvent("keyboard.e", KeyPhase.RELEASE),
                    KeyEvent("mouse.left", KeyPhase.RELEASE),
                ),
            ),
        ],
        controller,
    )

    ctx.advance_frame()
    input_system.process_frame(ctx, ctx.current_frame)

    ctx.advance_frame()
    input_system.process_frame(ctx, ctx.current_frame)

    ctx.advance_frame()
    input_system.process_frame(ctx, ctx.current_frame)

    assert controller.received == [
        (1, "keyboard.e", KeyPhase.PRESS, None, frozenset({"keyboard.e"})),
        (1, "mouse.left", KeyPhase.PRESS, None, frozenset({"keyboard.e", "mouse.left"})),
        (3, "keyboard.e", KeyPhase.RELEASE, 2, frozenset({"mouse.left"})),
        (3, "mouse.left", KeyPhase.RELEASE, 2, frozenset()),
    ]
    assert input_system.is_finished()


def test_trace_input_system_ignores_future_frames_until_reached():
    ctx = SimulationContext()
    controller = RecordingTeamController()
    input_system = TraceInputSystem(
        [
            InputFrame(
                frame=2,
                events=(KeyEvent("keyboard.q", KeyPhase.PRESS),),
            ),
            InputFrame(
                frame=3,
                events=(KeyEvent("keyboard.q", KeyPhase.RELEASE),),
            ),
        ],
        controller,
    )

    ctx.advance_frame()
    input_system.process_frame(ctx, ctx.current_frame)

    assert controller.received == []
    assert not input_system.is_finished()

    ctx.advance_frame()
    input_system.process_frame(ctx, ctx.current_frame)

    assert [entry[1:3] for entry in controller.received] == [
        ("keyboard.q", KeyPhase.PRESS),
    ]
    assert not input_system.is_finished()

    ctx.advance_frame()
    input_system.process_frame(ctx, ctx.current_frame)

    assert [entry[1:3] for entry in controller.received] == [
        ("keyboard.q", KeyPhase.PRESS),
        ("keyboard.q", KeyPhase.RELEASE),
    ]
    assert input_system.is_finished()


def test_trace_input_system_rejects_missed_input_frame():
    ctx = SimulationContext()
    controller = RecordingTeamController()
    input_system = TraceInputSystem(
        [
            InputFrame(
                frame=1,
                events=(KeyEvent("keyboard.q", KeyPhase.PRESS),),
            ),
            InputFrame(
                frame=2,
                events=(KeyEvent("keyboard.q", KeyPhase.RELEASE),),
            ),
        ],
        controller,
    )

    ctx.advance_frame(2)

    with pytest.raises(InputTraceError, match="input frame 1 was missed before frame 2"):
        input_system.process_frame(ctx, ctx.current_frame)


def test_trace_input_system_publishes_input_key_events():
    ctx = SimulationContext()
    events: list[GameEvent] = []
    ctx.events.subscribe(EventType.INPUT_KEY_EVENT, events.append)
    controller = RecordingTeamController()
    input_system = TraceInputSystem(
        [
            InputFrame(
                frame=1,
                events=(KeyEvent("keyboard.e", KeyPhase.PRESS),),
            ),
            InputFrame(
                frame=3,
                events=(KeyEvent("keyboard.e", KeyPhase.RELEASE),),
            ),
        ],
        controller,
    )

    ctx.advance_frame()
    input_system.process_frame(ctx, ctx.current_frame)
    ctx.advance_frame()
    input_system.process_frame(ctx, ctx.current_frame)
    ctx.advance_frame()
    input_system.process_frame(ctx, ctx.current_frame)

    assert [event.data for event in events] == [
        {
            "key": "keyboard.e",
            "phase": "press",
            "held_frames": None,
        },
        {
            "key": "keyboard.e",
            "phase": "release",
            "held_frames": 2,
        },
    ]


@pytest.mark.parametrize(
    ("frames", "message"),
    [
        ([InputFrame(-1, ())], "input frame must be positive"),
        ([InputFrame(0, ())], "input frame must be positive"),
        (
            [InputFrame(1, ()), InputFrame(1, ())],
            "input frames must be strictly increasing",
        ),
        (
            [InputFrame(1, (KeyEvent("keyboard.w", KeyPhase.PRESS),))],
            "unsupported input key: keyboard.w",
        ),
        (
            [
                InputFrame(
                    1,
                    (
                        KeyEvent("keyboard.e", KeyPhase.PRESS),
                        KeyEvent("keyboard.e", KeyPhase.RELEASE),
                    ),
                )
            ],
            "duplicate key in input frame 1: keyboard.e",
        ),
        (
            [
                InputFrame(1, (KeyEvent("keyboard.e", KeyPhase.PRESS),)),
                InputFrame(2, (KeyEvent("keyboard.e", KeyPhase.PRESS),)),
            ],
            "key already pressed: keyboard.e",
        ),
        (
            [InputFrame(1, (KeyEvent("keyboard.e", KeyPhase.RELEASE),))],
            "key released before press: keyboard.e",
        ),
        (
            [InputFrame(1, (KeyEvent("keyboard.e", KeyPhase.PRESS),))],
            "input trace ended with pressed keys: keyboard.e",
        ),
    ],
)
def test_trace_input_system_validates_input_trace(
    frames: list[InputFrame],
    message: str,
):
    controller = RecordingTeamController()

    with pytest.raises(InputTraceError, match=message):
        TraceInputSystem(frames, controller)
