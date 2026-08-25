"""分析查询 HTTP 路由。"""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends, Request

from genshin_sim.application import (
    AnalysisPlan,
    AnalysisPlanNode,
    ApplicationFacade,
)
from genshin_sim.server.dependencies import require_initialized
from genshin_sim.server.dto.analysis import (
    AnalysisSchemaResponse,
    EventFieldDto,
    EventTypeSchemaDto,
    ExecutePlanRequest,
    ExecutePlanResponse,
    SchemaColumnDto,
    SnapshotPathDto,
    TableColumnDto,
    TableResponse,
    TableSchemaDto,
)

router = APIRouter(
    prefix="/api/v1/analysis",
    tags=["analysis"],
    dependencies=[Depends(require_initialized)],
)


@router.post("/query", response_model=ExecutePlanResponse)
def execute_plan(payload: ExecutePlanRequest, request: Request) -> ExecutePlanResponse:
    facade = cast(ApplicationFacade, request.app.state.application)
    plan = AnalysisPlan(
        session_ids=tuple(payload.session_ids),
        nodes=tuple(
            AnalysisPlanNode(
                id=item.id,
                kind=item.kind,
                params=item.params,
                inputs=tuple(item.inputs),
            )
            for item in payload.nodes
        ),
        outputs=tuple(payload.outputs),
    )
    tables = facade.execute_analysis_plan(plan)
    return ExecutePlanResponse(
        tables={node_id: _table_to_dto(table) for node_id, table in tables.items()}
    )


@router.get("/schema", response_model=AnalysisSchemaResponse)
def read_schema(request: Request) -> AnalysisSchemaResponse:
    facade = cast(ApplicationFacade, request.app.state.application)
    schema = facade.analysis_schema()
    return _schema_to_dto(schema)


def _table_to_dto(result: Any) -> TableResponse:
    rows: list[list[Any]] = [list(row) for row in result.rows]
    return TableResponse(
        columns=[
            TableColumnDto(name=column.name, type=column.type) for column in result.columns
        ],
        rows=rows,
        truncated=result.truncated,
    )


def _schema_to_dto(schema: Any) -> AnalysisSchemaResponse:
    return AnalysisSchemaResponse(
        tables=[
            TableSchemaDto(
                name=table.name,
                columns=[
                    SchemaColumnDto(
                        name=column.name, type=column.type, description=column.description
                    )
                    for column in table.columns
                ],
            )
            for table in schema.tables
        ],
        event_types=[
            EventTypeSchemaDto(
                name=event_type.name,
                fields=[
                    EventFieldDto(
                        path=field.path, type=field.type, description=field.description
                    )
                    for field in event_type.fields
                ],
            )
            for event_type in schema.event_types
        ],
        snapshot_paths=[
            SnapshotPathDto(
                path=item.path,
                type=item.type,
                default_name=item.default_name,
                segments=list(item.segments),
            )
            for item in schema.snapshot_paths
        ],
    )
