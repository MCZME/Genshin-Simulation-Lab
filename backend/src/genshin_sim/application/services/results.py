from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from genshin_sim.application.execution.models import RecordedEvent
from genshin_sim.application.models import RunDetail, RunListItem
from genshin_sim.application.services.frame_state import fold_frame_state
from genshin_sim.application.services.protocols import ResultRepository

logger = logging.getLogger(__name__)


class FrameOutOfRangeError(ValueError):
    """请求帧超出会话运行范围或会话没有可投影的状态。"""


class ResultsService:
    """读取已持久化的仿真运行。"""

    def __init__(self, repository: ResultRepository) -> None:
        self.repository = repository

    def list_runs(
        self,
        limit: int = 50,
        offset: int = 0,
        state: str | None = None,
        *,
        name_query: str | None = None,
        created_from: str | None = None,
        created_to: str | None = None,
        session_ids: tuple[str, ...] | list[str] | None = None,
    ) -> tuple[RunListItem, ...]:
        logger.debug(
            "列出仿真结果",
            extra={
                "limit": limit,
                "offset": offset,
                "state": state,
                "name_query": name_query,
                "created_from": created_from,
                "created_to": created_to,
                "session_ids": session_ids,
            },
        )
        items = self.repository.list_runs(
            limit=limit,
            offset=offset,
            state=state,
            name_query=name_query,
            created_from=created_from,
            created_to=created_to,
            session_ids=session_ids,
        )
        if session_ids is None:
            return items
        by_id = {item.session_id: item for item in items}
        return tuple(
            by_id[session_id] for session_id in dict.fromkeys(session_ids) if session_id in by_id
        )

    def inspect_run(self, session_id: str, *, include_events: bool = True) -> RunDetail:
        logger.debug(
            "查看仿真结果",
            extra={"session_id": session_id, "include_events": include_events},
        )
        return self.repository.get_run(session_id, include_events=include_events)

    def get_events(
        self,
        session_id: str,
        *,
        frame_min: int | None = None,
        frame_max: int | None = None,
        event_type: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> tuple[RecordedEvent, ...]:
        logger.debug(
            "查询仿真事件",
            extra={
                "session_id": session_id,
                "frame_min": frame_min,
                "frame_max": frame_max,
                "event_type": event_type,
                "offset": offset,
                "limit": limit,
            },
        )
        return self.repository.get_events(
            session_id,
            frame_min=frame_min,
            frame_max=frame_max,
            event_type=event_type,
            offset=offset,
            limit=limit,
        )

    def get_event(self, session_id: str, ordinal: int) -> RecordedEvent | None:
        """按会话内事实顺序读取单条事件；事件不存在返回 None。"""

        logger.debug(
            "查询单条仿真事件",
            extra={"session_id": session_id, "ordinal": ordinal},
        )
        return self.repository.get_event(session_id, ordinal)

    def get_frame_state(self, session_id: str, frame: int) -> dict[str, Any]:
        """读取指定帧的帧末角色状态（初始快照基线 + 事件折叠）。"""

        logger.debug(
            "查询帧状态投影",
            extra={"session_id": session_id, "frame": frame},
        )
        detail = self.repository.get_run(session_id, include_events=False)
        summary = detail.summary
        end_frame = None if summary is None else summary.end_frame
        if end_frame is None or frame < 0 or frame > end_frame:
            raise FrameOutOfRangeError(
                f"frame {frame} 超出会话 {session_id} 的运行范围 [0, {end_frame}]"
            )
        initial_snapshot = self.repository.get_initial_snapshot(session_id)
        if initial_snapshot is None:
            raise FrameOutOfRangeError(f"会话 {session_id} 没有可用的初始快照")
        events = self.repository.get_events(session_id, frame_max=frame)
        return fold_frame_state(
            session_id=session_id,
            frame=frame,
            initial_snapshot=initial_snapshot,
            events=events,
        )

    def count_events(
        self,
        session_id: str,
        *,
        frame_min: int | None = None,
        frame_max: int | None = None,
        event_type: str | None = None,
    ) -> int:
        """返回匹配查询条件的事件总数，供分页响应使用。"""

        logger.debug(
            "统计仿真事件",
            extra={
                "session_id": session_id,
                "frame_min": frame_min,
                "frame_max": frame_max,
                "event_type": event_type,
            },
        )
        return self.repository.count_events(
            session_id,
            frame_min=frame_min,
            frame_max=frame_max,
            event_type=event_type,
        )


class ResultDatabaseService:
    """结果数据库维护操作的应用层封装。"""

    def __init__(self, init_database: Callable[[str | Path], Path]) -> None:
        self._init_database = init_database

    def init_database(self, db_path: str | Path) -> Path:
        path = self._init_database(db_path)
        logger.info("结果数据库已初始化", extra={"result_db": str(path)})
        return path
