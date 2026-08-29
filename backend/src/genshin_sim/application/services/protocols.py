from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from genshin_sim.application.config import ProjectConfig
from genshin_sim.application.execution.models import RecordedEvent
from genshin_sim.application.input import SimulationInput
from genshin_sim.application.models import (
    AnalysisPlan,
    AnalysisReadSchema,
    AnalysisTableResult,
    RunDetail,
    RunListItem,
)


class ResultRepository(Protocol):
    """读取已持久化的仿真运行。"""

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
    ) -> tuple[RunListItem, ...]: ...

    def get_run(self, session_id: str, *, include_events: bool = True) -> RunDetail: ...

    def get_events(
        self,
        session_id: str,
        frame_min: int | None = None,
        frame_max: int | None = None,
        event_type: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> tuple[RecordedEvent, ...]: ...

    def get_event(self, session_id: str, ordinal: int) -> RecordedEvent | None: ...

    def get_initial_snapshot(self, session_id: str) -> dict[str, Any] | None: ...

    def count_events(
        self,
        session_id: str,
        *,
        frame_min: int | None = None,
        frame_max: int | None = None,
        event_type: str | None = None,
    ) -> int: ...


class AnalysisQueryExecutor(Protocol):
    """结果库查询计划执行器的稳定读取协议。"""

    def execute_plan(self, plan: AnalysisPlan) -> Mapping[str, AnalysisTableResult]: ...

    def read_schema(self) -> AnalysisReadSchema: ...


class SimulationInputValidator(Protocol):
    """加载并校验模拟输入。"""

    def validate_input(self, config: SimulationInput) -> SimulationInput: ...

    def validate_file(self, path: str | Path) -> SimulationInput: ...


class ProjectConfigStore(Protocol):
    """项目配置（config.toml）的文件存储协议。"""

    def config_path(self, project_root: str | Path) -> Path: ...

    def template_path(self, project_root: str | Path) -> Path: ...

    def load(self, project_root: str | Path) -> ProjectConfig: ...

    def load_template(self, project_root: str | Path) -> ProjectConfig: ...

    def save(self, project_root: str | Path, config: ProjectConfig) -> Path: ...

    def create_default(self, project_root: str | Path) -> Path: ...


class ProjectTemplateProvider(Protocol):
    """未来从 GitHub 等来源获取配置模板；是否需要下载由交互端口征得用户同意。"""

    def provide(self, project_root: str | Path) -> Path | None: ...
