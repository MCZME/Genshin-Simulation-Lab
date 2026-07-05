from __future__ import annotations

from pathlib import Path

import pytest

from genshin_sim.application.config import SimulationConfig
from genshin_sim.application.execution import SimulationRunSummary
from genshin_sim.application.jobs import (
    SimulationJobResult,
    SimulationJobState,
    SimulationJobStatus,
)
from genshin_sim.application.services import ApplicationServiceError, SimulationTaskService


class FakeRunner:
    def __init__(self, result: SimulationJobResult) -> None:
        self.result = result
        self.submitted: list[tuple[str, str]] = []

    def submit_config(self, config: SimulationConfig) -> str:
        self.submitted.append(("config", config.meta.name))
        return self.result.job_id

    def submit_file(self, path: str | Path) -> str:
        self.submitted.append(("file", str(path)))
        return self.result.job_id

    def get_status(self, job_id: str) -> SimulationJobStatus:
        return SimulationJobStatus(job_id=job_id, state=self.result.state)

    def get_result(self, job_id: str) -> SimulationJobResult:
        assert job_id == self.result.job_id
        return self.result

    def cancel(self, job_id: str) -> SimulationJobStatus:
        return SimulationJobStatus(job_id=job_id, state=SimulationJobState.CANCELLED)


class DelayedRunner(FakeRunner):
    def __init__(self, result: SimulationJobResult) -> None:
        super().__init__(result)
        self.get_result_calls = 0

    def get_result(self, job_id: str) -> SimulationJobResult:
        self.get_result_calls += 1
        if self.get_result_calls == 1:
            return SimulationJobResult(job_id=job_id, state=SimulationJobState.RUNNING)
        return super().get_result(job_id)


def test_simulation_task_service_submits_and_waits_for_file():
    runner = FakeRunner(
        SimulationJobResult(
            job_id="job-1",
            state=SimulationJobState.COMPLETED,
            session_id="session-1",
            summary=SimulationRunSummary(
                stop_reason="COMPLETED",
                end_frame=2,
                frames_run=2,
            ),
        )
    )
    service = SimulationTaskService(runner)

    result = service.run_file_and_wait("config.json")

    assert runner.submitted == [("file", "config.json")]
    assert result.session_id == "session-1"
    assert result.summary is not None
    assert result.summary.frames_run == 2


def test_simulation_task_service_polls_until_terminal_result():
    runner = DelayedRunner(
        SimulationJobResult(
            job_id="job-2",
            state=SimulationJobState.COMPLETED,
            session_id="session-2",
            summary=SimulationRunSummary(
                stop_reason="COMPLETED",
                end_frame=2,
                frames_run=2,
            ),
        )
    )
    service = SimulationTaskService(runner)

    result = service.run_file_and_wait("config.json", poll_interval_seconds=0)

    assert result.session_id == "session-2"
    assert runner.get_result_calls == 2


def test_simulation_task_service_raises_for_failed_wait():
    runner = FakeRunner(
        SimulationJobResult(
            job_id="job-3",
            state=SimulationJobState.FAILED,
            error_message="执行失败",
        )
    )
    service = SimulationTaskService(runner)

    with pytest.raises(ApplicationServiceError, match="执行失败"):
        service.run_file_and_wait("config.json")
