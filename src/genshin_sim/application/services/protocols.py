from __future__ import annotations

from pathlib import Path
from typing import Protocol

from genshin_sim.application.config import SimulationConfig
from genshin_sim.application.services.models import (
    RunDetail,
    RunListItem,
)


class ResultRepository(Protocol):
    """读取已持久化的仿真运行。"""

    def list_runs(self, limit: int = 50) -> tuple[RunListItem, ...]: ...

    def get_run(self, session_id: str) -> RunDetail: ...


class ConfigValidator(Protocol):
    """加载并校验仿真配置。"""

    def validate_config(self, config: SimulationConfig) -> SimulationConfig: ...

    def validate_file(self, path: str | Path) -> SimulationConfig: ...
