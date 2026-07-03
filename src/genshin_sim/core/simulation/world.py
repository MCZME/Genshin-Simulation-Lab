from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from genshin_sim.core.simulation.context import SimulationContext


class FrameUpdatable(Protocol):
    """每帧可推进的运行时对象。"""

    def update_frame(self, context: SimulationContext, frame: int) -> None:
        """推进指定帧。"""
        ...

    def is_idle(self) -> bool:
        """对象是否已经空闲。"""
        ...


class BasicRuntimeWorld:
    """按顺序推进一组运行时对象的最小世界实现。"""

    def __init__(self, updatables: Iterable[FrameUpdatable] = ()) -> None:
        self._updatables = list(updatables)

    @property
    def updatables(self) -> tuple[FrameUpdatable, ...]:
        return tuple(self._updatables)

    def add(self, updatable: FrameUpdatable) -> FrameUpdatable:
        self._updatables.append(updatable)
        return updatable

    def update_frame(self, context: SimulationContext, frame: int) -> None:
        for updatable in self._updatables:
            updatable.update_frame(context, frame)

    def is_idle(self) -> bool:
        return all(updatable.is_idle() for updatable in self._updatables)
