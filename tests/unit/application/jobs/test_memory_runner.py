from __future__ import annotations

import pytest

from genshin_sim.application.jobs import (
    InMemorySimulationJobRunner,
    SimulationJobNotFoundError,
    SimulationJobState,
)
from tests.helpers.assembly import minimal_input
from tests.helpers.jobs import FakeExecutor


def test_in_memory_runner_completes_config_job():
    runner = InMemorySimulationJobRunner(
        FakeExecutor(),
        job_id_factory=lambda: "job-1",
    )

    job_id = runner.submit_input(minimal_input())

    status = runner.get_status(job_id)
    result = runner.get_result(job_id)

    assert status.state is SimulationJobState.COMPLETED
    assert status.session_id == "session-1"
    assert status.started_at is not None
    assert status.finished_at is not None
    assert result.summary is not None
    assert result.summary.frames_run == 2


def test_in_memory_runner_records_failure():
    runner = InMemorySimulationJobRunner(
        FakeExecutor("failure"),
        job_id_factory=lambda: "job-2",
    )

    job_id = runner.submit_file("config.json")

    status = runner.get_status(job_id)
    result = runner.get_result(job_id)

    assert status.state is SimulationJobState.FAILED
    assert status.error_message == "执行失败"
    assert result.state is SimulationJobState.FAILED
    assert result.error_message == "执行失败"


def test_in_memory_runner_raises_for_missing_job():
    runner = InMemorySimulationJobRunner(FakeExecutor())

    with pytest.raises(SimulationJobNotFoundError, match="仿真任务不存在：missing"):
        runner.get_status("missing")
