"""分析模板 HTTP 路由。"""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends, Request

from genshin_sim.application import (
    ApplicationFacade,
    RelationTable,
    TemplateColumn,
    TemplateDeclaration,
    TemplateParam,
    TemplateRelation,
    TemplateResult,
)
from genshin_sim.server.dependencies import require_initialized
from genshin_sim.server.dto.analysis import (
    ExecuteTemplateRequest,
    TemplateColumnDto,
    TemplateDeclarationDto,
    TemplateListResponse,
    TemplateOutputDto,
    TemplateParamDto,
    TemplateRelationDto,
    TemplateResultResponse,
)

router = APIRouter(
    prefix="/api/v1/analysis",
    tags=["analysis"],
    dependencies=[Depends(require_initialized)],
)


@router.get("/templates", response_model=TemplateListResponse)
def list_templates(request: Request) -> TemplateListResponse:
    facade = cast(ApplicationFacade, request.app.state.application)
    return TemplateListResponse(
        items=[_declaration_to_dto(declaration) for declaration in facade.list_analysis_templates()]
    )


@router.post("/templates/{template_id}/execute", response_model=TemplateResultResponse)
def execute_template(
    template_id: str,
    payload: ExecuteTemplateRequest,
    request: Request,
) -> TemplateResultResponse:
    facade = cast(ApplicationFacade, request.app.state.application)
    relations = {
        name: RelationTable(
            columns=tuple(item.columns),
            rows=tuple(tuple(row) for row in item.rows),
        )
        for name, item in payload.relations.items()
    }
    result = facade.execute_analysis_template(
        template_id,
        params=payload.params,
        relations=relations,
    )
    return _result_to_dto(result)


def _declaration_to_dto(declaration: TemplateDeclaration) -> TemplateDeclarationDto:
    return TemplateDeclarationDto(
        template_id=declaration.template_id,
        display_name=declaration.display_name,
        params=[_param_to_dto(param) for param in declaration.params],
        relations=[_relation_to_dto(relation) for relation in declaration.relations],
        output=TemplateOutputDto(
            columns=[_column_to_dto(column) for column in declaration.output.columns]
        ),
    )


def _param_to_dto(param: TemplateParam) -> TemplateParamDto:
    return TemplateParamDto(
        name=param.name,
        type=param.type,
        required=param.required,
        binding=list(param.binding),
    )


def _relation_to_dto(relation: TemplateRelation) -> TemplateRelationDto:
    return TemplateRelationDto(
        name=relation.name,
        columns=list(relation.columns),
        required=relation.required,
    )


def _column_to_dto(column: TemplateColumn) -> TemplateColumnDto:
    return TemplateColumnDto(name=column.name, type=column.type)


def _result_to_dto(result: TemplateResult) -> TemplateResultResponse:
    rows: list[list[Any]] = [list(row) for row in result.rows]
    return TemplateResultResponse(
        columns=[_column_to_dto(column) for column in result.columns],
        rows=rows,
        truncated=result.truncated,
    )
