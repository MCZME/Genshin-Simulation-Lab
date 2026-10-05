from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.core.events import EmptyPayload, EventType, GameEvent, SimulationEndedPayload
from genshin_sim.core.protocols import RuntimeWorld
from genshin_sim.core.simulation.context import SimulationContext
from genshin_sim.core.simulation.stop_conditions import (
    IdleStopCondition,
    SimulationStopCondition,
    SimulationStopReason,
)
from genshin_sim.core.snapshots.runtime import SnapshotExportingWorld


@dataclass(frozen=True, slots=True)
class SimulationResult:
    """一次模拟器运行的基础结果。"""

    stop_reason: SimulationStopReason
    end_frame: int
    frames_run: int


class Simulator:
    """最小帧驱动模拟器。

    模拟器只负责帧循环、运行世界推进、基础生命周期事件和停止条件。
    它不理解具体按键含义、角色机制、资产来源或结果持久化。
    第 0 帧是初始化帧，配置装配和运行时对象构造应在进入 ``run`` 前完成；
    ``run`` 从下一帧开始处理输入和运行态更新。
    """

    def __init__(
        self,
        context: SimulationContext,
        *,
        runtime_world: RuntimeWorld | None = None,
        max_frames: int = 18000,
        stop_condition: SimulationStopCondition | None = None,
    ) -> None:
        if max_frames < 0:
            msg = "max_frames 不能为负数"
            raise ValueError(msg)

        self.context = context
        self.runtime_world = runtime_world
        self.max_frames = max_frames
        self.stop_condition = stop_condition or IdleStopCondition(runtime_world)

    def run(self) -> SimulationResult:
        start_frame = self.context.current_frame
        self._publish_simulation_started(start_frame)
        self._export_snapshot(start_frame)

        while self.context.current_frame < self.max_frames:
            frame = self.context.advance_frame()
            self._publish_frame_started(frame)
            self._update_world(frame)
            self._export_snapshot(frame)
            self._publish_frame_ended(frame)

            stop_reason = self.stop_condition.check()
            if stop_reason is not None:
                result = SimulationResult(
                    stop_reason=stop_reason,
                    end_frame=self.context.current_frame,
                    frames_run=self.context.current_frame - start_frame,
                )
                self._publish_simulation_ended(result)
                return result

        result = SimulationResult(
            stop_reason=SimulationStopReason.MAX_FRAMES_REACHED,
            end_frame=self.context.current_frame,
            frames_run=self.context.current_frame - start_frame,
        )
        self._publish_simulation_ended(result)
        return result

    def _update_world(self, frame: int) -> None:
        if self.runtime_world is not None:
            self.runtime_world.update_frame(self.context, frame)

    def _export_snapshot(self, frame: int) -> None:
        """在帧 0 与每帧更新后导出快照（若世界支持）。"""

        if isinstance(self.runtime_world, SnapshotExportingWorld):
            self.runtime_world.snapshot_frame(self.context, frame)

    def _publish_simulation_started(self, frame: int) -> None:
        self.context.events.publish(
            GameEvent(
                EventType.SIMULATION_STARTED,
                frame=frame,
                source=self,
                payload=EmptyPayload(),
            )
        )

    def _publish_simulation_ended(self, result: SimulationResult) -> None:
        self.context.events.publish(
            GameEvent(
                EventType.SIMULATION_ENDED,
                frame=result.end_frame,
                source=self,
                payload=SimulationEndedPayload(
                    stop_reason=result.stop_reason.name,
                    end_frame=result.end_frame,
                    frames_run=result.frames_run,
                ),
            )
        )

    def _publish_frame_started(self, frame: int) -> None:
        self.context.events.publish(
            GameEvent(
                EventType.FRAME_STARTED,
                frame=frame,
                source=self,
                payload=EmptyPayload(),
            )
        )

    def _publish_frame_ended(self, frame: int) -> None:
        self.context.events.publish(
            GameEvent(
                EventType.FRAME_ENDED,
                frame=frame,
                source=self,
                payload=EmptyPayload(),
            )
        )
