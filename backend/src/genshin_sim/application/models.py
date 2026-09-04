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
class AnalysisStageResult:
    """节点运行时中的一个可寻址阶段结果表。"""

    stage_id: str
    columns: tuple[AnalysisColumn, ...]
    rows: tuple[tuple[Any, ...], ...]
    truncated: bool
    source_node_id: str | None = None


@dataclass(frozen=True, slots=True)
class AnalysisNodeExecution:
    """节点运行时中的一次单节点执行：参数 + 已物化输入阶段。"""

    node_id: str
    kind: str
    params: Mapping[str, Any] = field(default_factory=dict)
    input_stages: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AnalysisStageSelection:
    """视图点击派生选择阶段的选择意图。

    - ``group``：按输入阶段的分组列与命中值筛选（饼图/柱状图扇区/柱）；
    - ``row``：按阶段行号取单行（表格行点击，阶段版本内稳定）。
    """

    kind: str  # "group" | "row"
    columns: tuple[str, ...] = ()
    values: tuple[Any, ...] = ()
    row_index: int | None = None


@dataclass(frozen=True, slots=True)
class AnalysisSchemaColumn:
    """可读 schema 中一个表列。"""

    name: str
    type: str
    description: str = ""
    value_kind: str = ""


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
    value_kind: str = ""


@dataclass(frozen=True, slots=True)
class AnalysisEventTypeSchema:
    """一个事件类型的可提取字段清单。"""

    name: str
    fields: tuple[AnalysisEventField, ...]


@dataclass(frozen=True, slots=True)
class AnalysisSchemaNode:
    """输入快照结构树节点：对象 / 列表 / 标量。

    列表节点不枚举位置（队伍/目标等可能是变长集合），由用户输入位置编号；
    叶子经 default_name_template 用 {0}/{1}... 按列表祖先顺序占位。
    """

    key: str
    label: str
    kind: str  # "object" | "list" | "scalar"
    type: str | None = None
    description: str = ""
    default_name: str | None = None
    default_name_template: str | None = None
    value_kind: str = ""
    children: tuple[AnalysisSchemaNode, ...] = ()


@dataclass(frozen=True, slots=True)
class AnalysisReadSchema:
    """取数节点编辑器的可读 schema（表列 + 事件类型字段 + 快照结构树）。"""

    tables: tuple[AnalysisTableSchema, ...]
    event_types: tuple[AnalysisEventTypeSchema, ...]
    snapshot_tree: AnalysisSchemaNode | None = None


__all__ = [
    "AnalysisColumn",
    "AnalysisEventField",
    "AnalysisEventTypeSchema",
    "AnalysisNodeExecution",
    "AnalysisPlan",
    "AnalysisPlanNode",
    "AnalysisReadSchema",
    "AnalysisSchemaNode",
    "AnalysisSchemaColumn",
    "AnalysisStageSelection",
    "AnalysisStageResult",
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
