from __future__ import annotations

from genshin_sim.core.events import EventType, GameEvent
from genshin_sim.core.simulation import (
    BasicRuntimeWorld,
    InputFrame,
    KeyEvent,
    KeyEventDispatch,
    KeyPhase,
    SimulationContext,
    SimulationStopReason,
    Simulator,
    TraceInputSystem,
)


class RecordingInputSystem:
    def __init__(self, calls: list[str], finish_after_frame: int = 1) -> None:
        self.calls = calls
        self.frames: list[int] = []
        self.finish_after_frame = finish_after_frame

    def process_frame(self, context: SimulationContext, frame: int) -> None:
        self.calls.append(f"input:{frame}")
        self.frames.append(frame)
        assert context.current_frame == frame

    def is_finished(self) -> bool:
        return bool(self.frames) and self.frames[-1] >= self.finish_after_frame


class RecordingRuntimeWorld:
    def __init__(self, calls: list[str], idle_after_frame: int = 1) -> None:
        self.calls = calls
        self.frames: list[int] = []
        self.idle_after_frame = idle_after_frame

    def update_frame(self, context: SimulationContext, frame: int) -> None:
        self.calls.append(f"world:{frame}")
        self.frames.append(frame)
        assert context.current_frame == frame

    def is_idle(self) -> bool:
        return bool(self.frames) and self.frames[-1] >= self.idle_after_frame


class RecordingTeamController:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def handle_key_event(self, context, dispatch: KeyEventDispatch, state) -> None:
        self.calls.append(f"key:{dispatch.frame}:{dispatch.event.key}:{dispatch.event.phase}")


def test_simulator_advances_frame_and_calls_input_before_world_then_frame_end():
    calls: list[str] = []
    ctx = SimulationContext()
    input_system = RecordingInputSystem(calls)
    runtime_world = RecordingRuntimeWorld(calls)

    def on_frame_end(event: GameEvent) -> None:
        calls.append(f"frame_end:{event.frame}")

    ctx.events.subscribe(EventType.FRAME_END, on_frame_end)

    result = Simulator(
        ctx,
        input_system=input_system,
        runtime_world=runtime_world,
        max_frames=10,
    ).run()

    assert result.stop_reason is SimulationStopReason.COMPLETED
    assert result.end_frame == 1
    assert result.frames_run == 1
    assert ctx.current_frame == 1
    assert calls == ["input:1", "world:1", "frame_end:1"]


def test_simulator_continues_until_input_finished_and_world_idle():
    calls: list[str] = []
    ctx = SimulationContext()
    input_system = RecordingInputSystem(calls, finish_after_frame=2)
    runtime_world = RecordingRuntimeWorld(calls, idle_after_frame=3)

    result = Simulator(
        ctx,
        input_system=input_system,
        runtime_world=runtime_world,
        max_frames=10,
    ).run()

    assert result.stop_reason is SimulationStopReason.COMPLETED
    assert result.end_frame == 3
    assert result.frames_run == 3
    assert input_system.frames == [1, 2, 3]
    assert runtime_world.frames == [1, 2, 3]


def test_simulator_stops_at_max_frames():
    calls: list[str] = []
    ctx = SimulationContext()
    input_system = RecordingInputSystem(calls, finish_after_frame=99)
    runtime_world = RecordingRuntimeWorld(calls, idle_after_frame=99)

    result = Simulator(
        ctx,
        input_system=input_system,
        runtime_world=runtime_world,
        max_frames=2,
    ).run()

    assert result.stop_reason is SimulationStopReason.MAX_FRAMES_REACHED
    assert result.end_frame == 2
    assert result.frames_run == 2
    assert ctx.current_frame == 2


def test_simulator_without_input_or_world_completes_after_one_frame():
    ctx = SimulationContext()

    result = Simulator(ctx, max_frames=10).run()

    assert result.stop_reason is SimulationStopReason.COMPLETED
    assert result.end_frame == 1
    assert result.frames_run == 1


def test_simulator_rejects_negative_max_frames():
    ctx = SimulationContext()

    try:
        Simulator(ctx, max_frames=-1)
    except ValueError as exc:
        assert str(exc) == "max_frames must be non-negative"
    else:
        raise AssertionError("negative max_frames should fail")


def test_simulator_runs_trace_input_system_and_basic_runtime_world_together():
    calls: list[str] = []
    ctx = SimulationContext()
    controller = RecordingTeamController(calls)
    input_system = TraceInputSystem(
        [
            InputFrame(
                frame=1,
                events=(KeyEvent("keyboard.e", KeyPhase.PRESS),),
            ),
            InputFrame(
                frame=2,
                events=(KeyEvent("keyboard.e", KeyPhase.RELEASE),),
            ),
        ],
        controller,
    )
    runtime_world = BasicRuntimeWorld([RecordingRuntimeWorld(calls)])

    result = Simulator(
        ctx,
        input_system=input_system,
        runtime_world=runtime_world,
        max_frames=10,
    ).run()

    assert result.stop_reason is SimulationStopReason.COMPLETED
    assert result.end_frame == 2
    assert calls == [
        "key:1:keyboard.e:press",
        "world:1",
        "key:2:keyboard.e:release",
        "world:2",
    ]
