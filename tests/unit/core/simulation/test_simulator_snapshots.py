from __future__ import annotations

from genshin_sim.core.events import EventType
from genshin_sim.core.simulation import SimulationContext, Simulator
from genshin_sim.core.snapshots.runtime import FrameSnapshot


class SnapshotRecordingWorld:
    def __init__(self, idle_after_frame: int = 3) -> None:
        self.frames: list[int] = []
        self.idle_after_frame = idle_after_frame

    def update_frame(self, context: SimulationContext, frame: int) -> None:
        del context

    def is_idle(self) -> bool:
        return bool(self.frames) and self.frames[-1] >= self.idle_after_frame

    def snapshot_frame(self, context: SimulationContext, frame: int) -> FrameSnapshot:
        self.frames.append(frame)
        return FrameSnapshot(
            frame=frame,
            events=tuple(
                {
                    "frame": event.frame,
                    "event_type": event.event_type.name,
                    "data": event.payload.to_dict(),
                }
                for event in context.events.frame_events
            ),
        )


def test_simulator_exports_initial_and_per_frame_snapshots():
    ctx = SimulationContext()
    world = SnapshotRecordingWorld()

    Simulator(ctx, runtime_world=world, max_frames=3).run()

    assert world.frames == [0, 1, 2, 3]


def test_simulator_initial_snapshot_includes_simulation_started_event():
    ctx = SimulationContext()
    world = SnapshotRecordingWorld()
    snapshots: list[FrameSnapshot] = []

    original = world.snapshot_frame

    def recording_snapshot(context: SimulationContext, frame: int) -> FrameSnapshot:
        snapshot = original(context, frame)
        snapshots.append(snapshot)
        return snapshot

    world.snapshot_frame = recording_snapshot  # type: ignore[method-assign]
    Simulator(ctx, runtime_world=world, max_frames=1).run()

    assert snapshots[0].frame == 0
    assert [event["event_type"] for event in snapshots[0].events] == [
        EventType.SIMULATION_STARTED.name
    ]


def test_simulator_skips_snapshot_for_world_without_exporter():
    class PlainWorld:
        def update_frame(self, context: SimulationContext, frame: int) -> None:
            del context, frame

        def is_idle(self) -> bool:
            return True

    result = Simulator(SimulationContext(), runtime_world=PlainWorld(), max_frames=2).run()

    assert result.frames_run == 1
