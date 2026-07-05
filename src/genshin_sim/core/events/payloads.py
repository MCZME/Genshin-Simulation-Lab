from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class EventPayload(Protocol):
    """事件载荷协议。"""

    def to_dict(self) -> dict[str, object]:
        """转换为可序列化字典。"""
        ...


@dataclass(frozen=True, slots=True)
class EmptyPayload:
    """无字段事件载荷。"""

    def to_dict(self) -> dict[str, object]:
        return {}


@dataclass(frozen=True, slots=True)
class SimulationEndedPayload:
    """仿真结束事件载荷。"""

    stop_reason: str
    end_frame: int
    frames_run: int

    def to_dict(self) -> dict[str, object]:
        return {
            "stop_reason": self.stop_reason,
            "end_frame": self.end_frame,
            "frames_run": self.frames_run,
        }


@dataclass(frozen=True, slots=True)
class InputKeyConsumedPayload:
    """输入按键被消费事件载荷。"""

    key: str
    phase: str
    held_frames: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "phase": self.phase,
            "held_frames": self.held_frames,
        }
