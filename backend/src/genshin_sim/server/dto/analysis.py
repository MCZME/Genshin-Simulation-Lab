"""分析查询 HTTP DTO。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PlanNodeDto(BaseModel):
    id: str
    kind: str
    params: dict[str, Any] = Field(default_factory=dict)
    inputs: list[str] = Field(default_factory=list)


class ExecutePlanRequest(BaseModel):
    session_ids: list[str] = Field(default_factory=list)
    nodes: list[PlanNodeDto] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)


class TableColumnDto(BaseModel):
    name: str
    type: str


class TableResponse(BaseModel):
    columns: list[TableColumnDto]
    rows: list[list[Any]]
    truncated: bool


class ExecutePlanResponse(BaseModel):
    tables: dict[str, TableResponse]


class SchemaColumnDto(BaseModel):
    name: str
    type: str
    description: str = ""


class TableSchemaDto(BaseModel):
    name: str
    columns: list[SchemaColumnDto]


class EventFieldDto(BaseModel):
    path: str
    type: str
    description: str = ""


class EventTypeSchemaDto(BaseModel):
    name: str
    fields: list[EventFieldDto]


class SchemaNodeDto(BaseModel):
    """输入快照结构树节点（object / list / scalar）。"""

    key: str
    label: str
    kind: str
    type: str | None = None
    description: str = ""
    default_name: str | None = None
    default_name_template: str | None = None
    children: list[SchemaNodeDto] = Field(default_factory=list)


class AnalysisSchemaResponse(BaseModel):
    tables: list[TableSchemaDto]
    event_types: list[EventTypeSchemaDto]
    snapshot_tree: SchemaNodeDto | None = None
