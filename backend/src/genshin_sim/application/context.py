"""Application 组装上下文与默认工厂。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

from genshin_sim.application.execution.protocols import ResultWriter
from genshin_sim.application.jobs import SimulationJobRunner
from genshin_sim.application.services.assets import (
    ManifestHandlerSyncer,
    ManifestHandlerUpdater,
    ManifestHandlerValidator,
)
from genshin_sim.application.services.protocols import (
    AnalysisTemplateExecutor,
    ProjectConfigStore,
    ResultRepository,
)
from genshin_sim.application.services.workflows import WorkflowStore
from genshin_sim.assets import AssetHandlerBindingRepository, AssetRepository
from genshin_sim.content.registries import ContentUnitRegistry
from genshin_sim.infrastructure.file_storage import WorkflowFileStore

if TYPE_CHECKING:
    from genshin_sim.application.facade import ApplicationFacade


@dataclass(frozen=True, slots=True)
class ApplicationContext:
    """一次 application 实例的内部依赖集合。"""

    project_root: Path
    config_store: ProjectConfigStore
    asset_repository: AssetRepository
    asset_db_path: Path
    result_repository: ResultRepository
    result_writer: ResultWriter
    job_runner: SimulationJobRunner
    analysis_template_executor: AnalysisTemplateExecutor | None = None
    asset_handler_repository: AssetHandlerBindingRepository | None = None
    content_unit_registry: ContentUnitRegistry | None = None
    init_result_database: Callable[[str | Path], Path] | None = None
    init_asset_database: Callable[[str | Path], Path] | None = None
    write_minimal_static_asset_database: Callable[[str | Path], Path] | None = None
    build_asset_database_from_manifest: Callable[[str | Path, str | Path], Path] | None = None
    validate_asset_database: Callable[[str | Path], None] | None = None
    fetch_asset_source_cache: Callable[..., Any] | None = None
    build_asset_manifest: Callable[[str | Path, str | Path], Any] | None = None
    audit_asset_manifest: Callable[[str | Path], Any] | None = None
    rebuild_asset_database_from_source: Callable[[str | Path], Path] | None = None
    manifest_validator: ManifestHandlerValidator | None = None
    manifest_updater: ManifestHandlerUpdater | None = None
    manifest_syncer: ManifestHandlerSyncer | None = None
    workflow_store: WorkflowStore | None = None


def resolve_workspace_data_dir(
    config_store: ProjectConfigStore,
    project_root: str | Path,
) -> Path:
    """解析当前生效的工作区数据目录；配置缺失时回落 root/data。"""

    config_path = config_store.config_path(project_root)
    config = config_store.load(project_root) if config_path.is_file() else None
    return config.data_dir(project_root) if config is not None else Path(project_root) / "data"


def create_application(
    *,
    project_root: str | Path,
    config_store: ProjectConfigStore,
    asset_repository: AssetRepository,
    asset_db_path: str | Path,
    result_repository: ResultRepository,
    result_writer: ResultWriter,
    job_runner: SimulationJobRunner | None = None,
    analysis_template_executor: AnalysisTemplateExecutor | None = None,
    content_unit_registry: ContentUnitRegistry | None = None,
    workflow_store: WorkflowStore | None = None,
) -> ApplicationFacade:
    """组装产品版 ApplicationContext 并返回公开 facade。"""
    from genshin_sim.application.facade import DefaultApplicationFacade

    runner = job_runner
    if runner is None:
        from genshin_sim.infrastructure.jobs import ProcessSimulationJobRunner

        runner = ProcessSimulationJobRunner(
            asset_db_path=asset_db_path,
            result_db_path=result_writer.db_path,
            max_workers=1,
        )
    executor = analysis_template_executor
    if executor is None:
        from genshin_sim.infrastructure.results_sqlite.templates import (
            SQLiteAnalysisTemplateExecutor,
        )

        executor = SQLiteAnalysisTemplateExecutor(result_writer.db_path)

    root = Path(project_root)
    # 配置是工作流存档路径的前置条件：组装时先解析一次，之后每次操作再按当前配置解析。
    resolve_workspace_data_dir(config_store, root)
    context = ApplicationContext(
        project_root=root,
        config_store=config_store,
        asset_repository=asset_repository,
        asset_db_path=Path(asset_db_path),
        result_repository=result_repository,
        result_writer=result_writer,
        job_runner=runner,
        analysis_template_executor=executor,
        content_unit_registry=content_unit_registry,
        workflow_store=(
            workflow_store
            or WorkflowFileStore(partial(resolve_workspace_data_dir, config_store, root))
        ),
    )
    return DefaultApplicationFacade(context)
