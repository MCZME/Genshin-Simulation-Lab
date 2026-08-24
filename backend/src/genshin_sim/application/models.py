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
class TemplateColumn:
    """模板输出/关系输入的一列：名称 + 类型。"""

    name: str
    type: str


@dataclass(frozen=True, slots=True)
class TemplateParam:
    """模板参数声明。binding 为允许的来源：static/config/session_group/upstream_column。"""

    name: str
    type: str
    required: bool
    binding: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TemplateRelation:
    """模板关系输入声明：名称 + 所需列。"""

    name: str
    columns: tuple[str, ...]
    required: bool


@dataclass(frozen=True, slots=True)
class TemplateOutput:
    """模板输出形状：列名 + 类型。"""

    columns: tuple[TemplateColumn, ...]


@dataclass(frozen=True, slots=True)
class TemplateDeclaration:
    """一张模板的对外声明（前端节点卡与校验的数据源）。"""

    template_id: str
    display_name: str
    params: tuple[TemplateParam, ...]
    relations: tuple[TemplateRelation, ...]
    output: TemplateOutput


@dataclass(frozen=True, slots=True)
class RelationTable:
    """模板执行请求中的一张关系表（列 + 行）。"""

    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]


@dataclass(frozen=True, slots=True)
class TemplateResult:
    """模板执行结果：一张表，行数硬上限内截断。"""

    columns: tuple[TemplateColumn, ...]
    rows: tuple[tuple[Any, ...], ...]
    truncated: bool


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
    "RelationTable",
    "RunDetail",
    "RunListItem",
    "RunState",
    "SimulationInputFile",
    "SimulationJobState",
    "SimulationRunSummary",
    "TemplateColumn",
    "TemplateDeclaration",
    "TemplateOutput",
    "TemplateParam",
    "TemplateRelation",
    "TemplateResult",
    "WorkspaceInfo",
]
