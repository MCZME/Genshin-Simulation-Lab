from __future__ import annotations

import enum
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from genshin_sim.application.config import ProjectConfig
from genshin_sim.application.errors import ConfigFileError
from genshin_sim.application.services.protocols import (
    ProjectConfigStore,
    ProjectTemplateProvider,
)

logger = logging.getLogger(__name__)


class AssetInitializationStrategy(enum.Enum):
    """资产库初始化方式。"""

    FETCH_SOURCE = "fetch_source"
    FROM_MANIFEST = "from_manifest"


@dataclass(frozen=True, slots=True)
class AssetInitializationPlan:
    """用户选择的资产库初始化计划。"""

    strategy: AssetInitializationStrategy
    manifest_path: Path | None = None


class AssetInitializationSelector(Protocol):
    """资产库初始化方式的交互端口；CLI 用命令行提示，UI 用弹窗实现。"""

    def select(self) -> AssetInitializationPlan: ...


@dataclass(frozen=True, slots=True)
class ProjectInitializationResult:
    """一次项目初始化的产物与选择结果。"""

    project_root: Path
    config_path: Path
    data_dir: Path
    workspace_dirs: tuple[Path, ...]
    result_db_path: Path
    asset_db_path: Path
    asset_plan: AssetInitializationPlan
    warnings: tuple[str, ...] = ()


class ProjectInitializationService:
    """编排项目初始化：配置、工作区目录、结果库与资产库。"""

    def __init__(
        self,
        config_store: ProjectConfigStore,
        init_result_database: Callable[[str | Path], Path],
        build_from_manifest: Callable[[str | Path, str | Path], Path],
        rebuild_from_source: Callable[[str | Path], Path],
        asset_selector: AssetInitializationSelector,
        template_provider: ProjectTemplateProvider | None = None,
    ) -> None:
        self.config_store = config_store
        self.init_result_database = init_result_database
        self.build_from_manifest = build_from_manifest
        self.rebuild_from_source = rebuild_from_source
        self.asset_selector = asset_selector
        self.template_provider = template_provider

    def initialize(
        self,
        project_root: str | Path,
        *,
        asset_db_path: str | Path,
    ) -> ProjectInitializationResult:
        root = Path(project_root)
        warnings: list[str] = []

        template_path = self.config_store.template_path(root)
        if not template_path.exists():
            warnings.append(f"缺少配置模板：{template_path}")
            if self.template_provider is not None:
                provided = self.template_provider.provide(root)
                if provided is not None:
                    template_path = self.config_store.template_path(root)

        config_path = self.config_store.config_path(root)
        if config_path.exists():
            config = self.config_store.load(root)
        elif template_path.exists():
            self._validate_template(root)
            self.config_store.create_default(root)
            config = self.config_store.load(root)
        else:
            raise ConfigFileError(
                "无法初始化项目：缺少 config.toml 且缺少配置模板（config.example.toml）。"
                "未来可提供 GitHub 模板下载，当前请先放置模板或配置文件。"
            )

        workspace_dirs = (
            config.inputs_dir(root),
            config.results_dir(root),
            config.exports_dir(root),
            config.templates_dir(root),
            config.logs_dir(root),
        )
        for path in workspace_dirs:
            path.mkdir(parents=True, exist_ok=True)

        result_db_path = config.results_db(root)
        self.init_result_database(result_db_path)

        asset_db = Path(asset_db_path)
        asset_db.parent.mkdir(parents=True, exist_ok=True)
        asset_plan = self.asset_selector.select()
        if asset_plan.strategy is AssetInitializationStrategy.FETCH_SOURCE:
            self.rebuild_from_source(asset_db)
        elif asset_plan.strategy is AssetInitializationStrategy.FROM_MANIFEST:
            if asset_plan.manifest_path is None:
                raise ValueError("从 manifest 构建资产库时必须提供 manifest 路径")
            self.build_from_manifest(asset_db, asset_plan.manifest_path)
        else:
            raise ValueError(f"不支持的资产库初始化方式：{asset_plan.strategy}")

        logger.info(
            "项目初始化完成",
            extra={
                "project_root": str(root),
                "config_path": str(config_path),
                "result_db": str(result_db_path),
                "asset_db": str(asset_db),
            },
        )
        for warning in warnings:
            logger.warning(warning)

        return ProjectInitializationResult(
            project_root=root,
            config_path=config_path,
            data_dir=config.data_dir(root),
            workspace_dirs=workspace_dirs,
            result_db_path=result_db_path,
            asset_db_path=asset_db,
            asset_plan=asset_plan,
            warnings=tuple(warnings),
        )

    def _validate_template(self, project_root: str | Path) -> ProjectConfig:
        return self.config_store.load_template(project_root)
