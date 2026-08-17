from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from genshin_sim.analysis.processors.comparison import (
    ComparisonQuery,
    ComparisonResult,
    build_comparison,
)
from genshin_sim.analysis.processors.metrics import (
    DamageMetrics,
    MetricsError,
    build_metrics,
)
from genshin_sim.analysis.processors.query import (
    EventQuery,
    EventQueryResult,
    StateQuery,
    StateQueryResult,
    query_events,
    query_state,
)
from genshin_sim.analysis.processors.sequences import (
    build_damage_sequence,
    build_healing_sequence,
)
from genshin_sim.analysis.processors.state_fold import FrameStateView, fold_state
from genshin_sim.application.execution.models import RecordedEvent
from genshin_sim.application.models import RunDetail, RunListItem
from genshin_sim.application.services.protocols import ResultRepository

logger = logging.getLogger(__name__)


class ResultsService:
    """读取已持久化的仿真运行。"""

    def __init__(self, repository: ResultRepository) -> None:
        self.repository = repository

    def list_runs(
        self,
        limit: int = 50,
        state: str | None = None,
    ) -> tuple[RunListItem, ...]:
        logger.debug("列出仿真结果", extra={"limit": limit, "state": state})
        return self.repository.list_runs(limit=limit, state=state)

    def inspect_run(self, session_id: str) -> RunDetail:
        logger.debug("查看仿真结果", extra={"session_id": session_id})
        return self.repository.get_run(session_id)

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

    def fold_state(self, session_id: str, frame: int) -> FrameStateView:
        """还原指定运行在指定帧的状态视图（analysis 读取侧加工）。"""

        logger.debug("还原运行状态", extra={"session_id": session_id, "frame": frame})
        run = self.repository.get_run(session_id)
        return fold_state(run.initial_snapshot, run.events, frame)

    def query_state(self, query: StateQuery) -> tuple[StateQueryResult, ...]:
        """按 StateQuery 查询状态数据。"""

        logger.debug("状态查询", extra={"sessions": query.session_ids, "frames": query.frames})
        return query_state(self.repository, query)

    def query_events(self, query: EventQuery) -> tuple[EventQueryResult, ...]:
        """按 EventQuery 查询事件数据。"""

        logger.debug("事件查询", extra={"session_id": query.session_id})
        return query_events(self.repository, query)

    def damage_metrics(self, session_id: str) -> DamageMetrics:
        """计算整场伤害/治疗摘要指标（analysis 读取侧加工）。"""

        logger.debug("计算整场指标", extra={"session_id": session_id})
        run = self.repository.get_run(session_id)
        if run.summary is None:
            raise MetricsError("运行缺少 summary，无法计算指标")
        damage_sequence = build_damage_sequence(run.events)
        healing_sequence = build_healing_sequence(run.events)
        return build_metrics(
            damage_sequence,
            healing_sequence,
            frames_run=run.summary.frames_run,
        )

    def compare(self, queries: tuple[ComparisonQuery, ...]) -> ComparisonResult:
        """执行多个查询并返回并置对比结果。"""

        logger.debug("对比查询", extra={"labels": [item.label for item in queries]})
        return build_comparison(self.repository, queries)


class ResultDatabaseService:
    """结果数据库维护操作的应用层封装。"""

    def __init__(self, init_database: Callable[[str | Path], Path]) -> None:
        self._init_database = init_database

    def init_database(self, db_path: str | Path) -> Path:
        path = self._init_database(db_path)
        logger.info("结果数据库已初始化", extra={"result_db": str(path)})
        return path
