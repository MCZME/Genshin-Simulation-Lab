from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from genshin_sim.core.simulation.context import SimulationContext


class RuntimeWorld(Protocol):
    """每帧推进运行时对象的统一入口。"""

    def update_frame(self, context: SimulationContext, frame: int) -> None:
        """推进指定帧的运行态。"""
        ...

    def is_idle(self) -> bool:
        """运行世界是否已经没有待完成的动作或实体任务。"""
        ...


class FrameUpdatable(Protocol):
    """每帧可推进的运行时对象。"""

    def update_frame(self, context: SimulationContext, frame: int) -> None:
        """推进指定帧。"""
        ...

    def is_idle(self) -> bool:
        """对象是否已经空闲。"""
        ...
