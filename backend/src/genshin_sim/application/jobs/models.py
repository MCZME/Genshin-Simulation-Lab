from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from genshin_sim.application.execution.models import SimulationRunSummary


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class SimulationJobState(StrEnum):
    """仿真任务状态。"""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class SimulationJobStatus:
    """仿真任务的轻量状态视图。"""

    job_id: str
    state: SimulationJobState
    session_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: str = field(default_factory=_utc_now)
    started_at: str | None = None
    finished_at: str | None = None


@dataclass(frozen=True, slots=True)
class SimulationJobResult:
    """仿真任务完成后的结果视图。"""

    job_id: str
    state: SimulationJobState
    session_id: str | None = None
    summary: SimulationRunSummary | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: str = field(default_factory=_utc_now)
    started_at: str | None = None
    finished_at: str | None = None
