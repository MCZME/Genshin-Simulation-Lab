"""application facade 单元测试。"""

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

import pytest

from genshin_sim.application import (
    AnalysisPlan,
    AnalysisPlanNode,
    ApplicationError,
    ApplicationFacade,
    AssetListKind,
    BatchMember,
    BatchMemberState,
    BatchRunState,
    create_application,
)
from genshin_sim.application.execution import SimulationExecutionOutcome
from genshin_sim.application.execution.models import (
    CompletedSimulationRun,
    FailedSimulationRun,
    SimulationRunSummary,
)
from genshin_sim.application.input import SimulationInput
from genshin_sim.application.jobs import (
    SimulationJobNotFoundError,
    SimulationJobResult,
    SimulationJobRunner,
    SimulationJobState,
    SimulationJobStatus,
)
from genshin_sim.application.models import RecordedEvent, RunDetail, RunListItem
from genshin_sim.application.services.workflows import (
    StoredWorkflow,
    WorkflowAlreadyExistsError,
    WorkflowNotFoundError,
)
from tests.helpers.assembly import minimal_input
from tests.helpers.asset_repository import FakeAssetRepository
from tests.helpers.jobs import FakeExecutor
from tests.helpers.project import FakeProjectConfigStore


class _FakeResultRepository:
    def __init__(
        self,
        runs: tuple[RunListItem, ...] = (),
        *,
        details: dict[str, RunDetail] | None = None,
    ) -> None:
        self.runs = runs
        self.details = details or {}

    def list_runs(
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
        return self.runs[offset : offset + limit]

    def get_run(self, session_id: str, *, include_events: bool = True) -> RunDetail:
        try:
            detail = self.details[session_id]
        except KeyError as exc:
            raise LookupError(session_id) from exc
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

    def get_events(
        self,
        session_id: str,
        frame_min: int | None = None,
        frame_max: int | None = None,
        event_type: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> tuple[RecordedEvent, ...]:
        run = self.details[session_id]
        events = run.events
        if frame_min is not None:
            events = tuple(event for event in events if event.frame >= frame_min)
        if frame_max is not None:
            events = tuple(event for event in events if event.frame <= frame_max)
        if event_type is not None:
            events = tuple(event for event in events if event.event_type == event_type)
        start = offset or 0
        end = None if limit is None else start + limit
        return events[start:end]

    def count_events(
        self,
        session_id: str,
        *,
        frame_min: int | None = None,
        frame_max: int | None = None,
        event_type: str | None = None,
    ) -> int:
        run = self.details[session_id]
        events = run.events
        if frame_min is not None:
            events = tuple(event for event in events if event.frame >= frame_min)
        if frame_max is not None:
            events = tuple(event for event in events if event.frame <= frame_max)
        if event_type is not None:
            events = tuple(event for event in events if event.event_type == event_type)
        return len(events)


class _FakeResultWriter:
    db_path = Path("results.db")

    def save_run(self, run: CompletedSimulationRun) -> str:
        return run.session_id

    def save_failed_run(self, run: FailedSimulationRun) -> str:
        return run.session_id


class _FakeJobRunner:
    """同步完成任务的假 job runner，替代已删除的内存版 runner。"""

    def __init__(
        self,
        executor: FakeExecutor,
        *,
        job_id_factory: Callable[[], str],
    ) -> None:
        self._executor = executor
        self._job_id_factory = job_id_factory
        self._results: dict[str, SimulationJobResult] = {}

    def submit_input(self, config: SimulationInput) -> str:
        job_id = self._job_id_factory()
        self._execute(job_id, lambda: self._executor.execute_input(config))
        return job_id

    def submit_file(self, path: str | Path) -> str:
        job_id = self._job_id_factory()
        self._execute(job_id, lambda: self._executor.execute_file(path))
        return job_id

    def _execute(
        self,
        job_id: str,
        execute: Callable[[], SimulationExecutionOutcome],
    ) -> None:
        try:
            outcome = execute()
        except Exception as exc:
            self._results[job_id] = SimulationJobResult(
                job_id=job_id,
                state=SimulationJobState.FAILED,
                error_message=str(exc),
            )
            return
        self._results[job_id] = SimulationJobResult(
            job_id=job_id,
            state=SimulationJobState.COMPLETED,
            session_id=outcome.session_id,
            summary=outcome.run.summary,
        )

    def get_status(self, job_id: str) -> SimulationJobStatus:
        result = self._require(job_id)
        return SimulationJobStatus(
            job_id=result.job_id,
            state=result.state,
            session_id=result.session_id,
            error_code=result.error_code,
            error_message=result.error_message,
        )

    def get_result(self, job_id: str) -> SimulationJobResult:
        return self._require(job_id)

    def cancel(self, job_id: str) -> SimulationJobStatus:
        return self.get_status(job_id)

    def _require(self, job_id: str) -> SimulationJobResult:
        try:
            return self._results[job_id]
        except KeyError as exc:
            raise SimulationJobNotFoundError(f"仿真任务不存在：{job_id}") from exc


class _FakeWorkflowStore:
    """工作流存储的内存假实现。"""

    def __init__(self) -> None:
        self.stored: dict[str, StoredWorkflow] = {}

    def list(self) -> tuple[StoredWorkflow, ...]:
        return tuple(self.stored.values())

    def get(self, workflow_id: str) -> StoredWorkflow:
        try:
            return self.stored[workflow_id]
        except KeyError as exc:
            raise WorkflowNotFoundError(workflow_id) from exc

    def create(self, workflow_id: str, definition: Mapping[str, Any]) -> StoredWorkflow:
        if workflow_id in self.stored:
            raise WorkflowAlreadyExistsError(workflow_id)
        stored = StoredWorkflow(workflow_id, dict(definition), "2026-08-18T00:00:00+00:00")
        self.stored[workflow_id] = stored
        return stored

    def replace(self, workflow_id: str, definition: Mapping[str, Any]) -> StoredWorkflow:
        if workflow_id not in self.stored:
            raise WorkflowNotFoundError(workflow_id)
        stored = StoredWorkflow(workflow_id, dict(definition), "2026-08-18T01:00:00+00:00")
        self.stored[workflow_id] = stored
        return stored

    def delete(self, workflow_id: str) -> None:
        if workflow_id not in self.stored:
            raise WorkflowNotFoundError(workflow_id)
        del self.stored[workflow_id]


def _make_facade(
    *,
    project_root: Path = Path("project"),
    config_store: FakeProjectConfigStore | None = None,
    asset_repository: FakeAssetRepository | None = None,
    asset_db_path: Path = Path("assets.db"),
    result_repository: _FakeResultRepository | None = None,
    job_runner: SimulationJobRunner | None = None,
    workflow_store: _FakeWorkflowStore | None = None,
) -> ApplicationFacade:
    return cast(
        ApplicationFacade,
        create_application(
            project_root=project_root,
            config_store=config_store or FakeProjectConfigStore(),
            asset_repository=asset_repository
            or FakeAssetRepository(meta={"data_version": "test-1"}),
            asset_db_path=asset_db_path,
            result_repository=result_repository or _FakeResultRepository(),
            result_writer=_FakeResultWriter(),
            job_runner=job_runner,
            workflow_store=workflow_store,
        ),
    )


def test_default_facade_returns_initialized_workspace(monkeypatch) -> None:
    project_root = Path("project")
    config_path = project_root / "config.toml"
    asset_db_path = Path("assets.db")
    monkeypatch.setattr(Path, "is_file", lambda self: self in {config_path, asset_db_path})
    facade = _make_facade(project_root=project_root, asset_db_path=asset_db_path)

    workspace = facade.get_workspace()

    assert workspace.data_dir == str(project_root / "data")
    assert workspace.asset_db_version == "test-1"
    assert workspace.initialized is True


@pytest.mark.parametrize(
    ("existing_paths", "asset_db_path"),
    [
        pytest.param(("assets.db",), "assets.db", id="missing-config"),
        pytest.param(("project/config.toml",), "missing.db", id="missing-asset-db"),
    ],
)
def test_default_facade_returns_uninitialized_workspace(
    monkeypatch,
    existing_paths: tuple[str, ...],
    asset_db_path: str,
) -> None:
    project_root = Path("project")
    existing = {Path(path) for path in existing_paths}
    monkeypatch.setattr(Path, "is_file", lambda self: self in existing)
    facade = _make_facade(project_root=project_root, asset_db_path=Path(asset_db_path))

    workspace = facade.get_workspace()

    assert workspace.data_dir == str(project_root / "data")
    assert workspace.asset_db_version == ""
    assert workspace.initialized is False


def test_facade_lists_assets() -> None:
    facade = _make_facade(asset_repository=FakeAssetRepository(meta={"data_version": "test-1"}))

    assets = facade.list_assets(AssetListKind.CHARACTERS)

    assert len(assets) == 1
    assert assets[0].asset_key == "character:75"
    assert assets[0].name == "test"


def test_facade_asset_search_detail_and_display_fields() -> None:
    facade = _make_facade(asset_repository=FakeAssetRepository(meta={"data_version": "test-1"}))

    items = facade.list_assets(AssetListKind.CHARACTERS, q="test", limit=1, offset=0)
    detail = facade.get_asset("characters", "75")

    assert items[0].source_id == "75"
    assert items[0].usable is True
    assert items[0].element == "hydro"
    assert items[0].weapon_type == "sword"
    assert items[0].rarity == 5
    assert detail.asset_key == "character:75"
    assert detail.status is None


def test_facade_lists_results() -> None:
    run = RunListItem(
        session_id="session-1",
        state="completed",
        name="demo",
        stop_reason="script_end",
        end_frame=10,
        frames_run=10,
        created_at="2026-01-01T00:00:00+00:00",
        event_count=2,
    )
    facade = _make_facade(result_repository=_FakeResultRepository((run,)))

    result = facade.list_results()

    assert result == (run,)


def test_facade_lists_results_with_offset() -> None:
    runs = tuple(
        RunListItem(
            session_id=f"session-{index}",
            state="completed",
            name=f"run-{index}",
            stop_reason="end",
            end_frame=10,
            frames_run=10,
            created_at=f"2026-01-0{index + 1}T00:00:00+00:00",
            event_count=0,
        )
        for index in range(2)
    )
    facade = _make_facade(result_repository=_FakeResultRepository(runs))

    result = facade.list_results(limit=1, offset=1)

    assert [item.session_id for item in result] == ["session-1"]


def test_facade_get_run_can_skip_events() -> None:
    detail = RunDetail(
        session_id="session-1",
        state="completed",
        input_snapshot={"meta": {"name": "demo"}},
        initial_snapshot={"frame": 0},
        summary=SimulationRunSummary(
            stop_reason="INPUT_EXHAUSTED",
            end_frame=600,
            frames_run=600,
        ),
        events=(RecordedEvent(frame=1, event_type="INPUT", data={"key": "keyboard.e"}),),
        error_code=None,
        error_message=None,
        created_at="2026-01-01T00:00:00+00:00",
        started_at=None,
        finished_at=None,
    )
    facade = _make_facade(result_repository=_FakeResultRepository(details={"session-1": detail}))

    metadata = facade.get_run("session-1", include_events=False)

    assert metadata.events == ()
    assert metadata.initial_snapshot is None
    assert metadata.summary is not None
    assert metadata.summary.frames_run == 600


def test_facade_counts_filtered_events() -> None:
    detail = RunDetail(
        session_id="session-1",
        state="completed",
        input_snapshot={"meta": {"name": "demo"}},
        initial_snapshot=None,
        summary=SimulationRunSummary(
            stop_reason="INPUT_EXHAUSTED",
            end_frame=600,
            frames_run=600,
        ),
        events=(
            RecordedEvent(
                frame=10,
                event_type="DAMAGE_RESOLVED",
                data={
                    "result": {
                        "request_id": "damage:1",
                        "source_ref": "character:slot_1",
                        "target_ref": "target:target_1",
                        "final_damage": 300.0,
                        "damage_type": "skill",
                    }
                },
            ),
            RecordedEvent(frame=20, event_type="INPUT", data={"key": "keyboard.e"}),
        ),
        error_code=None,
        error_message=None,
        created_at="2026-01-01T00:00:00+00:00",
        started_at=None,
        finished_at=None,
    )
    facade = _make_facade(result_repository=_FakeResultRepository(details={"session-1": detail}))

    count = facade.count_run_events(
        "session-1",
        frame_min=10,
        frame_max=10,
        event_type="DAMAGE_RESOLVED",
    )

    assert count == 1


def test_facade_executes_analysis_plan() -> None:
    facade = _make_facade()

    plan = AnalysisPlan(
        session_ids=("session-1",),
        nodes=(
            AnalysisPlanNode(id="runs1", kind="fetch", params={"source": "runs"}),
            AnalysisPlanNode(id="top1", kind="limit", params={"count": 5}, inputs=("runs1",)),
        ),
        outputs=("top1",),
    )
    tables = facade.execute_analysis_plan(plan)

    assert set(tables) == {"top1"}
    table = tables["top1"]
    assert table.rows == ()
    assert table.truncated is False
    assert table.columns[0].name == "session_id"

    schema = facade.analysis_schema()
    assert any(item.name == "simulation_runs" for item in schema.tables)

    bad_plan = AnalysisPlan(session_ids=(), nodes=(), outputs=("missing",))
    with pytest.raises(ApplicationError) as exc_info:
        facade.execute_analysis_plan(bad_plan)
    assert exc_info.value.code == "validation_failed"


def test_facade_exposes_batch_validation_and_lifecycle() -> None:
    job_counter = 0

    def job_id_factory() -> str:
        nonlocal job_counter
        job_counter += 1
        return f"job-{job_counter}"

    runner = _FakeJobRunner(
        FakeExecutor(),
        job_id_factory=job_id_factory,
    )
    facade = _make_facade(job_runner=runner)
    members = tuple(
        BatchMember(item_id=f"item-{index}", input=minimal_input().to_dict()) for index in range(2)
    )

    validation = facade.validate_batch_inputs(members)

    assert validation.ok is True
    assert [member.item_id for member in validation.members] == ["item-0", "item-1"]

    submitted = facade.submit_batch(members, name="facade batch", concurrency=1)

    assert submitted.state is BatchRunState.COMPLETED
    assert [member.item_id for member in submitted.members] == ["item-0", "item-1"]
    assert all(member.state is BatchMemberState.COMPLETED for member in submitted.members)
    assert facade.get_batch(submitted.run_id) == submitted
    assert facade.cancel_batch(submitted.run_id).state is BatchRunState.COMPLETED

    single = facade.run_input_and_wait(minimal_input())
    assert single.session_id == "session-1"
    assert single.error_code is None


def test_facade_batch_validation_returns_asset_diagnostic_for_member() -> None:
    payload = minimal_input().to_dict()
    payload["team"][0]["character"]["asset_key"] = "character:missing"
    facade = _make_facade()

    result = facade.validate_batch_inputs((BatchMember("bad-item", payload),))

    assert result.ok is False
    assert result.members[0].item_id == "bad-item"
    assert result.members[0].details[0].code == "ASSET_NOT_FOUND"
    assert result.members[0].details[0].item_id == "bad-item"


def test_facade_workflow_lifecycle() -> None:
    store = _FakeWorkflowStore()
    facade = _make_facade(workflow_store=store)

    created = facade.create_workflow(name="主配队")

    assert created.id.startswith("wf_")
    assert created.name == "主配队"
    assert [item.id for item in facade.list_workflows()] == [created.id]
    assert facade.get_workflow(created.id).definition == created.definition

    renamed = facade.save_workflow(
        created.id,
        {**created.definition, "meta": {"name": "新名字"}},
    )

    assert renamed.name == "新名字"
    assert facade.get_workflow(created.id).name == "新名字"

    facade.delete_workflow(created.id)

    assert facade.list_workflows() == ()
    with pytest.raises(WorkflowNotFoundError):
        facade.get_workflow(created.id)


def test_facade_default_workflow_store_follows_config_data_dir_changes(tmp_path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "config.toml").write_text("", encoding="utf-8")
    config_store = FakeProjectConfigStore(data_dir="data")
    facade = _make_facade(project_root=project_root, config_store=config_store)

    first = facade.create_workflow(name="甲")

    assert (project_root / "data" / "workflows" / f"{first.id}.json").is_file()

    config_store.data_dir = "lab"
    second = facade.create_workflow(name="乙")

    assert (project_root / "lab" / "workflows" / f"{second.id}.json").is_file()
    assert not (project_root / "data" / "workflows" / f"{second.id}.json").exists()
