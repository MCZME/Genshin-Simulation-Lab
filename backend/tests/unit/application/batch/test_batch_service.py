from __future__ import annotations

from dataclasses import replace

import pytest

from genshin_sim.application.batch import (
    BatchMember,
    BatchMemberState,
    BatchRunService,
    BatchRunState,
    BatchValidationError,
)
from genshin_sim.application.jobs import SimulationJobState, SimulationJobStatus
from genshin_sim.application.services import BatchInputValidationService
from genshin_sim.assets import CharacterAsset
from genshin_sim.content import create_default_content_unit_registry
from tests.helpers.assembly import minimal_input
from tests.helpers.asset_repository import FakeAssetRepository


class _ControlledRunner:
    def __init__(self, *, cancel_error: str | None = None) -> None:
        self.submitted: list[tuple[str, str]] = []
        self.cancelled: list[str] = []
        self.statuses: dict[str, SimulationJobStatus] = {}
        self.cancel_error = cancel_error
        self._counter = 0

    def submit_input(self, config):
        self._counter += 1
        job_id = f"job-{self._counter}"
        self.submitted.append((job_id, config.meta.name))
        self.statuses[job_id] = SimulationJobStatus(
            job_id=job_id,
            state=SimulationJobState.QUEUED,
            created_at=f"2026-08-18T00:00:0{self._counter}+00:00",
        )
        return job_id

    def submit_file(self, path):
        raise AssertionError(path)

    def get_status(self, job_id):
        return self.statuses[job_id]

    def get_result(self, job_id):
        raise AssertionError(job_id)

    def cancel(self, job_id):
        self.cancelled.append(job_id)
        if self.cancel_error is not None:
            raise RuntimeError(self.cancel_error)
        status = self.statuses[job_id]
        if status.state is SimulationJobState.QUEUED:
            status = replace(
                status, state=SimulationJobState.CANCELLED, finished_at="2026-08-18T00:01:00+00:00"
            )
            self.statuses[job_id] = status
        return status

    def set_status(self, job_id: str, state: SimulationJobState, **kwargs) -> None:
        self.statuses[job_id] = replace(self.statuses[job_id], state=state, **kwargs)


def _members(count: int) -> tuple[BatchMember, ...]:
    return tuple(
        BatchMember(
            item_id=f"item-{index}",
            input=minimal_input(),
        )
        for index in range(count)
    )


def _full_validator() -> BatchInputValidationService:
    """带默认测试资产与内容注册表的完整校验器。"""

    return BatchInputValidationService(FakeAssetRepository())


def test_batch_submission_preserves_order_and_concurrency_slots() -> None:
    runner = _ControlledRunner()
    service = BatchRunService(
        runner,
        validator=_full_validator(),
        run_id_factory=lambda: "run-1",
        default_concurrency=2,
    )

    initial = service.submit(_members(3))

    assert initial.run_id == "run-1"
    assert initial.concurrency == 2
    assert [item_id for item_id, _ in runner.submitted] == ["job-1", "job-2"]
    assert [member.item_id for member in initial.members] == ["item-0", "item-1", "item-2"]

    runner.set_status("job-1", SimulationJobState.RUNNING, started_at="2026-08-18T00:00:01+00:00")
    running = service.get("run-1")
    assert running.state is BatchRunState.RUNNING
    assert [item_id for item_id, _ in runner.submitted] == ["job-1", "job-2"]

    runner.set_status(
        "job-1",
        SimulationJobState.COMPLETED,
        session_id="session-1",
        finished_at="2026-08-18T00:00:02+00:00",
    )
    service.get("run-1")

    assert [item_id for item_id, _ in runner.submitted] == ["job-1", "job-2", "job-3"]


def test_batch_derives_partial_state_from_completed_and_failed_members() -> None:
    runner = _ControlledRunner()
    service = BatchRunService(
        runner,
        validator=_full_validator(),
        run_id_factory=lambda: "run-2",
        default_concurrency=2,
    )
    service.submit(_members(2))

    runner.set_status("job-1", SimulationJobState.COMPLETED, session_id="session-1")
    runner.set_status(
        "job-2",
        SimulationJobState.FAILED,
        error_message="执行失败",
        finished_at="2026-08-18T00:00:02+00:00",
    )
    result = service.get("run-2")

    assert result.state is BatchRunState.PARTIAL
    assert result.members[0].state is BatchMemberState.COMPLETED
    assert result.members[0].session_id == "session-1"
    assert result.members[1].state is BatchMemberState.FAILED
    assert result.members[1].error_message == "执行失败"


def test_batch_cancel_marks_queued_members_and_waits_for_running_member() -> None:
    runner = _ControlledRunner()
    service = BatchRunService(
        runner,
        validator=_full_validator(),
        run_id_factory=lambda: "run-3",
        default_concurrency=1,
    )
    service.submit(_members(3))
    runner.set_status("job-1", SimulationJobState.RUNNING)
    service.get("run-3")

    stopping = service.cancel("run-3")

    assert stopping.state is BatchRunState.STOPPING
    assert stopping.cancel_requested is True
    assert [member.state for member in stopping.members] == [
        BatchMemberState.STOPPING,
        BatchMemberState.CANCELLED,
        BatchMemberState.CANCELLED,
    ]
    assert runner.cancelled == ["job-1"]

    runner.set_status("job-1", SimulationJobState.COMPLETED, session_id="session-ignored")
    finished = service.get("run-3")

    assert finished.state is BatchRunState.CANCELLED
    assert finished.members[0].state is BatchMemberState.CANCELLED
    assert finished.members[0].session_id is None


def test_batch_cancel_failure_is_recorded_and_persisted() -> None:
    runner = _ControlledRunner(cancel_error="cancel boom")
    service = BatchRunService(
        runner,
        validator=_full_validator(),
        run_id_factory=lambda: "run-6",
        default_concurrency=1,
    )
    service.submit(_members(1))
    runner.set_status("job-1", SimulationJobState.RUNNING)
    service.get("run-6")

    stopping = service.cancel("run-6")

    assert stopping.state is BatchRunState.STOPPING
    assert stopping.members[0].error_message == "cancel boom"

    refreshed = service.get("run-6")
    assert refreshed.state is BatchRunState.STOPPING
    assert refreshed.members[0].error_message == "cancel boom"


@pytest.mark.parametrize(
    ("members", "code"),
    [
        pytest.param(_members(201), "batch_too_large", id="too-large"),
        pytest.param(
            (BatchMember("duplicate", minimal_input()), BatchMember("duplicate", minimal_input())),
            "duplicate_item_id",
            id="duplicate-item-id",
        ),
    ],
)
def test_batch_rejects_invalid_batch_shape(members, code: str) -> None:
    service = BatchRunService(_ControlledRunner())

    with pytest.raises(BatchValidationError) as error:
        service.validate_members(members)

    assert error.value.code == code


def test_batch_input_validation_reports_structure_asset_and_handler_errors() -> None:
    repository = FakeAssetRepository(
        characters=(
            CharacterAsset(
                asset_key="character:75",
                source_id="75",
                name="test",
                element="hydro",
                weapon_type="sword",
                rarity=5,
                burst_energy_cost=60.0,
                handler_key=None,
            ),
        )
    )
    validator = BatchInputValidationService(
        repository,
        content_unit_registry=create_default_content_unit_registry(),
    )
    invalid_input = minimal_input().to_dict()
    invalid_input["team"][0]["character"]["asset_key"] = "character:missing"

    result = validator.validate_members(
        (
            BatchMember("bad-structure", {"schema_version": 2}),
            BatchMember("bad-asset", invalid_input),
            BatchMember("bad-handler", minimal_input()),
        )
    )

    assert result.ok is False
    assert [member.item_id for member in result.members] == [
        "bad-structure",
        "bad-asset",
        "bad-handler",
    ]
    assert result.members[0].details[0].code == "CONFIG_INVALID"
    assert result.members[1].details[0].code == "ASSET_NOT_FOUND"
    assert result.members[2].details[0].code == "HANDLER_UNAVAILABLE"
    assert all(
        "handler_key" not in detail.message
        for member in result.members
        for detail in member.details
    )


def test_batch_validation_reports_unavailable_without_asset_dependencies() -> None:
    validator = BatchInputValidationService()

    result = validator.validate_members((BatchMember("item-1", minimal_input()),))

    assert result.ok is False
    assert result.members[0].details[0].code == "VALIDATION_UNAVAILABLE"


def test_batch_submit_refuses_without_asset_dependency_validation() -> None:
    runner = _ControlledRunner()
    service = BatchRunService(runner, run_id_factory=lambda: "run-5")

    with pytest.raises(BatchValidationError) as error:
        service.submit(_members(1))

    assert error.value.code == "validation_failed"
    assert error.value.details[0]["code"] == "VALIDATION_UNAVAILABLE"
    assert runner.submitted == []


def test_batch_submit_is_atomic_when_member_validation_fails() -> None:
    runner = _ControlledRunner()
    validator = _full_validator()
    service = BatchRunService(runner, validator=validator)
    invalid = minimal_input().to_dict()
    invalid["team"] = []

    with pytest.raises(BatchValidationError) as error:
        service.submit(
            (
                BatchMember("valid", minimal_input()),
                BatchMember("invalid", invalid),
            )
        )

    assert error.value.code == "validation_failed"
    assert runner.submitted == []


def test_terminal_batch_remains_queryable_until_retention_expires() -> None:
    runner = _ControlledRunner()
    service = BatchRunService(
        runner,
        validator=_full_validator(),
        run_id_factory=lambda: "run-ttl",
        default_concurrency=1,
    )
    clock = [0.0]

    service.submit(_members(1))
    runner.set_status(
        "job-1",
        SimulationJobState.COMPLETED,
        session_id="session-1",
        finished_at="2026-08-18T00:00:02+00:00",
    )
    terminal = service.get("run-ttl")

    assert terminal.state is BatchRunState.COMPLETED
    assert service.get("run-ttl").state is BatchRunState.COMPLETED

    service._monotonic_factory = lambda: clock[0]  # noqa: SLF001 - 测试时钟推进
    service._runs["run-ttl"].terminal_at = 60.0  # noqa: SLF001 - 测试固定截止时刻
    clock[0] = 61.0
    service.validate_members(_members(1))

    with pytest.raises(Exception, match="run-ttl"):
        service.get("run-ttl")
