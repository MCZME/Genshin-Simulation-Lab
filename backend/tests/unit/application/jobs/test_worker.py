from __future__ import annotations

import pytest

from genshin_sim.application.jobs import (
    SimulationJobPayloadError,
    SimulationJobState,
    SimulationWorkerPayload,
    run_simulation_worker,
)
from tests.helpers.assembly import minimal_input
from tests.helpers.jobs import FakeExecutor


def test_worker_runs_input_payload():
    executor = FakeExecutor()
    payload = SimulationWorkerPayload.from_input(
        job_id="job-1",
        simulation_input=minimal_input(),
        asset_db_path="assets.db",
        result_db_path="results.db",
        created_at="2026-07-06T00:00:00+00:00",
    )

    result = run_simulation_worker(payload, executor)

    assert executor.calls == [("input", "demo")]
    assert result.state is SimulationJobState.COMPLETED
    assert result.session_id == "session-1"
    assert result.summary is not None
    assert result.summary.frames_run == 2
    assert result.created_at == "2026-07-06T00:00:00+00:00"
    assert result.started_at is not None
    assert result.finished_at is not None


def test_worker_runs_input_file():
    executor = FakeExecutor()
    payload = SimulationWorkerPayload.from_file(
        job_id="job-2",
        input_path="config.json",
    )

    result = run_simulation_worker(payload, executor)

    assert executor.calls == [("file", "config.json")]
    assert result.state is SimulationJobState.COMPLETED
    assert result.session_id == "session-1"


def test_worker_returns_failed_result_for_execution_error():
    payload = SimulationWorkerPayload.from_file(job_id="job-3", input_path="config.json")

    result = run_simulation_worker(payload, FakeExecutor("failure"))

    assert result.state is SimulationJobState.FAILED
    assert result.error_message == "执行失败"
    assert result.started_at is not None
    assert result.finished_at is not None


def test_worker_payload_requires_exactly_one_input_source():
    with pytest.raises(SimulationJobPayloadError, match="必须且只能提供"):
        SimulationWorkerPayload(job_id="job-4")

    with pytest.raises(SimulationJobPayloadError, match="必须且只能提供"):
        SimulationWorkerPayload(
            job_id="job-5",
            input_payload=minimal_input().to_dict(),
            input_path="config.json",
        )
