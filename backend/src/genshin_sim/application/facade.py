"""Python 后端公开能力出口与默认实现。

入口层只依赖本模块导出的协议和公开模型，不直接接触 service、
repository 或 infrastructure。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from genshin_sim.application.services.assets import AssetsService
from genshin_sim.application.services.project import ProjectService
from genshin_sim.application.services.protocols import ProjectConfigStore
from genshin_sim.assets import AssetRepository


@dataclass(frozen=True, slots=True)
class WorkspaceInfo:
    """工作区公开视图。"""

    data_dir: str
    asset_db_version: str
    initialized: bool


class ApplicationFacade(Protocol):
    """server 与 cli 共用的 Python 后端公开能力出口。"""

    def get_workspace(self) -> WorkspaceInfo: ...


class DefaultApplicationFacade:
    """基于现有应用服务的默认 facade 实现。"""

    def __init__(
        self,
        *,
        project_root: str | Path,
        config_store: ProjectConfigStore,
        asset_repository: AssetRepository,
        asset_db_path: str | Path,
    ) -> None:
        self._project_root = Path(project_root)
        self._config_store = config_store
        self._asset_repository = asset_repository
        self._asset_db_path = Path(asset_db_path)

    def get_workspace(self) -> WorkspaceInfo:
        config_path = self._config_store.config_path(self._project_root)
        if not config_path.is_file():
            return WorkspaceInfo(
                data_dir=str(self._project_root / "data"),
                asset_db_version="",
                initialized=False,
            )

        config = ProjectService(self._config_store).load_project(self._project_root)
        data_dir = str(config.data_dir(self._project_root))
        if not self._asset_db_path.is_file():
            return WorkspaceInfo(
                data_dir=data_dir,
                asset_db_version="",
                initialized=False,
            )

        info = AssetsService(self._asset_repository).get_info()
        return WorkspaceInfo(
            data_dir=data_dir,
            asset_db_version=info.meta.get("data_version", ""),
            initialized=True,
        )
