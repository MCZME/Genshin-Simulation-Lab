from __future__ import annotations

from pathlib import Path
from typing import Protocol

from genshin_sim.application.config import ProjectConfig
from genshin_sim.application.execution.models import RecordedEvent
from genshin_sim.application.input import SimulationInput
from genshin_sim.application.services.models import (
    RunDetail,
    RunListItem,
)


class ResultRepository(Protocol):
    """读取已持久化的仿真运行。"""

    def list_runs(
        self,
        limit: int = 50,
        state: str | None = None,
    ) -> tuple[RunListItem, ...]: ...

    def get_run(self, session_id: str) -> RunDetail: ...

    def get_events(
        self,
        session_id: str,
        frame_min: int | None = None,
        frame_max: int | None = None,
        event_type: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> tuple[RecordedEvent, ...]: ...


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
