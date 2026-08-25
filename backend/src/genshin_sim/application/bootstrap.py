"""CLI 入口使用的 application 装配。

具体基础设施适配集中在这里，入口层只需要调用 create_cli_application 并消费 facade。
"""

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

from genshin_sim.application.context import ApplicationContext, resolve_workspace_data_dir
from genshin_sim.content import create_default_content_unit_registry
from genshin_sim.infrastructure.assets_project_amber import (
    build_asset_manifest_from_project_amber_cache,
    fetch_project_amber_source_cache,
)
from genshin_sim.infrastructure.assets_sqlite import (
    SQLiteAssetRepository,
    apply_handler_binding_to_manifest,
    audit_asset_manifest,
    build_asset_database_from_manifest,
    init_asset_database,
    sync_asset_manifest_handler_bindings,
    validate_asset_database,
    validate_handler_binding_in_manifest,
    write_minimal_static_asset_database,
)
from genshin_sim.infrastructure.file_storage import ProjectConfigFileStore, WorkflowFileStore
from genshin_sim.infrastructure.results_sqlite import (
    SQLiteResultRepository,
    SQLiteResultWriter,
    init_result_database,
)
from genshin_sim.infrastructure.results_sqlite.analysis_query import (
    SQLiteAnalysisQueryExecutor,
)

if TYPE_CHECKING:
    from genshin_sim.application.facade import ApplicationFacade

DEFAULT_ASSET_DB = Path("data") / "assets" / "assets.db"
DEFAULT_ASSET_MANIFEST = Path("data") / "assets" / "manifests" / "project_amber_yatta.json"
DEFAULT_ASSET_SOURCE_CACHE = Path("data") / "assets" / "sources" / "project_amber_yatta" / "default"


def create_cli_application(
    *,
    project_root: str | Path,
    asset_db_path: str | Path | None = None,
    result_db_path: str | Path | None = None,
    source_cache_dir: str | Path | None = None,
    asset_manifest_path: str | Path | None = None,
) -> ApplicationFacade:
    """组装 CLI 可用的完整 application facade。"""
    from genshin_sim.application.batch import MAX_BATCH_CONCURRENCY
    from genshin_sim.application.facade import DefaultApplicationFacade
    from genshin_sim.infrastructure.jobs import ProcessSimulationJobRunner

    root = Path(project_root)
    config_store = ProjectConfigFileStore()
    asset_db = Path(asset_db_path) if asset_db_path is not None else root / DEFAULT_ASSET_DB
    config_path = config_store.config_path(root)
    config = config_store.load(root) if config_path.is_file() else None
    if result_db_path is None:
        if config is not None:
            result_db = config.results_db(root)
        else:
            result_db = root / "data" / "results" / "results.db"
    else:
        result_db = Path(result_db_path)

    source_cache = (
        Path(source_cache_dir)
        if source_cache_dir is not None
        else root / DEFAULT_ASSET_SOURCE_CACHE
    )
    manifest_path = (
        Path(asset_manifest_path)
        if asset_manifest_path is not None
        else root / DEFAULT_ASSET_MANIFEST
    )

    runner = ProcessSimulationJobRunner(
        asset_db_path=asset_db,
        result_db_path=result_db,
        # 执行后端容量覆盖批调度允许的上限；批服务是唯一队列。
        max_workers=MAX_BATCH_CONCURRENCY,
    )

    asset_repository = SQLiteAssetRepository(asset_db)
    result_repository = SQLiteResultRepository(result_db)
    result_writer = SQLiteResultWriter(result_db)

    def rebuild_asset_database_from_source(db_path: str | Path) -> Path:
        fetch_project_amber_source_cache(source_cache)
        summary = build_asset_manifest_from_project_amber_cache(source_cache, manifest_path)
        return build_asset_database_from_manifest(db_path, summary.output_path)

    context = ApplicationContext(
        project_root=root,
        config_store=config_store,
        asset_repository=asset_repository,
        asset_db_path=asset_db,
        result_repository=result_repository,
        result_writer=result_writer,
        job_runner=runner,
        analysis_query_executor=SQLiteAnalysisQueryExecutor(result_db),
        asset_handler_repository=asset_repository,
        content_unit_registry=create_default_content_unit_registry(),
        init_result_database=init_result_database,
        init_asset_database=init_asset_database,
        write_minimal_static_asset_database=write_minimal_static_asset_database,
        build_asset_database_from_manifest=build_asset_database_from_manifest,
        validate_asset_database=validate_asset_database,
        fetch_asset_source_cache=fetch_project_amber_source_cache,
        build_asset_manifest=build_asset_manifest_from_project_amber_cache,
        audit_asset_manifest=audit_asset_manifest,
        rebuild_asset_database_from_source=rebuild_asset_database_from_source,
        manifest_validator=validate_handler_binding_in_manifest,
        manifest_updater=apply_handler_binding_to_manifest,
        manifest_syncer=sync_asset_manifest_handler_bindings,
        workflow_store=WorkflowFileStore(partial(resolve_workspace_data_dir, config_store, root)),
    )
    return DefaultApplicationFacade(context)


def create_server_application(
    *,
    project_root: str | Path,
    asset_db_path: str | Path | None = None,
    result_db_path: str | Path | None = None,
    source_cache_dir: str | Path | None = None,
    asset_manifest_path: str | Path | None = None,
) -> ApplicationFacade:
    """组装 server 可用的完整 application facade。"""

    return create_cli_application(
        project_root=project_root,
        asset_db_path=asset_db_path,
        result_db_path=result_db_path,
        source_cache_dir=source_cache_dir,
        asset_manifest_path=asset_manifest_path,
    )
