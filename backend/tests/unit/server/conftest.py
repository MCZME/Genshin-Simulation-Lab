"""server 单元测试共享脚手架。"""

from collections.abc import Callable
from typing import Any, cast

import pytest

from genshin_sim.application import (
    ApplicationError,
    ApplicationFacade,
    AssetListItem,
    BatchMember,
    BatchMemberState,
    BatchMemberStatus,
    BatchMemberValidation,
    BatchRunState,
    BatchRunStatus,
    BatchValidationResult,
    RecordedEvent,
    RelationTable,
    RunDetail,
    RunListItem,
    TemplateDeclaration,
    TemplateResult,
    UiConfig,
    WorkflowDetail,
    WorkflowSummary,
    WorkspaceInfo,
)

ApplicationFacadeFactory = Callable[..., ApplicationFacade]


class FakeApplicationFacade:
    """覆盖切片 3 全部 MVP 端点的内存 facade 替身。"""

    def __init__(
        self,
        *,
        workspace: WorkspaceInfo | None = None,
        ui_settings: UiConfig | None = None,
        workflows: tuple[WorkflowDetail, ...] = (),
        results: tuple[RunDetail, ...] = (),
        assets: tuple[AssetListItem, ...] = (),
        batch_runs: tuple[BatchRunStatus, ...] = (),
        analysis_declarations: tuple[TemplateDeclaration, ...] = (),
        analysis_results: dict[str, TemplateResult] | None = None,
    ) -> None:
        self.workspace = workspace or WorkspaceInfo("data", "2026.08.17", True)
        self.ui_settings = ui_settings or UiConfig()
        self.saved_ui_settings: list[bool] = []
        self._workflows = {workflow.id: workflow for workflow in workflows}
        self._results = {run.session_id: run for run in results}
        self._assets = list(assets)
        self._batch_runs = {run.run_id: run for run in batch_runs}
        self._analysis_declarations = analysis_declarations
        self._analysis_results = analysis_results or {}

    def get_workspace(self) -> WorkspaceInfo:
        return self.workspace

    def list_workflows(self) -> tuple[WorkflowSummary, ...]:
        return tuple(
            WorkflowSummary(id=workflow.id, name=workflow.name, updated_at=workflow.updated_at)
            for workflow in sorted(
                self._workflows.values(),
                key=lambda item: item.updated_at,
                reverse=True,
            )
        )

    def create_workflow(self, name: str = "未命名工作流") -> WorkflowDetail:
        workflow_id = f"wf_{len(self._workflows) + 1:08x}"
        detail = WorkflowDetail(
            id=workflow_id,
            name=name,
            updated_at="2026-08-18T00:00:00+00:00",
            definition={
                "schema_version": 1,
                "meta": {"name": name},
                "regions": [],
                "nodes": [],
                "edges": [],
                "layout": {},
            },
        )
        self._workflows[workflow_id] = detail
        return detail

    def get_workflow(self, workflow_id: str) -> WorkflowDetail:
        return self._require_workflow(workflow_id)

    def save_workflow(
        self,
        workflow_id: str,
        definition: dict[str, Any],
    ) -> WorkflowDetail:
        current = self._require_workflow(workflow_id)
        meta = definition.get("meta")
        name = meta.get("name") if isinstance(meta, dict) else None
        detail = WorkflowDetail(
            id=workflow_id,
            name=name if isinstance(name, str) and name.strip() else current.name,
            updated_at="2026-08-18T01:00:00+00:00",
            definition=dict(definition),
        )
        self._workflows[workflow_id] = detail
        return detail

    def delete_workflow(self, workflow_id: str) -> None:
        self._require_workflow(workflow_id)
        del self._workflows[workflow_id]

    def get_ui_settings(self) -> UiConfig:
        return self.ui_settings

    def save_ui_settings(self, *, run_animation: bool) -> UiConfig:
        self.saved_ui_settings.append(run_animation)
        self.ui_settings = UiConfig(run_animation=run_animation)
        return self.ui_settings

    def validate_batch_inputs(self, members: list[BatchMember]) -> BatchValidationResult:
        if len(members) > 200:
            raise ApplicationError("batch_too_large", "批次成员数不能超过 200")
        seen: set[str] = set()
        for member in members:
            if member.item_id in seen:
                raise ApplicationError(
                    "duplicate_item_id",
                    f"批次内 item_id 不能重复：{member.item_id}",
                )
            seen.add(member.item_id)
        return BatchValidationResult(
            ok=True,
            members=tuple(
                BatchMemberValidation(item_id=member.item_id, ok=True) for member in members
            ),
        )

    def submit_batch(
        self,
        members: list[BatchMember],
        *,
        name: str = "",
        concurrency: int | None = None,
    ) -> BatchRunStatus:
        self.validate_batch_inputs(members)
        run_id = f"run_{len(self._batch_runs) + 1:06x}"
        status = BatchRunStatus(
            run_id=run_id,
            name=name,
            state=BatchRunState.COMPLETED,
            concurrency=concurrency or 4,
            cancel_requested=False,
            member_count=len(members),
            members=tuple(
                BatchMemberStatus(
                    item_id=member.item_id,
                    state=BatchMemberState.COMPLETED,
                    session_id=f"session-{index}",
                )
                for index, member in enumerate(members)
            ),
        )
        self._batch_runs[run_id] = status
        return status

    def get_batch(self, run_id: str) -> BatchRunStatus:
        try:
            return self._batch_runs[run_id]
        except KeyError as exc:
            raise ApplicationError("not_found", f"批次不存在：{run_id}") from exc

    def cancel_batch(self, run_id: str) -> BatchRunStatus:
        return self.get_batch(run_id)

    def list_results(
        self,
        limit: int = 50,
        offset: int = 0,
        state: str | None = None,
    ) -> tuple[RunListItem, ...]:
        items = [
            _run_list_item(run)
            for run in self._results.values()
            if state is None or run.state == state
        ]
        return tuple(items[offset : offset + limit])

    def get_run(self, session_id: str, *, include_events: bool = True) -> RunDetail:
        try:
            detail = self._results[session_id]
        except KeyError as exc:
            raise ApplicationError("not_found", f"运行结果不存在：{session_id}") from exc
        if include_events:
            return detail
        return RunDetail(
            session_id=detail.session_id,
            state=detail.state,
            input_snapshot=detail.input_snapshot,
            initial_snapshot=None,
            summary=detail.summary,
            events=(),
            error_code=detail.error_code,
            error_message=detail.error_message,
            created_at=detail.created_at,
            started_at=detail.started_at,
            finished_at=detail.finished_at,
        )

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
        events = _filter_events(self.get_run(session_id).events, frame_min, frame_max, event_type)
        start = offset or 0
        end = None if limit is None else start + limit
        return events[start:end]

    def count_run_events(
        self,
        session_id: str,
        *,
        frame_min: int | None = None,
        frame_max: int | None = None,
        event_type: str | None = None,
    ) -> int:
        return len(
            _filter_events(self.get_run(session_id).events, frame_min, frame_max, event_type)
        )

    def list_analysis_templates(self) -> tuple[TemplateDeclaration, ...]:
        return self._analysis_declarations

    def execute_analysis_template(
        self,
        template_id: str,
        *,
        params: dict[str, Any] | None = None,
        relations: dict[str, RelationTable] | None = None,
    ) -> TemplateResult:
        params = params or {}
        if "session_ids" in params and not isinstance(params["session_ids"], list):
            raise ApplicationError("validation_failed", "session_ids 必须是字符串列表")
        try:
            return self._analysis_results[template_id]
        except KeyError as exc:
            raise ApplicationError("not_found", f"分析模板不存在：{template_id}") from exc

    def list_assets(
        self,
        kind: str,
        *,
        q: str | None = None,
        element: str | None = None,
        weapon_type: str | None = None,
        rarity: int | None = None,
        usable: bool | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[AssetListItem, ...]:
        prefix = _asset_prefix(kind)
        query = (q or "").strip().casefold()
        items = [
            item
            for item in self._assets
            if item.asset_key.startswith(prefix + ":")
            and (not query or query in item.name.casefold() or query in item.source_id.casefold())
        ]
        if element is not None:
            items = [item for item in items if item.element == element]
        if weapon_type is not None:
            items = [item for item in items if item.weapon_type == weapon_type]
        if rarity is not None:
            items = [item for item in items if item.rarity == rarity]
        if usable is not None:
            items = [item for item in items if item.usable == usable]
        start = offset
        end = None if limit is None else start + limit
        return tuple(items[start:end])

    def get_asset(self, kind: str, source_id: str) -> AssetListItem:
        prefix = _asset_prefix(kind)
        for item in self._assets:
            if item.asset_key == f"{prefix}:{source_id}":
                return item
        raise ApplicationError("not_found", f"资产不存在：{kind}/{source_id}")

    def _require_workflow(self, workflow_id: str) -> WorkflowDetail:
        try:
            return self._workflows[workflow_id]
        except KeyError as exc:
            raise ApplicationError("not_found", f"工作流不存在：{workflow_id}") from exc


def _asset_prefix(kind: str) -> str:
    prefixes = {
        "characters": "character",
        "weapons": "weapon",
        "artifact-sets": "artifact_set",
    }
    if kind not in prefixes:
        raise ApplicationError("not_found", f"未知资产类型：{kind}")
    return prefixes[kind]


def _run_list_item(run: RunDetail) -> RunListItem:
    return RunListItem(
        session_id=run.session_id,
        state=run.state,
        name=_run_name(run),
        stop_reason="" if run.summary is None else run.summary.stop_reason,
        end_frame=0 if run.summary is None else run.summary.end_frame,
        frames_run=0 if run.summary is None else run.summary.frames_run,
        created_at=run.created_at,
        event_count=len(run.events),
    )


def _run_name(run: RunDetail) -> str:
    meta = run.input_snapshot.get("meta")
    if isinstance(meta, dict):
        name = meta.get("name")
        if isinstance(name, str) and name.strip():
            return name
    return "未命名仿真"


def _filter_events(
    events: tuple[RecordedEvent, ...],
    frame_min: int | None,
    frame_max: int | None,
    event_type: str | None,
) -> tuple[RecordedEvent, ...]:
    return tuple(
        event
        for event in events
        if (frame_min is None or event.frame >= frame_min)
        and (frame_max is None or event.frame <= frame_max)
        and (event_type is None or event.event_type == event_type)
    )


@pytest.fixture
def application_facade() -> ApplicationFacadeFactory:
    """构造覆盖切片 3 全部端点的 server facade 替身。"""

    def make(**kwargs: Any) -> ApplicationFacade:
        return cast(ApplicationFacade, FakeApplicationFacade(**kwargs))

    return make
