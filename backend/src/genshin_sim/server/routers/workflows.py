"""工作流存档 HTTP 路由。"""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends, Request, Response

from genshin_sim.application import ApplicationFacade, WorkflowDetail, WorkflowSummary
from genshin_sim.server.dependencies import require_initialized
from genshin_sim.server.dto.workflows import (
    WorkflowCreateRequest,
    WorkflowListItem,
    WorkflowListResponse,
    WorkflowResponse,
)

router = APIRouter(
    prefix="/api/v1/workflows",
    tags=["workflows"],
    dependencies=[Depends(require_initialized)],
)


@router.get("", response_model=WorkflowListResponse)
def list_workflows(request: Request) -> WorkflowListResponse:
    facade = cast(ApplicationFacade, request.app.state.application)
    return WorkflowListResponse(items=[_summary_to_dto(item) for item in facade.list_workflows()])


@router.post("", response_model=WorkflowResponse, status_code=201)
def create_workflow(
    request: Request,
    payload: WorkflowCreateRequest | None = None,
) -> WorkflowResponse:
    facade = cast(ApplicationFacade, request.app.state.application)
    if payload is not None and payload.name is not None:
        detail = facade.create_workflow(name=payload.name)
    else:
        detail = facade.create_workflow()
    return _detail_to_dto(detail)


@router.get("/{workflow_id}", response_model=WorkflowResponse)
def get_workflow(workflow_id: str, request: Request) -> WorkflowResponse:
    facade = cast(ApplicationFacade, request.app.state.application)
    return _detail_to_dto(facade.get_workflow(workflow_id))


@router.put("/{workflow_id}", response_model=WorkflowResponse)
def save_workflow(
    workflow_id: str,
    definition: dict[str, Any],
    request: Request,
) -> WorkflowResponse:
    facade = cast(ApplicationFacade, request.app.state.application)
    return _detail_to_dto(facade.save_workflow(workflow_id, definition))


@router.delete("/{workflow_id}", status_code=204)
def delete_workflow(workflow_id: str, request: Request) -> Response:
    facade = cast(ApplicationFacade, request.app.state.application)
    facade.delete_workflow(workflow_id)
    return Response(status_code=204)


def _summary_to_dto(item: WorkflowSummary) -> WorkflowListItem:
    return WorkflowListItem(
        id=item.id,
        name=item.name,
        updated_at=item.updated_at,
    )


def _detail_to_dto(detail: WorkflowDetail) -> WorkflowResponse:
    return WorkflowResponse(
        id=detail.id,
        name=detail.name,
        updated_at=detail.updated_at,
        definition=detail.definition,
    )
