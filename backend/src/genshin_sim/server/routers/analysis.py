"""分析查询 HTTP 路由。"""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends, Request, status

from genshin_sim.application import (
    AnalysisNodeExecution,
    AnalysisPlan,
    AnalysisPlanNode,
    AnalysisStageSelection,
    ApplicationFacade,
)
from genshin_sim.server.dependencies import require_initialized
from genshin_sim.server.dto.analysis import (
    AnalysisSchemaResponse,
    CreateAnalysisContextRequest,
    CreateAnalysisContextResponse,
    EventFieldDto,
    EventTypeSchemaDto,
    ExecutePlanRequest,
    ExecutePlanResponse,
    MergeStagesRequest,
    NodeExecutionRequest,
    SchemaColumnDto,
    SchemaNodeDto,
    StageResponse,
    StageSelectionRequest,
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


@router.post("/runtime/contexts", response_model=CreateAnalysisContextResponse)
def create_analysis_context(
    payload: CreateAnalysisContextRequest,
    request: Request,
) -> CreateAnalysisContextResponse:
    facade = cast(ApplicationFacade, request.app.state.application)
    context_id = facade.create_analysis_context(payload.session_ids)
    return CreateAnalysisContextResponse(context_id=context_id)


@router.post(
    "/runtime/contexts/{context_id}/nodes/execute",
    response_model=StageResponse,
)
def execute_analysis_node(
    context_id: str,
    payload: NodeExecutionRequest,
    request: Request,
) -> StageResponse:
    facade = cast(ApplicationFacade, request.app.state.application)
    result = facade.execute_analysis_node(
        context_id,
        AnalysisNodeExecution(
            node_id=payload.node_id,
            kind=payload.kind,
            params=payload.params,
            input_stages=tuple(payload.input_stages),
        ),
    )
    return _stage_to_dto(result)


@router.get(
    "/runtime/contexts/{context_id}/stages/{stage_id}",
    response_model=StageResponse,
)
def read_analysis_stage(
    context_id: str,
    stage_id: str,
    request: Request,
) -> StageResponse:
    facade = cast(ApplicationFacade, request.app.state.application)
    return _stage_to_dto(facade.read_analysis_stage(context_id, stage_id))


@router.post(
    "/runtime/contexts/{context_id}/stages/{stage_id}/select",
    response_model=StageResponse,
)
def select_analysis_stage(
    context_id: str,
    stage_id: str,
    payload: StageSelectionRequest,
    request: Request,
) -> StageResponse:
    facade = cast(ApplicationFacade, request.app.state.application)
    result = facade.select_analysis_stage(
        context_id,
        stage_id,
        AnalysisStageSelection(
            kind=payload.kind,
            columns=tuple(payload.columns),
            values=tuple(payload.values),
            row_index=payload.row_index,
        ),
    )
    return _stage_to_dto(result)


@router.post(
    "/runtime/contexts/{context_id}/merge",
    response_model=StageResponse,
)
def merge_analysis_stages(
    context_id: str,
    payload: MergeStagesRequest,
    request: Request,
) -> StageResponse:
    facade = cast(ApplicationFacade, request.app.state.application)
    return _stage_to_dto(
        facade.merge_analysis_stages(
            context_id,
            tuple(payload.stage_ids),
        )
    )


@router.delete(
    "/runtime/contexts/{context_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def close_analysis_context(context_id: str, request: Request) -> None:
    facade = cast(ApplicationFacade, request.app.state.application)
    facade.close_analysis_context(context_id)


def _table_to_dto(result: Any) -> TableResponse:
    rows: list[list[Any]] = [list(row) for row in result.rows]
    return TableResponse(
        columns=[TableColumnDto(name=column.name, type=column.type) for column in result.columns],
        rows=rows,
        truncated=result.truncated,
    )


def _stage_to_dto(result: Any) -> StageResponse:
    rows: list[list[Any]] = [list(row) for row in result.rows]
    return StageResponse(
        stage_id=result.stage_id,
        columns=[TableColumnDto(name=column.name, type=column.type) for column in result.columns],
        rows=rows,
        truncated=result.truncated,
        source_node_id=result.source_node_id,
    )


def _schema_to_dto(schema: Any) -> AnalysisSchemaResponse:
    return AnalysisSchemaResponse(
        tables=[
            TableSchemaDto(
                name=table.name,
                columns=[
                    SchemaColumnDto(
                        name=column.name,
                        type=column.type,
                        description=column.description,
                        value_kind=column.value_kind,
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
                        path=field.path,
                        type=field.type,
                        description=field.description,
                        value_kind=field.value_kind,
                    )
                    for field in event_type.fields
                ],
            )
            for event_type in schema.event_types
        ],
        snapshot_tree=(
            _node_to_dto(schema.snapshot_tree) if schema.snapshot_tree is not None else None
        ),
    )


def _node_to_dto(node: Any) -> SchemaNodeDto:
    return SchemaNodeDto(
        key=node.key,
        label=node.label,
        kind=node.kind,
        type=node.type,
        description=node.description,
        default_name=node.default_name,
        default_name_template=node.default_name_template,
        value_kind=node.value_kind,
        children=[_node_to_dto(child) for child in node.children],
    )
