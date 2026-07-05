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
    InMemorySimulationJobRunner,
    SimulationJobNotFoundError,
    SimulationJobState,
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
                    event_type="INPUT_KEY_CONSUMED",
                    data={"key": "keyboard.e"},
                ),
            ),
        )
        return SimulationExecutionOutcome(session_id="session-1", run=run)


def test_in_memory_runner_completes_config_job():
    runner = InMemorySimulationJobRunner(
        FakeExecutor(),
        job_id_factory=lambda: "job-1",
    )

    job_id = runner.submit_config(_minimal_config())

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
