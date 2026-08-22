"""Python 后端公开能力出口与默认实现。

入口层只依赖本模块导出的协议和公开模型，不直接接触 service、
repository 或 infrastructure。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, Protocol

from genshin_sim.analysis.processors.metrics import DamageMetrics, MetricsError
from genshin_sim.application.batch import (
    BatchMember,
    BatchRunService,
    BatchRunStatus,
    BatchValidationResult,
    SingleBatchResult,
)
from genshin_sim.application.config import ProjectConfig, UiConfig
from genshin_sim.application.context import ApplicationContext
from genshin_sim.application.errors import ApplicationError
from genshin_sim.application.input import SimulationInput
from genshin_sim.application.models import (
    AssetListItem,
    AssetListKind,
    RecordedEvent,
    RunDetail,
    RunListItem,
    SimulationInputFile,
    WorkspaceInfo,
)
from genshin_sim.application.services.assets import (
    AssetDatabaseService,
    AssetHandlerBindingService,
    AssetManifestAuditService,
    AssetManifestBuildService,
    AssetsService,
    HandlerBindingKind,
)
from genshin_sim.application.services.input_validation import (
    BatchInputValidationService,
    InputValidationService,
)
from genshin_sim.application.services.inputs import InputDiscoveryService
from genshin_sim.application.services.project import ProjectService
from genshin_sim.application.services.project_initialization import (
    AssetInitializationSelector,
    ProjectInitializationResult,
    ProjectInitializationService,
)
from genshin_sim.application.services.results import ResultDatabaseService, ResultsService
from genshin_sim.application.services.workflows import (
    DEFAULT_WORKFLOW_NAME,
    WorkflowDetail,
    WorkflowService,
    WorkflowSummary,
)
from genshin_sim.assets import AssetDbInfo, HandlerBinding
from genshin_sim.content import create_default_content_unit_registry


class ApplicationFacade(Protocol):
    """server 与 cli 共用的 Python 后端公开能力出口。"""

    def get_workspace(self) -> WorkspaceInfo: ...

    def get_asset_db_info(self) -> AssetDbInfo: ...

    def list_assets(
        self,
        kind: AssetListKind | str,
        *,
        q: str | None = None,
        element: str | None = None,
        weapon_type: str | None = None,
        rarity: int | None = None,
        usable: bool | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[AssetListItem, ...]: ...

    def get_asset(self, kind: AssetListKind | str, source_id: str) -> AssetListItem: ...

    def inspect_asset(self, asset_key: str) -> dict[str, Any]: ...

    def init_asset_database(self, path: str | Path) -> Path: ...

    def build_asset_database(
        self,
        path: str | Path,
        manifest_path: str | Path | None = None,
    ) -> Path: ...

    def validate_asset_database(self, path: str | Path) -> None: ...

    def fetch_asset_source(
        self,
        output_dir: str | Path,
        *,
        source: str = "project-amber-yatta",
        character_ids: Sequence[str] = (),
        weapon_ids: Sequence[str] = (),
        artifact_set_ids: Sequence[str] = (),
        include_all_details: bool = False,
    ) -> Any: ...

    def build_asset_manifest(
        self,
        source_cache_dir: str | Path,
        output_path: str | Path,
    ) -> Any: ...

    def audit_asset_manifest(self, path: str | Path) -> Any: ...

    def set_asset_handler(
        self,
        kind: HandlerBindingKind | str,
        key: str,
        handler_key: str,
        pieces: int | None = None,
        *,
        manifest_paths: Sequence[str | Path] = (),
    ) -> HandlerBinding: ...

    def reset_asset_handler(
        self,
        kind: HandlerBindingKind | str,
        key: str,
        pieces: int | None = None,
        *,
        manifest_paths: Sequence[str | Path] = (),
    ) -> HandlerBinding: ...

    def list_asset_handlers(
        self,
        kind: str,
        owner_key: str | None = None,
    ) -> tuple[HandlerBinding, ...]: ...

    def sync_asset_handlers(
        self,
        manifest_paths: Sequence[str | Path],
        kind: str | None = None,
    ) -> dict[str, int]: ...

    def list_inputs(self) -> tuple[SimulationInputFile, ...]: ...

    def validate_input_file(self, path: str | Path) -> SimulationInput: ...

    def initialize_project(
        self,
        project_root: str | Path,
        *,
        asset_db_path: str | Path,
        selector: AssetInitializationSelector,
    ) -> ProjectInitializationResult: ...

    def load_project(self, project_root: str | Path) -> ProjectConfig: ...

    def workspace_paths(self, project_root: str | Path) -> dict[str, Path]: ...

    def validate_batch_inputs(
        self,
        members: Sequence[BatchMember],
    ) -> BatchValidationResult: ...

    def submit_batch(
        self,
        members: Sequence[BatchMember],
        *,
        name: str = "",
        concurrency: int | None = None,
    ) -> BatchRunStatus: ...

    def get_batch(self, run_id: str) -> BatchRunStatus: ...

    def cancel_batch(self, run_id: str) -> BatchRunStatus: ...

    def run_file_and_wait(
        self,
        path: str | Path,
        *,
        poll_interval_seconds: float = 0.05,
        timeout_seconds: float | None = None,
    ) -> SingleBatchResult: ...

    def run_input_and_wait(
        self,
        config: SimulationInput,
        *,
        poll_interval_seconds: float = 0.05,
        timeout_seconds: float | None = None,
    ) -> SingleBatchResult: ...

    def init_result_database(self, path: str | Path) -> Path: ...

    def list_results(
        self,
        limit: int = 50,
        offset: int = 0,
        state: str | None = None,
    ) -> tuple[RunListItem, ...]: ...

    def get_run(self, session_id: str, *, include_events: bool = True) -> RunDetail: ...

    def count_run_events(
        self,
        session_id: str,
        *,
        frame_min: int | None = None,
        frame_max: int | None = None,
        event_type: str | None = None,
    ) -> int: ...

    def get_run_events(
        self,
        session_id: str,
        *,
        frame_min: int | None = None,
        frame_max: int | None = None,
        event_type: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> tuple[RecordedEvent, ...]: ...

    def damage_metrics(self, session_id: str) -> DamageMetrics: ...

    def create_workflow(self, name: str = DEFAULT_WORKFLOW_NAME) -> WorkflowDetail: ...

    def list_workflows(self) -> tuple[WorkflowSummary, ...]: ...

    def get_workflow(self, workflow_id: str) -> WorkflowDetail: ...

    def save_workflow(
        self,
        workflow_id: str,
        definition: Mapping[str, Any],
    ) -> WorkflowDetail: ...

    def delete_workflow(self, workflow_id: str) -> None: ...

    def get_ui_settings(self) -> UiConfig: ...

    def save_ui_settings(self, *, run_animation: bool) -> UiConfig: ...


class DefaultApplicationFacade:
    """基于现有应用服务的默认 facade 实现。"""

    def __init__(self, context: ApplicationContext) -> None:
        self._context = context
        content_unit_registry = (
            context.content_unit_registry or create_default_content_unit_registry()
        )
        self._project_service = ProjectService(context.config_store)
        self._assets_service = AssetsService(
            context.asset_repository,
            content_unit_registry=content_unit_registry,
        )
        self._inputs_service = InputDiscoveryService(context.config_store)
        self._input_validation_service = InputValidationService()
        self._results_service = ResultsService(context.result_repository)
        self._batch_service = BatchRunService(
            context.job_runner,
            validator=BatchInputValidationService(
                context.asset_repository,
                content_unit_registry=content_unit_registry,
            ),
        )
        self._workflow_service = (
            WorkflowService(context.workflow_store) if context.workflow_store is not None else None
        )

    def get_workspace(self) -> WorkspaceInfo:
        config_path = self._context.config_store.config_path(self._context.project_root)
        if not config_path.is_file():
            return WorkspaceInfo(
                data_dir=str(self._context.project_root / "data"),
                asset_db_version="",
                initialized=False,
            )

        config = self._project_service.load_project(self._context.project_root)
        data_dir = str(config.data_dir(self._context.project_root))
        if not self._context.asset_db_path.is_file():
            return WorkspaceInfo(
                data_dir=data_dir,
                asset_db_version="",
                initialized=False,
            )

        info = self._assets_service.get_info()
        return WorkspaceInfo(
            data_dir=data_dir,
            asset_db_version=info.meta.get("data_version", ""),
            initialized=True,
        )

    def get_asset_db_info(self) -> AssetDbInfo:
        return self._assets_service.get_info()

    def list_assets(
        self,
        kind: AssetListKind | str,
        *,
        q: str | None = None,
        element: str | None = None,
        weapon_type: str | None = None,
        rarity: int | None = None,
        usable: bool | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[AssetListItem, ...]:
        try:
            return self._assets_service.list_assets(
                kind,
                q=q,
                element=element,
                weapon_type=weapon_type,
                rarity=rarity,
                usable=usable,
                limit=limit,
                offset=offset,
            )
        except ValueError as exc:
            raise ApplicationError("not_found", f"未知资产类型：{kind}") from exc

    def get_asset(self, kind: AssetListKind | str, source_id: str) -> AssetListItem:
        try:
            return self._assets_service.get_asset(kind, source_id)
        except (KeyError, LookupError, ValueError) as exc:
            raise ApplicationError(
                "not_found",
                f"资产不存在：{kind}/{source_id}",
            ) from exc

    def inspect_asset(self, asset_key: str) -> dict[str, Any]:
        return self._assets_service.inspect_asset_dict(asset_key)

    def init_asset_database(self, path: str | Path) -> Path:
        return self._asset_database_service().init_database(path)

    def build_asset_database(
        self,
        path: str | Path,
        manifest_path: str | Path | None = None,
    ) -> Path:
        return self._asset_database_service(manifest_path=manifest_path).build_database(path)

    def validate_asset_database(self, path: str | Path) -> None:
        self._asset_database_service().validate_database(path)

    def fetch_asset_source(
        self,
        output_dir: str | Path,
        *,
        source: str = "project-amber-yatta",
        character_ids: Sequence[str] = (),
        weapon_ids: Sequence[str] = (),
        artifact_set_ids: Sequence[str] = (),
        include_all_details: bool = False,
    ) -> Any:
        callback = self._context.fetch_asset_source_cache
        if callback is None:
            raise ApplicationError("admin_service_unavailable", "资产源抓取能力未配置")
        if source != "project-amber-yatta":
            raise ValueError(f"不支持的资产源：{source}")
        return callback(
            output_dir,
            character_ids=tuple(character_ids),
            weapon_ids=tuple(weapon_ids),
            artifact_set_ids=tuple(artifact_set_ids),
            include_all_details=include_all_details,
        )

    def build_asset_manifest(
        self,
        source_cache_dir: str | Path,
        output_path: str | Path,
    ) -> Any:
        callback = self._context.build_asset_manifest
        if callback is None:
            raise ApplicationError("admin_service_unavailable", "资产 manifest 构建能力未配置")
        return AssetManifestBuildService(build_manifest=callback).build_manifest(
            source_cache_dir,
            output_path,
        )

    def audit_asset_manifest(self, path: str | Path) -> Any:
        callback = self._context.audit_asset_manifest
        if callback is None:
            raise ApplicationError("admin_service_unavailable", "资产 manifest 验收能力未配置")
        return AssetManifestAuditService(audit_manifest=callback).audit_manifest(path)

    def set_asset_handler(
        self,
        kind: HandlerBindingKind | str,
        key: str,
        handler_key: str,
        pieces: int | None = None,
        *,
        manifest_paths: Sequence[str | Path] = (),
    ) -> HandlerBinding:
        return self._asset_handler_service().set_handler(
            kind,
            key,
            handler_key,
            pieces,
            manifest_paths=manifest_paths,
        )

    def reset_asset_handler(
        self,
        kind: HandlerBindingKind | str,
        key: str,
        pieces: int | None = None,
        *,
        manifest_paths: Sequence[str | Path] = (),
    ) -> HandlerBinding:
        return self._asset_handler_service().reset_handler(
            kind,
            key,
            pieces,
            manifest_paths=manifest_paths,
        )

    def list_asset_handlers(
        self,
        kind: str,
        owner_key: str | None = None,
    ) -> tuple[HandlerBinding, ...]:
        return self._asset_handler_service().show_handlers(kind, owner_key)

    def sync_asset_handlers(
        self,
        manifest_paths: Sequence[str | Path],
        kind: str | None = None,
    ) -> dict[str, int]:
        return self._asset_handler_service().sync_handlers_to_manifests(
            manifest_paths,
            kind=kind,
        )

    def list_inputs(self) -> tuple[SimulationInputFile, ...]:
        return self._inputs_service.list_inputs(self._context.project_root)

    def validate_input_file(self, path: str | Path) -> SimulationInput:
        return self._input_validation_service.validate_file(path)

    def initialize_project(
        self,
        project_root: str | Path,
        *,
        asset_db_path: str | Path,
        selector: AssetInitializationSelector,
    ) -> ProjectInitializationResult:
        if (
            self._context.init_result_database is None
            or self._context.build_asset_database_from_manifest is None
            or self._context.rebuild_asset_database_from_source is None
        ):
            raise ApplicationError("admin_service_unavailable", "项目初始化能力未配置")
        service = ProjectInitializationService(
            config_store=self._context.config_store,
            init_result_database=self._context.init_result_database,
            build_from_manifest=self._context.build_asset_database_from_manifest,
            rebuild_from_source=self._context.rebuild_asset_database_from_source,
            asset_selector=selector,
        )
        return service.initialize(project_root, asset_db_path=asset_db_path)

    def load_project(self, project_root: str | Path) -> ProjectConfig:
        return self._project_service.load_project(project_root)

    def workspace_paths(self, project_root: str | Path) -> dict[str, Path]:
        return self._project_service.workspace_paths(project_root)

    def validate_batch_inputs(
        self,
        members: Sequence[BatchMember],
    ) -> BatchValidationResult:
        return self._batch_service.validate_members(members)

    def submit_batch(
        self,
        members: Sequence[BatchMember],
        *,
        name: str = "",
        concurrency: int | None = None,
    ) -> BatchRunStatus:
        return self._batch_service.submit(
            members,
            name=name,
            concurrency=concurrency,
        )

    def get_batch(self, run_id: str) -> BatchRunStatus:
        return self._batch_service.get(run_id)

    def cancel_batch(self, run_id: str) -> BatchRunStatus:
        return self._batch_service.cancel(run_id)

    def run_file_and_wait(
        self,
        path: str | Path,
        *,
        poll_interval_seconds: float = 0.05,
        timeout_seconds: float | None = None,
    ) -> SingleBatchResult:
        config = self.validate_input_file(path)
        return self._batch_service.run_single_and_wait(
            BatchMember(item_id="single", input=config),
            poll_interval_seconds=poll_interval_seconds,
            timeout_seconds=timeout_seconds,
        )

    def run_input_and_wait(
        self,
        config: SimulationInput,
        *,
        poll_interval_seconds: float = 0.05,
        timeout_seconds: float | None = None,
    ) -> SingleBatchResult:
        return self._batch_service.run_single_and_wait(
            BatchMember(item_id="single", input=config),
            poll_interval_seconds=poll_interval_seconds,
            timeout_seconds=timeout_seconds,
        )

    def init_result_database(self, path: str | Path) -> Path:
        callback = self._context.init_result_database
        if callback is None:
            raise ApplicationError("admin_service_unavailable", "结果库初始化能力未配置")
        return ResultDatabaseService(callback).init_database(path)

    def list_results(
        self,
        limit: int = 50,
        offset: int = 0,
        state: str | None = None,
    ) -> tuple[RunListItem, ...]:
        return self._results_service.list_runs(limit=limit, offset=offset, state=state)

    def get_run(self, session_id: str, *, include_events: bool = True) -> RunDetail:
        try:
            return self._results_service.inspect_run(
                session_id,
                include_events=include_events,
            )
        except LookupError as exc:
            raise _result_not_found(session_id) from exc

    def count_run_events(
        self,
        session_id: str,
        *,
        frame_min: int | None = None,
        frame_max: int | None = None,
        event_type: str | None = None,
    ) -> int:
        try:
            return self._results_service.count_events(
                session_id,
                frame_min=frame_min,
                frame_max=frame_max,
                event_type=event_type,
            )
        except LookupError as exc:
            raise _result_not_found(session_id) from exc

    def get_run_events(
        self,
        session_id: str,
        *,
        frame_min: int | None = None,
        frame_max: int | None = None,
        event_type: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> tuple[RecordedEvent, ...]:
        try:
            return self._results_service.get_events(
                session_id,
                frame_min=frame_min,
                frame_max=frame_max,
                event_type=event_type,
                offset=offset,
                limit=limit,
            )
        except LookupError as exc:
            raise _result_not_found(session_id) from exc

    def damage_metrics(self, session_id: str) -> DamageMetrics:
        try:
            return self._results_service.damage_metrics(session_id)
        except KeyError:
            raise
        except LookupError as exc:
            raise _result_not_found(session_id) from exc
        except MetricsError as exc:
            raise ApplicationError(
                "metrics_unavailable",
                "运行结果尚无法计算摘要指标",
            ) from exc

    def create_workflow(self, name: str = DEFAULT_WORKFLOW_NAME) -> WorkflowDetail:
        return self._require_workflow_service().create(name)

    def list_workflows(self) -> tuple[WorkflowSummary, ...]:
        return self._require_workflow_service().list()

    def get_workflow(self, workflow_id: str) -> WorkflowDetail:
        return self._require_workflow_service().get(workflow_id)

    def save_workflow(
        self,
        workflow_id: str,
        definition: Mapping[str, Any],
    ) -> WorkflowDetail:
        return self._require_workflow_service().save(workflow_id, definition)

    def delete_workflow(self, workflow_id: str) -> None:
        self._require_workflow_service().delete(workflow_id)

    def get_ui_settings(self) -> UiConfig:
        return self._project_service.load_project(self._context.project_root).ui

    def save_ui_settings(self, *, run_animation: bool) -> UiConfig:
        root = self._context.project_root
        config = self._project_service.load_project(root)
        updated = replace(config, ui=UiConfig(run_animation=run_animation))
        self._context.config_store.save(root, updated)
        return updated.ui

    def _asset_database_service(
        self,
        *,
        manifest_path: str | Path | None = None,
    ) -> AssetDatabaseService:
        init_database = self._context.init_asset_database
        validate_database = self._context.validate_asset_database
        build_database: Callable[[str | Path], Path]
        if manifest_path is None:
            minimal_writer = self._context.write_minimal_static_asset_database
            if minimal_writer is None:
                raise ApplicationError("admin_service_unavailable", "资产库构建能力未配置")
            build_database = minimal_writer
        else:
            build_from_manifest = self._context.build_asset_database_from_manifest
            if build_from_manifest is None:
                raise ApplicationError("admin_service_unavailable", "资产库构建能力未配置")

            def build_database_from_manifest(db_path: str | Path) -> Path:
                return build_from_manifest(db_path, manifest_path)

            build_database = build_database_from_manifest

        if init_database is None or validate_database is None:
            raise ApplicationError("admin_service_unavailable", "资产库维护能力未配置")
        return AssetDatabaseService(
            init_database=init_database,
            build_database=build_database,
            validate_database=validate_database,
        )

    def _asset_handler_service(self) -> AssetHandlerBindingService:
        repository = self._context.asset_handler_repository
        registry = self._context.content_unit_registry
        if repository is None or registry is None:
            raise ApplicationError("admin_service_unavailable", "资产 handler 维护能力未配置")
        return AssetHandlerBindingService(
            repository=repository,
            content_unit_registry=registry,
            manifest_validator=self._context.manifest_validator,
            manifest_updater=self._context.manifest_updater,
            manifest_syncer=self._context.manifest_syncer,
        )

    def _require_workflow_service(self) -> WorkflowService:
        if self._workflow_service is None:
            raise ApplicationError("workflow_store_unavailable", "工作流存档能力未配置")
        return self._workflow_service


def _result_not_found(session_id: str) -> ApplicationError:
    return ApplicationError("not_found", f"运行结果不存在：{session_id}")
