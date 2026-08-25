"""分析查询 HTTP DTO。"""

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


class SnapshotPathDto(BaseModel):
    path: str
    type: str
    default_name: str
    segments: list[str]


class AnalysisSchemaResponse(BaseModel):
    tables: list[TableSchemaDto]
    event_types: list[EventTypeSchemaDto]
    snapshot_paths: list[SnapshotPathDto] = Field(default_factory=list)
