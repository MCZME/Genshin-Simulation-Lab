from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any

from genshin_sim.core.events import EventEngine
from genshin_sim.core.simulation.clock import FrameClock

_current_context: ContextVar[SimulationContext | None] = ContextVar(
    "current_simulation_context", default=None
)


@dataclass
class SimulationContext:
    """一次仿真的运行时上下文。

    上下文只保存运行态协作对象，不负责资产读取、结果写库或 UI 展示。
    """

    clock: FrameClock = field(default_factory=FrameClock)
    events: EventEngine = field(default_factory=EventEngine)
    space: Any | None = None
    _systems: list[Any] = field(default_factory=list, init=False, repr=False)
    _token: Token[SimulationContext | None] | None = field(default=None, init=False, repr=False)

    @property
    def current_frame(self) -> int:
        return self.clock.current_frame

    @property
    def event_engine(self) -> EventEngine:
        """旧项目兼容入口。新代码优先使用 ``events``。"""

        return self.events

    @event_engine.setter
    def event_engine(self, value: EventEngine) -> None:
        self.events = value

    def __enter__(self) -> SimulationContext:
        self._token = _current_context.set(self)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._token is not None:
            _current_context.reset(self._token)
            self._token = None

    def advance_frame(self, frames: int = 1) -> int:
        """推进帧时钟。

        推进前清空上一帧事件缓冲，让事件记录与当前帧边界保持一致。
        """

        self.events.clear_frame_events()
        return self.clock.advance(frames)

    def reset(self) -> None:
        self.clock.reset()
        self.events.clear_frame_events()

    def register_system(self, system: Any) -> Any:
        if hasattr(system, "initialize"):
            system.initialize(self)
        self._systems.append(system)
        return system

    def get_system(self, cls_or_name: str | type[Any]) -> Any | None:
        for system in self._systems:
            if isinstance(cls_or_name, str):
                if system.__class__.__name__ == cls_or_name:
                    return system
            elif isinstance(system, cls_or_name):
                return system
        return None

    def clear_systems(self) -> None:
        self._systems.clear()


def get_context() -> SimulationContext:
    ctx = _current_context.get()
    if ctx is None:
        msg = "No active SimulationContext found."
        raise RuntimeError(msg)
    return ctx


def set_context(ctx: SimulationContext) -> None:
    _current_context.set(ctx)


def create_context() -> SimulationContext:
    ctx = SimulationContext()
    set_context(ctx)
    return ctx
