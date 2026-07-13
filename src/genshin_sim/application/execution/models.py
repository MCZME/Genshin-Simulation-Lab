from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from genshin_sim.core.simulation import SimulationStopReason


class RunState(StrEnum):
    """已持久化仿真运行的高层状态。"""

    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class RecordedEvent:
    frame: int
    event_type: str
    data: dict[str, Any] = field(default_factory=dict)
    source_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame": self.frame,
            "event_type": self.event_type,
            "data": dict(self.data),
            "source_type": self.source_type,
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
    config_schema_version: int
    config_kind: str
    config_meta: dict[str, Any]
    config_snapshot: dict[str, Any]
    summary: SimulationRunSummary
    events: tuple[RecordedEvent, ...]
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "config_schema_version": self.config_schema_version,
            "config_kind": self.config_kind,
            "config_meta": dict(self.config_meta),
            "config_snapshot": dict(self.config_snapshot),
            "summary": self.summary.to_dict(),
            "events": [event.to_dict() for event in self.events],
            "created_at": self.created_at,
        }
