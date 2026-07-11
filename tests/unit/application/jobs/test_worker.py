from __future__ import annotations

from pathlib import Path
from typing import Literal

import pytest

from genshin_sim.application.config import SimulationConfig
from genshin_sim.application.execution import (
    CompletedSimulationRun,
    RecordedEvent,
    SimulationExecutionOutcome,
    SimulationRunSummary,
)
from genshin_sim.application.jobs import (
    SimulationJobPayloadError,
    SimulationJobState,
    SimulationWorkerPayload,
    run_simulation_worker,
)


class FakeExecutor:
    def __init__(self, mode: Literal["success", "failure"] = "success") -> None:
        self.mode = mode
        self.calls: list[tuple[str, str]] = []

    def execute_config(self, config: SimulationConfig) -> SimulationExecutionOutcome:
        self.calls.append(("config", config.meta.name))
        return self._execute()

    def execute_file(self, path: str | Path) -> SimulationExecutionOutcome:
        self.calls.append(("file", str(path)))
        return self._execute()

    def _execute(self) -> SimulationExecutionOutcome:
        if self.mode == "failure":
            raise RuntimeError("执行失败")
        run = CompletedSimulationRun(
            config_schema_version=1,
            config_kind="simulation_config",
            config_meta={"name": "demo"},
            config_snapshot={"schema_version": 1, "kind": "simulation_config"},
            summary=SimulationRunSummary(
                stop_reason="COMPLETED",
                end_frame=2,
                frames_run=2,
            ),
            events=(
                RecordedEvent(
                    frame=1,
                    event_type="INPUT_KEY_RECEIVED",
                    data={"key": "keyboard.e"},
                ),
            ),
        )
        return SimulationExecutionOutcome(session_id="session-1", run=run)


def test_worker_runs_config_payload():
    executor = FakeExecutor()
    payload = SimulationWorkerPayload.from_config(
        job_id="job-1",
        config=_minimal_config(),
        asset_db_path="assets.db",
        result_db_path="results.db",
        created_at="2026-07-06T00:00:00+00:00",
    )

    result = run_simulation_worker(payload, executor)

    assert executor.calls == [("config", "demo")]
    assert result.state is SimulationJobState.COMPLETED
    assert result.session_id == "session-1"
    assert result.summary is not None
    assert result.summary.frames_run == 2
    assert result.created_at == "2026-07-06T00:00:00+00:00"
    assert result.started_at is not None
    assert result.finished_at is not None


def test_worker_runs_config_file():
    executor = FakeExecutor()
    payload = SimulationWorkerPayload.from_file(
        job_id="job-2",
        config_path="config.json",
    )

    result = run_simulation_worker(payload, executor)

    assert executor.calls == [("file", "config.json")]
    assert result.state is SimulationJobState.COMPLETED
    assert result.session_id == "session-1"


def test_worker_returns_failed_result_for_execution_error():
    payload = SimulationWorkerPayload.from_file(job_id="job-3", config_path="config.json")

    result = run_simulation_worker(payload, FakeExecutor("failure"))

    assert result.state is SimulationJobState.FAILED
    assert result.error_message == "执行失败"
    assert result.started_at is not None
    assert result.finished_at is not None


def test_worker_payload_requires_exactly_one_config_source():
    with pytest.raises(SimulationJobPayloadError, match="必须且只能提供"):
        SimulationWorkerPayload(job_id="job-4")

    with pytest.raises(SimulationJobPayloadError, match="必须且只能提供"):
        SimulationWorkerPayload(
            job_id="job-5",
            config_payload=_minimal_config().to_dict(),
            config_path="config.json",
        )


def _minimal_config() -> SimulationConfig:
    return SimulationConfig.from_mapping(
        {
            "schema_version": 1,
            "kind": "simulation_config",
            "meta": {"name": "demo", "description": ""},
            "team": [
                {
                    "slot": 1,
                    "character": {
                        "asset_key": "character:75",
                        "level": 90,
                        "constellation": 0,
                        "talents": {"normal_attack": 1},
                    },
                }
            ],
            "scene": {"targets": []},
            "input_trace": [],
            "rules": {"enabled": []},
            "run_options": {"max_frames": 10},
        }
    )
