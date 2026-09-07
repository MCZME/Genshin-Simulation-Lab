from __future__ import annotations

from genshin_sim.core.simulation import BasicRuntimeWorld, SimulationContext


class RecordingUpdatable:
    def __init__(self, name: str, calls: list[str], idle_after_frame: int = 1) -> None:
        self.name = name
        self.calls = calls
        self.frames: list[int] = []
        self.idle_after_frame = idle_after_frame

    def update_frame(self, context: SimulationContext, frame: int) -> None:
        assert context.current_frame == frame
        self.frames.append(frame)
        self.calls.append(f"{self.name}:{frame}")

    def is_idle(self) -> bool:
        return bool(self.frames) and self.frames[-1] >= self.idle_after_frame


def test_basic_runtime_world_updates_updatables_in_order():
    calls: list[str] = []
    ctx = SimulationContext()
    first = RecordingUpdatable("first", calls)
    second = RecordingUpdatable("second", calls)
    world = BasicRuntimeWorld([first])
    world.add(second)

    ctx.advance_frame()
    world.update_frame(ctx, ctx.current_frame)

    assert calls == ["first:1", "second:1"]
    assert world.updatables == (first, second)


def test_basic_runtime_world_is_idle_only_when_all_updatables_are_idle():
    calls: list[str] = []
    ctx = SimulationContext()
    first = RecordingUpdatable("first", calls, idle_after_frame=1)
    second = RecordingUpdatable("second", calls, idle_after_frame=2)
    world = BasicRuntimeWorld([first, second])

    ctx.advance_frame()
    world.update_frame(ctx, ctx.current_frame)

    assert not world.is_idle()

    ctx.advance_frame()
    world.update_frame(ctx, ctx.current_frame)

    assert world.is_idle()
