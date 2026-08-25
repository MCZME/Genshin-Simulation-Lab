"""Application 公开数据模型。

入口层和 facade 只消费本模块或 application 顶层导出的模型，
内部 service/execution/jobs 不应成为对外契约。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
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
from genshin_sim.application.jobs.models import SimulationJobState


class AssetListKind(StrEnum):
    """资产只读查询类别。"""

    CHARACTERS = "characters"
    WEAPONS = "weapons"
    ARTIFACT_SETS = "artifact-sets"


@dataclass(frozen=True, slots=True)
class AssetListItem:
    asset_key: str
    source_id: str
    name: str
    usable: bool
    status: str | None = None
    rarity: int | None = None
    element: str | None = None
    weapon_type: str | None = None


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


@dataclass(frozen=True, slots=True)
class AnalysisColumn:
    """分析结果表的一列：名称 + 类型（string/int/float/bool）。"""

    name: str
    type: str


@dataclass(frozen=True, slots=True)
class AnalysisPlanNode:
    """查询计划中的一个节点：id、kind、参数与有序输入。"""

    id: str
    kind: str
    params: Mapping[str, Any] = field(default_factory=dict)
    inputs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AnalysisPlan:
    """一次分析查询计划：会话组 + 节点清单 + 输出清单，不含任何 SQL 文本。"""

    session_ids: tuple[str, ...]
    nodes: tuple[AnalysisPlanNode, ...]
    outputs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AnalysisTableResult:
    """计划输出中的一张表，行数硬上限内截断。"""

    columns: tuple[AnalysisColumn, ...]
    rows: tuple[tuple[Any, ...], ...]
    truncated: bool


@dataclass(frozen=True, slots=True)
class AnalysisSchemaColumn:
    """可读 schema 中一个表列。"""

    name: str
    type: str
    description: str = ""


@dataclass(frozen=True, slots=True)
class AnalysisTableSchema:
    """可读 schema 中一张表。"""

    name: str
    columns: tuple[AnalysisSchemaColumn, ...]


@dataclass(frozen=True, slots=True)
class AnalysisEventField:
    """事件载荷的一个可提取字段：点分路径 + 类型。"""

    path: str
    type: str
    description: str = ""


@dataclass(frozen=True, slots=True)
class AnalysisEventTypeSchema:
    """一个事件类型的可提取字段清单。"""

    name: str
    fields: tuple[AnalysisEventField, ...]


@dataclass(frozen=True, slots=True)
class AnalysisSnapshotPath:
    """输入快照可提取路径：逐段选择器所需的结构目录。"""

    path: str
    type: str
    default_name: str
    segments: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AnalysisReadSchema:
    """取数节点编辑器的可读 schema（表列 + 事件类型字段 + 快照路径目录）。"""

    tables: tuple[AnalysisTableSchema, ...]
    event_types: tuple[AnalysisEventTypeSchema, ...]
    snapshot_paths: tuple[AnalysisSnapshotPath, ...] = ()


__all__ = [
    "AnalysisColumn",
    "AnalysisEventField",
    "AnalysisEventTypeSchema",
    "AnalysisPlan",
    "AnalysisPlanNode",
    "AnalysisReadSchema",
    "AnalysisSnapshotPath",
    "AnalysisSchemaColumn",
    "AnalysisTableResult",
    "AnalysisTableSchema",
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
    "SimulationJobState",
    "SimulationRunSummary",
    "WorkspaceInfo",
]
