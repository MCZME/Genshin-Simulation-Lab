"""结果查询 HTTP 路由。"""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, Query, Request

from genshin_sim.application import (
    ApplicationError,
    ApplicationFacade,
    RecordedEvent,
    RunDetail,
    RunListItem,
)
from genshin_sim.server.dependencies import require_initialized
from genshin_sim.server.dto.results import (
    DamageEventView,
    EventDetailResponse,
    EventItem,
    EventPageResponse,
    FrameStateResponse,
    RunDetailResponse,
    RunListResponse,
    RunSummary,
    SessionEntitiesView,
    SessionEntityCharacter,
    SessionEntityTarget,
)
from genshin_sim.server.dto.results import (
    RunListItem as RunListItemDto,
)

router = APIRouter(
    prefix="/api/v1/results",
    tags=["results"],
    dependencies=[Depends(require_initialized)],
)

_UTC_ISO_DATETIME_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?\+00:00$"
MAX_SESSION_IDS = 200


@router.get("", response_model=RunListResponse)
def list_results(
    request: Request,
    limit: int = Query(default=50, ge=0, le=200),
    offset: int = Query(default=0, ge=0),
    state: str | None = Query(default=None, pattern="^(completed|failed|cancelled)$"),
    q: str | None = Query(default=None, max_length=64),
    created_from: str | None = Query(default=None, pattern=_UTC_ISO_DATETIME_PATTERN),
    created_to: str | None = Query(default=None, pattern=_UTC_ISO_DATETIME_PATTERN),
    ids: str | None = Query(default=None),
) -> RunListResponse:
    facade = cast(ApplicationFacade, request.app.state.application)
    session_ids = _parse_session_ids(ids)
    if session_ids is not None:
        items = facade.list_results(
            limit=limit,
            offset=offset,
            session_ids=session_ids,
        )
    else:
        items = facade.list_results(
            limit=limit,
            offset=offset,
            state=state,
            name_query=q,
            created_from=created_from,
            created_to=created_to,
        )
    return RunListResponse(items=[_list_item_to_dto(item) for item in items])


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


@router.get("/{session_id}/events/{ordinal}", response_model=EventDetailResponse)
def get_run_event_detail(
    session_id: str,
    ordinal: int,
    request: Request,
) -> EventDetailResponse:
    facade = cast(ApplicationFacade, request.app.state.application)
    event = facade.get_run_event(session_id, ordinal)
    if event is None:
        raise ApplicationError(
            "not_found",
            f"事件 {session_id}/{ordinal} 不存在",
        )
    raw_entities = facade.get_run_entities(session_id)
    entities = SessionEntitiesView(
        characters=[
            SessionEntityCharacter.model_validate(item) for item in raw_entities["characters"]
        ],
        targets=[SessionEntityTarget.model_validate(item) for item in raw_entities["targets"]],
    )
    return EventDetailResponse(
        session_id=session_id,
        ordinal=event.ordinal,
        frame=event.frame,
        event_type=event.event_type,
        data=event.data,
        damage=_damage_view(event),
        entities=entities,
    )


@router.get("/{session_id}/frames/{frame}", response_model=FrameStateResponse)
def get_frame_state(
    session_id: str,
    frame: int,
    request: Request,
) -> FrameStateResponse:
    facade = cast(ApplicationFacade, request.app.state.application)
    return FrameStateResponse.model_validate(facade.get_frame_state(session_id, frame))


def _damage_view(event: RecordedEvent) -> DamageEventView | None:
    """从 DAMAGE_RESOLVED 存储数据规范化伤害视图；其余事件返回 None。"""

    if event.event_type != "DAMAGE_RESOLVED":
        return None
    result = event.data.get("result")
    if not isinstance(result, dict):
        return None
    return DamageEventView(summary=result, audit=event.data.get("audit"))


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


def _parse_session_ids(raw: str | None) -> tuple[str, ...] | None:
    if raw is None or not raw.strip():
        return None
    session_ids = tuple(dict.fromkeys(part.strip() for part in raw.split(",") if part.strip()))
    if len(session_ids) > MAX_SESSION_IDS:
        raise ApplicationError(
            "validation_failed",
            f"ids 最多支持 {MAX_SESSION_IDS} 个会话",
        )
    return session_ids


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
        ordinal=event.ordinal,
        frame=event.frame,
        event_type=event.event_type,
        data=event.data,
    )
