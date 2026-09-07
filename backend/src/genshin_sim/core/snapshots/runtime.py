"""帧快照导出运行时。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from genshin_sim.core.events import GameEvent

if TYPE_CHECKING:
    from genshin_sim.core.simulation.context import SimulationContext

type SnapshotProvider = Callable[[int], dict[str, object]]


class SnapshotError(Exception):
    """快照错误基类。"""


class DuplicateSnapshotProviderError(SnapshotError, ValueError):
    """重复注册快照 provider。"""


@dataclass(frozen=True, slots=True)
class EventSnapshot:
    """一次事件的持久化快照形态。"""

    event_type: str
    frame: int
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_event(cls, event: GameEvent) -> EventSnapshot:
        return cls(
            event_type=event.event_type.name,
            frame=event.frame,
            data=event.payload.to_dict(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "frame": self.frame,
            "data": dict(self.data),
        }


@runtime_checkable
class SnapshotExportingWorld(Protocol):
    """可导出帧快照的运行时世界协议。"""

    def snapshot_frame(self, context: SimulationContext, frame: int) -> object | None: ...


@dataclass(frozen=True, slots=True)
class FrameSnapshot:
    """一帧的导出快照。"""

    frame: int
    events: tuple[dict[str, object], ...] = ()
    providers: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise ValueError("frame 必须是非负整数")
        object.__setattr__(self, "events", tuple(self.events))
        object.__setattr__(self, "providers", dict(self.providers))

    def to_dict(self) -> dict[str, object]:
        return {
            "frame": self.frame,
            "events": [dict(event) for event in self.events],
            "providers": dict(self.providers),
        }


class SnapshotRuntime:
    """每帧导出快照；由 Simulator 在帧 0 与每帧更新后调用。"""

    def __init__(self) -> None:
        self._providers: dict[str, SnapshotProvider] = {}
        self._snapshots: dict[int, FrameSnapshot] = {}

    @property
    def provider_keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))

    @property
    def snapshots(self) -> tuple[FrameSnapshot, ...]:
        return tuple(self._snapshots[frame] for frame in sorted(self._snapshots))

    def register(self, key: str, provider: SnapshotProvider) -> None:
        if not isinstance(key, str) or not key.strip():
            raise ValueError("key 必须是非空字符串")
        if not callable(provider):
            raise TypeError("provider 必须可调用")
        if key in self._providers:
            raise DuplicateSnapshotProviderError(f"重复注册快照 provider：{key}")
        self._providers[key] = provider

    def snapshot_frame(self, context: SimulationContext, frame: int) -> FrameSnapshot:
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            raise ValueError("frame 必须是非负整数")

        events = tuple(
            EventSnapshot.from_event(event).to_dict() for event in context.events.frame_events
        )
        providers: dict[str, object] = {
            key: self._providers[key](frame) for key in sorted(self._providers)
        }
        snapshot = FrameSnapshot(frame=frame, events=events, providers=providers)
        self._snapshots[frame] = snapshot
        return snapshot

    def snapshot_at(self, frame: int) -> FrameSnapshot | None:
        return self._snapshots.get(frame)
