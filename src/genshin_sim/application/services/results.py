from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from genshin_sim.application.services.models import RunDetail, RunListItem
from genshin_sim.application.services.protocols import ResultRepository

logger = logging.getLogger(__name__)


class ResultsService:
    """读取已持久化的仿真运行。"""

    def __init__(self, repository: ResultRepository) -> None:
        self.repository = repository

    def list_runs(self, limit: int = 50) -> tuple[RunListItem, ...]:
        logger.debug("列出仿真结果", extra={"limit": limit})
        return self.repository.list_runs(limit=limit)

    def inspect_run(self, session_id: str) -> RunDetail:
        logger.debug("查看仿真结果", extra={"session_id": session_id})
        return self.repository.get_run(session_id)


class ResultDatabaseService:
    """结果数据库维护操作的应用层封装。"""

    def __init__(self, init_database: Callable[[str | Path], Path]) -> None:
        self._init_database = init_database

    def init_database(self, db_path: str | Path) -> Path:
        path = self._init_database(db_path)
        logger.info("结果数据库已初始化", extra={"result_db": str(path)})
        return path
