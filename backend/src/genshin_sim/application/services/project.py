from __future__ import annotations

import logging
from pathlib import Path

from genshin_sim.application.config import ProjectConfig
from genshin_sim.application.services.protocols import ProjectConfigStore

logger = logging.getLogger(__name__)


class ProjectService:
    """项目配置的对外用例服务。"""

    def __init__(self, store: ProjectConfigStore) -> None:
        self.store = store

    def load_project(self, project_root: str | Path) -> ProjectConfig:
        logger.debug("加载项目配置", extra={"project_root": str(project_root)})
        return self.store.load(project_root)

    def workspace_paths(self, project_root: str | Path) -> dict[str, Path]:
        config = self.load_project(project_root)
        return {
            "inputs": config.inputs_dir(project_root),
            "results": config.results_dir(project_root),
            "results_db": config.results_db(project_root),
            "logs": config.logs_dir(project_root),
            "exports": config.exports_dir(project_root),
            "templates": config.templates_dir(project_root),
        }
