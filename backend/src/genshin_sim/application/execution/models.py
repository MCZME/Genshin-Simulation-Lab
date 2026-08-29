from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from genshin_sim.core.simulation import SimulationStopReason


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class RunState(StrEnum):
    """已持久化仿真运行的高层状态。"""

    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class RecordedEvent:
    """一次已记录的仿真事件；``ordinal`` 是会话内全局事实顺序。"""

    frame: int
    event_type: str
    data: dict[str, Any] = field(default_factory=dict)
    ordinal: int = -1

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame": self.frame,
            "event_type": self.event_type,
            "data": dict(self.data),
            "ordinal": self.ordinal,
        }


@dataclass(frozen=True, slots=True)
class SimulationRunSummary:
    stop_reason: str
    end_frame: int
    frames_run: int

    @classmethod
    def from_result(cls, result: Any) -> SimulationRunSummary:
        stop_reason = result.stop_reason
        if isinstance(stop_reason, SimulationStopReason):
            stop_reason_value = stop_reason.name
        else:
            stop_reason_value = str(stop_reason)
        return cls(
            stop_reason=stop_reason_value,
            end_frame=int(result.end_frame),
            frames_run=int(result.frames_run),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "stop_reason": self.stop_reason,
            "end_frame": self.end_frame,
            "frames_run": self.frames_run,
        }


@dataclass(frozen=True, slots=True)
class CompletedSimulationRun:
    input_schema_version: int
    input_kind: str
    input_meta: dict[str, Any]
    input_snapshot: dict[str, Any]
    summary: SimulationRunSummary
    events: tuple[RecordedEvent, ...]
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    initial_snapshot: dict[str, Any] | None = None
    asset_version: str | None = None
    content_version: str | None = None
    seed: str | None = None
    created_at: str = field(default_factory=_utc_now)
    started_at: str | None = None
    finished_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "input_schema_version": self.input_schema_version,
            "input_kind": self.input_kind,
            "input_meta": dict(self.input_meta),
            "input_snapshot": dict(self.input_snapshot),
            "initial_snapshot": (
                None if self.initial_snapshot is None else dict(self.initial_snapshot)
            ),
            "summary": self.summary.to_dict(),
            "events": [event.to_dict() for event in self.events],
            "asset_version": self.asset_version,
            "content_version": self.content_version,
            "seed": self.seed,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


@dataclass(frozen=True, slots=True)
class FailedSimulationRun:
    """失败/取消运行的最小持久化记录。"""

    session_id: str
    input_schema_version: int
    input_kind: str
    input_meta: dict[str, Any]
    input_snapshot: dict[str, Any]
    state: RunState = RunState.FAILED
    error_code: str | None = None
    error_message: str | None = None
    created_at: str = field(default_factory=_utc_now)
    started_at: str | None = None
    finished_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "state": self.state.value,
            "input_schema_version": self.input_schema_version,
            "input_kind": self.input_kind,
            "input_meta": dict(self.input_meta),
            "input_snapshot": dict(self.input_snapshot),
            "error_code": self.error_code,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }
