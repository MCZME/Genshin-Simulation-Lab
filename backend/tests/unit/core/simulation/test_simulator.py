from __future__ import annotations

from genshin_sim.core.events import EventType, GameEvent
from genshin_sim.core.simulation import SimulationContext, SimulationStopReason, Simulator


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


def test_simulator_advances_frame_and_updates_runtime_world():
    calls: list[str] = []
    ctx = SimulationContext()
    runtime_world = RecordingRuntimeWorld(calls)

    def on_simulation_started(event: GameEvent) -> None:
        calls.append(f"simulation_started:{event.frame}")

    def on_frame_started(event: GameEvent) -> None:
        calls.append(f"frame_started:{event.frame}")

    def on_frame_ended(event: GameEvent) -> None:
        calls.append(f"frame_ended:{event.frame}")

    def on_simulation_ended(event: GameEvent) -> None:
        calls.append(f"simulation_ended:{event.frame}")

    ctx.events.subscribe(EventType.SIMULATION_STARTED, on_simulation_started)
    ctx.events.subscribe(EventType.FRAME_STARTED, on_frame_started)
    ctx.events.subscribe(EventType.FRAME_ENDED, on_frame_ended)
    ctx.events.subscribe(EventType.SIMULATION_ENDED, on_simulation_ended)

    result = Simulator(ctx, runtime_world=runtime_world, max_frames=10).run()

    assert result.stop_reason is SimulationStopReason.COMPLETED
    assert result.end_frame == 1
    assert result.frames_run == 1
    assert ctx.current_frame == 1
    assert calls == [
        "simulation_started:0",
        "frame_started:1",
        "world:1",
        "frame_ended:1",
        "simulation_ended:1",
    ]


def test_simulator_records_lifecycle_events_but_not_frame_boundary_events():
    ctx = SimulationContext()

    result = Simulator(ctx, max_frames=10).run()

    assert result.stop_reason is SimulationStopReason.COMPLETED
    assert [event.event_type for event in ctx.events.frame_events] == [
        EventType.SIMULATION_ENDED,
    ]
    assert ctx.events.frame_events[0].payload.to_dict() == {
        "stop_reason": "COMPLETED",
        "end_frame": 1,
        "frames_run": 1,
    }


def test_simulator_continues_until_world_idle():
    calls: list[str] = []
    ctx = SimulationContext()
    runtime_world = RecordingRuntimeWorld(calls, idle_after_frame=3)

    result = Simulator(ctx, runtime_world=runtime_world, max_frames=10).run()

    assert result.stop_reason is SimulationStopReason.COMPLETED
    assert result.end_frame == 3
    assert result.frames_run == 3
    assert runtime_world.frames == [1, 2, 3]


def test_simulator_stops_at_max_frames():
    calls: list[str] = []
    ctx = SimulationContext()
    runtime_world = RecordingRuntimeWorld(calls, idle_after_frame=99)

    result = Simulator(ctx, runtime_world=runtime_world, max_frames=2).run()

    assert result.stop_reason is SimulationStopReason.MAX_FRAMES_REACHED
    assert result.end_frame == 2
    assert result.frames_run == 2
    assert ctx.current_frame == 2


def test_simulator_without_world_completes_after_one_frame():
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
        assert str(exc) == "max_frames 不能为负数"
    else:
        raise AssertionError("negative max_frames should fail")
