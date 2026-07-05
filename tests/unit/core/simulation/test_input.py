from __future__ import annotations

import pytest

from genshin_sim.core.events import EventType, GameEvent
from genshin_sim.core.simulation import (
    InputState,
    InputTraceError,
    KeyEvent,
    KeyEventDispatch,
    KeyInputFrame,
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
            KeyInputFrame(
                frame=1,
                events=(
                    KeyEvent("keyboard.e", KeyPhase.PRESS),
                    KeyEvent("mouse.left", KeyPhase.PRESS),
                ),
            ),
            KeyInputFrame(
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
            KeyInputFrame(
                frame=2,
                events=(KeyEvent("keyboard.q", KeyPhase.PRESS),),
            ),
            KeyInputFrame(
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
            KeyInputFrame(
                frame=1,
                events=(KeyEvent("keyboard.q", KeyPhase.PRESS),),
            ),
            KeyInputFrame(
                frame=2,
                events=(KeyEvent("keyboard.q", KeyPhase.RELEASE),),
            ),
        ],
        controller,
    )

    ctx.advance_frame(2)

    with pytest.raises(InputTraceError, match="第 1 帧输入已错过，当前帧为 2"):
        input_system.process_frame(ctx, ctx.current_frame)


def test_trace_input_system_publishes_input_key_consumed_events():
    ctx = SimulationContext()
    events: list[GameEvent] = []
    ctx.events.subscribe(EventType.INPUT_KEY_CONSUMED, events.append)
    controller = RecordingTeamController()
    input_system = TraceInputSystem(
        [
            KeyInputFrame(1, (KeyEvent("keyboard.e", KeyPhase.PRESS),)),
            KeyInputFrame(3, (KeyEvent("keyboard.e", KeyPhase.RELEASE),)),
        ],
        controller,
    )

    ctx.advance_frame()
    input_system.process_frame(ctx, ctx.current_frame)
    ctx.advance_frame()
    input_system.process_frame(ctx, ctx.current_frame)
    ctx.advance_frame()
    input_system.process_frame(ctx, ctx.current_frame)

    assert [event.payload.to_dict() for event in events] == [
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
        ([KeyInputFrame(-1, ())], "输入帧号必须为正整数"),
        ([KeyInputFrame(0, ())], "输入帧号必须为正整数"),
        (
            [KeyInputFrame(1, ()), KeyInputFrame(1, ())],
            "输入帧号必须严格递增",
        ),
        (
            [KeyInputFrame(1, (KeyEvent("keyboard.w", KeyPhase.PRESS),))],
            "不支持的输入按键：keyboard.w",
        ),
        (
            [
                KeyInputFrame(
                    1,
                    (
                        KeyEvent("keyboard.e", KeyPhase.PRESS),
                        KeyEvent("keyboard.e", KeyPhase.RELEASE),
                    ),
                )
            ],
            "第 1 帧存在重复按键：keyboard.e",
        ),
        (
            [
                KeyInputFrame(1, (KeyEvent("keyboard.e", KeyPhase.PRESS),)),
                KeyInputFrame(2, (KeyEvent("keyboard.e", KeyPhase.PRESS),)),
            ],
            "按键已经处于按下状态：keyboard.e",
        ),
        (
            [KeyInputFrame(1, (KeyEvent("keyboard.e", KeyPhase.RELEASE),))],
            "按键在按下前被释放：keyboard.e",
        ),
        (
            [KeyInputFrame(1, (KeyEvent("keyboard.e", KeyPhase.PRESS),))],
            "输入轨迹结束时仍有按键未释放：keyboard.e",
        ),
    ],
)
def test_trace_input_system_validates_input_trace(
    frames: list[KeyInputFrame],
    message: str,
):
    controller = RecordingTeamController()

    with pytest.raises(InputTraceError, match=message):
        TraceInputSystem(frames, controller)
