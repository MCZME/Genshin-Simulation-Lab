from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from types import TracebackType
from typing import TYPE_CHECKING, Protocol, TypeVar, runtime_checkable

from genshin_sim.core.events import EventEngine
from genshin_sim.core.simulation.clock import FrameClock

if TYPE_CHECKING:
    from genshin_sim.core.space.runtime import SpaceRuntime

_SystemT = TypeVar("_SystemT")


@runtime_checkable
class _InitializableSystem(Protocol):
    def initialize(self, context: SimulationContext) -> None: ...


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
    space_runtime: SpaceRuntime | None = None
    # TODO: 引入明确系统协议后，将这里收紧为具体运行时系统类型。
    _systems: list[object] = field(default_factory=list, init=False, repr=False)
    # ContextVar.set 返回的恢复令牌，用于退出 with 块时恢复上一个活动上下文。
    _token: Token[SimulationContext | None] | None = field(default=None, init=False, repr=False)

    @property
    def current_frame(self) -> int:
        return self.clock.current_frame

    def __enter__(self) -> SimulationContext:
        self._token = _current_context.set(self)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        del exc_type, exc_val, exc_tb
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

    def register_system(self, system: _SystemT) -> _SystemT:
        # TODO: 系统协议收紧后，这里的 initialize 钩子也应改为显式协议调用。
        if isinstance(system, _InitializableSystem):
            system.initialize(self)
        self._systems.append(system)
        return system

    def get_system(self, cls_or_name: str | type[object]) -> object | None:
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
        msg = "没有活动的 SimulationContext。"
        raise RuntimeError(msg)
    return ctx
