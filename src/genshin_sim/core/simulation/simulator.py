from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Protocol

from genshin_sim.core.events import EventType, GameEvent
from genshin_sim.core.simulation.context import SimulationContext


class SimulationStopReason(Enum):
    """仿真停止原因。"""

    COMPLETED = auto()
    MAX_FRAMES_REACHED = auto()


@dataclass(frozen=True, slots=True)
class SimulationResult:
    """一次模拟器运行的基础结果。"""

    stop_reason: SimulationStopReason
    end_frame: int
    frames_run: int


class InputSystem(Protocol):
    """按帧消费输入轨迹的运行时入口。"""

    def process_frame(self, context: SimulationContext, frame: int) -> None:
        """处理指定帧的输入事件。"""
        ...

    def is_finished(self) -> bool:
        """输入轨迹是否已经消费完成。"""
        ...


class RuntimeWorld(Protocol):
    """每帧推进运行时对象的统一入口。"""

    def update_frame(self, context: SimulationContext, frame: int) -> None:
        """推进指定帧的运行态。"""
        ...

    def is_idle(self) -> bool:
        """运行世界是否已经没有待完成的动作或实体任务。"""
        ...


class Simulator:
    """最小帧驱动模拟器。

    模拟器只负责帧循环、输入入口调用、运行世界推进、帧结束事件和停止条件。
    它不理解具体按键含义、角色机制、资产来源或结果持久化。
    """

    def __init__(
        self,
        context: SimulationContext,
        *,
        input_system: InputSystem | None = None,
        runtime_world: RuntimeWorld | None = None,
        max_frames: int = 18000,
    ) -> None:
        if max_frames < 0:
            msg = "max_frames must be non-negative"
            raise ValueError(msg)

        self.context = context
        self.input_system = input_system
        self.runtime_world = runtime_world
        self.max_frames = max_frames

    def run(self) -> SimulationResult:
        start_frame = self.context.current_frame

        while self.context.current_frame < self.max_frames:
            frame = self.context.advance_frame()
            self._process_input(frame)
            self._update_world(frame)
            self._publish_frame_end(frame)

            if self._is_finished():
                return SimulationResult(
                    stop_reason=SimulationStopReason.COMPLETED,
                    end_frame=self.context.current_frame,
                    frames_run=self.context.current_frame - start_frame,
                )

        return SimulationResult(
            stop_reason=SimulationStopReason.MAX_FRAMES_REACHED,
            end_frame=self.context.current_frame,
            frames_run=self.context.current_frame - start_frame,
        )

    def _process_input(self, frame: int) -> None:
        if self.input_system is not None:
            self.input_system.process_frame(self.context, frame)

    def _update_world(self, frame: int) -> None:
        if self.runtime_world is not None:
            self.runtime_world.update_frame(self.context, frame)

    def _publish_frame_end(self, frame: int) -> None:
        self.context.events.publish(GameEvent(EventType.FRAME_END, frame=frame, record=False))

    def _is_finished(self) -> bool:
        input_finished = self.input_system is None or self.input_system.is_finished()
        world_idle = self.runtime_world is None or self.runtime_world.is_idle()
        return input_finished and world_idle
