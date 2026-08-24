"""结果查询 HTTP 路由。"""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, Query, Request

from genshin_sim.application import (
    ApplicationFacade,
    RecordedEvent,
    RunDetail,
    RunListItem,
)
from genshin_sim.server.dependencies import require_initialized
from genshin_sim.server.dto.results import (
    EventItem,
    EventPageResponse,
    RunDetailResponse,
    RunListResponse,
    RunSummary,
)
from genshin_sim.server.dto.results import (
    RunListItem as RunListItemDto,
)

router = APIRouter(
    prefix="/api/v1/results",
    tags=["results"],
    dependencies=[Depends(require_initialized)],
)


@router.get("", response_model=RunListResponse)
def list_results(
    request: Request,
    limit: int = Query(default=50, ge=0, le=200),
    offset: int = Query(default=0, ge=0),
    state: str | None = Query(default=None, pattern="^(completed|failed|cancelled)$"),
) -> RunListResponse:
    facade = cast(ApplicationFacade, request.app.state.application)
    return RunListResponse(
        items=[
            _list_item_to_dto(item)
            for item in facade.list_results(limit=limit, offset=offset, state=state)
        ]
    )


@router.get("/{session_id}", response_model=RunDetailResponse)
def get_run_detail(session_id: str, request: Request) -> RunDetailResponse:
    facade = cast(ApplicationFacade, request.app.state.application)
    detail = facade.get_run(session_id, include_events=False)
    event_count = facade.count_run_events(session_id)
    return _detail_to_dto(detail, event_count)


@router.get("/{session_id}/events", response_model=EventPageResponse)
def get_run_events(
    session_id: str,
    request: Request,
    frame_min: int | None = Query(default=None),
    frame_max: int | None = Query(default=None),
    event_type: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=0, le=500),
) -> EventPageResponse:
    facade = cast(ApplicationFacade, request.app.state.application)
    events = facade.get_run_events(
        session_id,
        frame_min=frame_min,
        frame_max=frame_max,
        event_type=event_type,
        offset=offset,
        limit=limit,
    )
    total = facade.count_run_events(
        session_id,
        frame_min=frame_min,
        frame_max=frame_max,
        event_type=event_type,
    )
    return EventPageResponse(
        items=[_event_to_dto(event) for event in events],
        offset=offset,
        limit=limit,
        total=total,
    )


def _list_item_to_dto(item: RunListItem) -> RunListItemDto:
    return RunListItemDto(
        session_id=item.session_id,
        state=item.state,
        name=item.name,
        stop_reason=item.stop_reason,
        end_frame=item.end_frame,
        frames_run=item.frames_run,
        created_at=item.created_at,
        event_count=item.event_count,
    )


def _detail_to_dto(detail: RunDetail, event_count: int) -> RunDetailResponse:
    return RunDetailResponse(
        session_id=detail.session_id,
        state=detail.state,
        name=_run_name(detail),
        summary=None if detail.summary is None else RunSummary(**detail.summary.to_dict()),
        error_code=detail.error_code,
        error_message=detail.error_message,
        created_at=detail.created_at,
        started_at=detail.started_at,
        finished_at=detail.finished_at,
        event_count=event_count,
    )


def _run_name(detail: RunDetail) -> str:
    meta = detail.input_snapshot.get("meta")
    if isinstance(meta, dict):
        name = meta.get("name")
        if isinstance(name, str) and name.strip():
            return name
    return "未命名仿真"


def _event_to_dto(event: RecordedEvent) -> EventItem:
    return EventItem(
        frame=event.frame,
        event_type=event.event_type,
        data=event.data,
    )
