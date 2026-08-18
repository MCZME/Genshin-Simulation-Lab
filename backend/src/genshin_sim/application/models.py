"""Application 公开数据模型。

入口层和 facade 只消费本模块或 application 顶层导出的模型，
内部 service/execution/jobs 不应成为对外契约。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from genshin_sim.application.batch.models import (
    BatchDiagnostic,
    BatchInput,
    BatchMember,
    BatchMemberState,
    BatchMemberStatus,
    BatchMemberValidation,
    BatchRunState,
    BatchRunStatus,
    BatchValidationResult,
)
from genshin_sim.application.execution.models import (
    RecordedEvent,
    RunState,
    SimulationRunSummary,
)
from genshin_sim.application.jobs.models import (
    SimulationJobResult,
    SimulationJobState,
    SimulationJobStatus,
)


class AssetListKind(StrEnum):
    """资产只读查询类别。"""

    CHARACTERS = "characters"
    WEAPONS = "weapons"
    ARTIFACT_SETS = "artifact-sets"


@dataclass(frozen=True, slots=True)
class AssetListItem:
    asset_key: str
    name: str


@dataclass(frozen=True, slots=True)
class WorkspaceInfo:
    data_dir: str
    asset_db_version: str
    initialized: bool


@dataclass(frozen=True, slots=True)
class RunListItem:
    session_id: str
    state: str
    name: str
    stop_reason: str
    end_frame: int
    frames_run: int
    created_at: str
    event_count: int


@dataclass(frozen=True, slots=True)
class RunDetail:
    session_id: str
    state: str
    input_snapshot: dict[str, Any]
    initial_snapshot: dict[str, Any] | None
    summary: SimulationRunSummary | None
    events: tuple[RecordedEvent, ...]
    error_code: str | None
    error_message: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None


@dataclass(frozen=True, slots=True)
class SimulationInputFile:
    path: Path
    input_key: str
    name: str = ""
    schema_version: int | None = None
    error: str | None = None


__all__ = [
    "AssetListItem",
    "AssetListKind",
    "BatchDiagnostic",
    "BatchInput",
    "BatchMember",
    "BatchMemberState",
    "BatchMemberStatus",
    "BatchMemberValidation",
    "BatchRunState",
    "BatchRunStatus",
    "BatchValidationResult",
    "RecordedEvent",
    "RunDetail",
    "RunListItem",
    "RunState",
    "SimulationInputFile",
    "SimulationJobResult",
    "SimulationJobState",
    "SimulationJobStatus",
    "SimulationRunSummary",
    "WorkspaceInfo",
]
