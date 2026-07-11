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
class InputKeyReceivedPayload:
    """输入按键事实进入运行时处理的事件载荷。"""

    key: str
    phase: str
    order: int
    session_id: int

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "phase": self.phase,
            "order": self.order,
            "session_id": self.session_id,
        }


@dataclass(frozen=True, slots=True)
class InputSessionBoundaryPayload:
    """输入会话边界被 ActionManager 处理的事件载荷。"""

    session_id: int
    key: str
    phase: str
    order: int
    press_frame: int
    held_frames: int
    physical_state: str
    control_state: str
    owner_kind: str
    owner_slot: int | None
    interpreter_id: str
    binding_scope: str
    will_interpret: bool
    skip_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "key": self.key,
            "phase": self.phase,
            "order": self.order,
            "press_frame": self.press_frame,
            "held_frames": self.held_frames,
            "physical_state": self.physical_state,
            "control_state": self.control_state,
            "owner_kind": self.owner_kind,
            "owner_slot": self.owner_slot,
            "interpreter_id": self.interpreter_id,
            "binding_scope": self.binding_scope,
            "will_interpret": self.will_interpret,
            "skip_reason": self.skip_reason,
        }
