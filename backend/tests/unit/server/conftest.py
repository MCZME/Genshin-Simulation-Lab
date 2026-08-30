"""server 单元测试共享脚手架。"""

from collections.abc import Callable
from typing import Any, cast

import pytest

from genshin_sim.application import (
    AnalysisPlan,
    AnalysisReadSchema,
    AnalysisTableResult,
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
    RunDetail,
    RunListItem,
    UiConfig,
    WorkflowDetail,
    WorkflowSummary,
    WorkspaceInfo,
)
from genshin_sim.application.config import DeveloperConfig
from genshin_sim.application.services.frame_state import fold_frame_state

ApplicationFacadeFactory = Callable[..., ApplicationFacade]


class FakeApplicationFacade:
    """覆盖切片 3 全部 MVP 端点的内存 facade 替身。"""

    def __init__(
        self,
        *,
        workspace: WorkspaceInfo | None = None,
        ui_settings: UiConfig | None = None,
        developer_settings: DeveloperConfig | None = None,
        workflows: tuple[WorkflowDetail, ...] = (),
        results: tuple[RunDetail, ...] = (),
        assets: tuple[AssetListItem, ...] = (),
        batch_runs: tuple[BatchRunStatus, ...] = (),
        analysis_plan_results: dict[str, AnalysisTableResult] | None = None,
        analysis_schema: AnalysisReadSchema | None = None,
    ) -> None:
        self.workspace = workspace or WorkspaceInfo("data", "2026.08.17", True)
        self.ui_settings = ui_settings or UiConfig()
        self.developer_settings = developer_settings or DeveloperConfig()
        self.saved_ui_settings: list[bool] = []
        self.saved_developer_settings: list[bool] = []
        self._workflows = {workflow.id: workflow for workflow in workflows}
        self._results = {run.session_id: run for run in results}
        self._assets = list(assets)
        self._batch_runs = {run.run_id: run for run in batch_runs}
        self._analysis_plan_results = analysis_plan_results or {}
        self._analysis_schema = analysis_schema

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

    def get_developer_settings(self) -> DeveloperConfig:
        return self.developer_settings

    def save_developer_settings(self, *, enabled: bool) -> DeveloperConfig:
        self.saved_developer_settings.append(enabled)
        self.developer_settings = DeveloperConfig(enabled=enabled)
        return self.developer_settings

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
        *,
        name_query: str | None = None,
        created_from: str | None = None,
        created_to: str | None = None,
        session_ids: tuple[str, ...] | list[str] | None = None,
    ) -> tuple[RunListItem, ...]:
        runs = sorted(
            self._results.values(),
            key=lambda run: (run.created_at, run.session_id),
            reverse=True,
        )
        if session_ids is not None:
            by_id = {run.session_id: run for run in runs}
            ordered = tuple(
                by_id[session_id]
                for session_id in dict.fromkeys(session_ids)
                if session_id in by_id
            )
            return tuple(_run_list_item(run) for run in ordered)[offset : offset + limit]
        query = (name_query or "").strip().casefold()
        items = [
            _run_list_item(run)
            for run in runs
            if (state is None or run.state == state)
            and (not query or query in _run_name(run).casefold())
            and (created_from is None or run.created_at >= created_from)
            and (created_to is None or run.created_at <= created_to)
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

    def get_run_event(self, session_id: str, ordinal: int) -> RecordedEvent | None:
        events = self.get_run(session_id).events
        if ordinal < 0 or ordinal >= len(events):
            return None
        return events[ordinal]

    def get_run_entities(self, session_id: str) -> dict[str, Any]:
        run = self.get_run(session_id, include_events=False)
        snapshot = run.input_snapshot
        characters: list[dict[str, Any]] = []
        asset_keys: list[str] = []
        slots: list[int] = []
        team = snapshot.get("team")
        if isinstance(team, list):
            for entry in team:
                if not isinstance(entry, dict):
                    continue
                slot = entry.get("slot")
                character = entry.get("character")
                if not isinstance(slot, int) or not isinstance(character, dict):
                    continue
                asset_key = character.get("asset_key")
                if not isinstance(asset_key, str) or not asset_key:
                    continue
                slots.append(slot)
                asset_keys.append(asset_key)
        names = {item.asset_key: item.name for item in self.resolve_assets(tuple(asset_keys))}
        characters = [
            {"slot": slot, "asset_key": asset_key, "name": names.get(asset_key, "")}
            for slot, asset_key in zip(slots, asset_keys, strict=True)
        ]
        scene = snapshot.get("scene")
        targets: list[dict[str, Any]] = []
        if isinstance(scene, dict) and isinstance(scene.get("targets"), list):
            for target in scene["targets"]:
                if not isinstance(target, dict) or not isinstance(target.get("id"), str):
                    continue
                targets.append(
                    {
                        "id": target["id"],
                        "label": target.get("label")
                        if isinstance(target.get("label"), str)
                        else "",
                    }
                )
        return {"characters": characters, "targets": targets}

    def get_frame_state(self, session_id: str, frame: int) -> dict[str, Any]:
        try:
            run = self._results[session_id]
        except KeyError as exc:
            raise ApplicationError("not_found", f"运行结果不存在：{session_id}") from exc
        end_frame = None if run.summary is None else run.summary.end_frame
        if end_frame is None or frame < 0 or frame > end_frame:
            raise ApplicationError(
                "frame_out_of_range",
                f"frame {frame} 超出会话 {session_id} 的运行范围",
            )
        return fold_frame_state(
            session_id=session_id,
            frame=frame,
            initial_snapshot=run.initial_snapshot or {},
            events=tuple(event for event in run.events if event.frame <= frame),
        )

    def execute_analysis_plan(self, plan: AnalysisPlan) -> dict[str, AnalysisTableResult]:
        try:
            return {node_id: self._analysis_plan_results[node_id] for node_id in plan.outputs}
        except KeyError as exc:
            raise ApplicationError("validation_failed", "outputs 引用了计划外的节点") from exc

    def analysis_schema(self) -> AnalysisReadSchema:
        if self._analysis_schema is None:
            raise ApplicationError("analysis_query_unavailable", "分析查询能力未配置")
        return self._analysis_schema

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

    def resolve_assets(self, keys: tuple[str, ...]) -> tuple[AssetListItem, ...]:
        found = {item.asset_key: item for item in self._assets}
        return tuple(found[key] for key in keys if key in found)

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
