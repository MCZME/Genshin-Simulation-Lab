"""Application 组装上下文与默认工厂。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from genshin_sim.application.execution import SynchronousSimulationExecutor
from genshin_sim.application.execution.protocols import ResultWriter
from genshin_sim.application.jobs import InMemorySimulationJobRunner, SimulationJobRunner
from genshin_sim.application.services.assets import (
    ManifestHandlerSyncer,
    ManifestHandlerUpdater,
    ManifestHandlerValidator,
)
from genshin_sim.application.services.protocols import ProjectConfigStore, ResultRepository
from genshin_sim.assets import AssetHandlerBindingRepository, AssetRepository
from genshin_sim.content.registries import ContentUnitRegistry

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


def create_application(
    *,
    project_root: str | Path,
    config_store: ProjectConfigStore,
    asset_repository: AssetRepository,
    asset_db_path: str | Path,
    result_repository: ResultRepository,
    result_writer: ResultWriter,
    job_runner: SimulationJobRunner | None = None,
    content_unit_registry: ContentUnitRegistry | None = None,
) -> ApplicationFacade:
    """组装产品版 ApplicationContext 并返回公开 facade。"""
    from genshin_sim.application.facade import DefaultApplicationFacade

    runner = job_runner
    if runner is None:
        executor = SynchronousSimulationExecutor.create(asset_repository, result_writer)
        runner = InMemorySimulationJobRunner(executor)

    context = ApplicationContext(
        project_root=Path(project_root),
        config_store=config_store,
        asset_repository=asset_repository,
        asset_db_path=Path(asset_db_path),
        result_repository=result_repository,
        result_writer=result_writer,
        job_runner=runner,
        content_unit_registry=content_unit_registry,
    )
    return DefaultApplicationFacade(context)
