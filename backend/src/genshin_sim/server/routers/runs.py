"""批次运行 HTTP 路由。"""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, Request

from genshin_sim.application import (
    ApplicationFacade,
    BatchMember,
    BatchMemberStatus,
    BatchRunStatus,
)
from genshin_sim.server.dependencies import require_initialized
from genshin_sim.server.dto.runs import (
    RunMemberStatus,
    RunStatusResponse,
    SubmitRunRequest,
)

router = APIRouter(
    prefix="/api/v1/runs",
    tags=["runs"],
    dependencies=[Depends(require_initialized)],
)


@router.post("", response_model=RunStatusResponse, status_code=202)
def submit_run(request: Request, payload: SubmitRunRequest) -> RunStatusResponse:
    facade = cast(ApplicationFacade, request.app.state.application)
    status = facade.submit_batch(
        tuple(
            BatchMember(item_id=member.item_id, input=member.input) for member in payload.members
        ),
        name=payload.name,
        concurrency=payload.concurrency,
    )
    return _run_status_to_dto(status)


@router.get("/{run_id}", response_model=RunStatusResponse)
def get_run(run_id: str, request: Request) -> RunStatusResponse:
    facade = cast(ApplicationFacade, request.app.state.application)
    return _run_status_to_dto(facade.get_batch(run_id))


@router.post("/{run_id}/cancel", response_model=RunStatusResponse)
def cancel_run(run_id: str, request: Request) -> RunStatusResponse:
    facade = cast(ApplicationFacade, request.app.state.application)
    return _run_status_to_dto(facade.cancel_batch(run_id))


def _run_status_to_dto(status: BatchRunStatus) -> RunStatusResponse:
    return RunStatusResponse(
        run_id=status.run_id,
        name=status.name,
        state=status.state,
        concurrency=status.concurrency,
        cancel_requested=status.cancel_requested,
        member_count=status.member_count,
        members=[_member_to_dto(member) for member in status.members],
    )


def _member_to_dto(member: BatchMemberStatus) -> RunMemberStatus:
    return RunMemberStatus(
        item_id=member.item_id,
        state=member.state,
        session_id=member.session_id,
        error_message=member.error_message,
        created_at=member.created_at,
        started_at=member.started_at,
        finished_at=member.finished_at,
    )
