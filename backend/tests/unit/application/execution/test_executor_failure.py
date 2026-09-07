from __future__ import annotations

import logging
from pathlib import Path
from typing import cast

import pytest

from genshin_sim.application.assembly import SimulationAssembler
from genshin_sim.application.execution import (
    CompletedSimulationRun,
    FailedSimulationRun,
    RunState,
    SynchronousSimulationExecutor,
)
from genshin_sim.application.input import SimulationInput


class _RecordHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class RaisingAssembler:
    def assemble(self, config: SimulationInput) -> object:
        raise RuntimeError("组装失败")


class AssemblerWithFailingSimulation:
    """组装成功但模拟运行失败的替身。"""

    def assemble(self, config: SimulationInput) -> object:
        from genshin_sim.core.simulation import SimulationContext

        class _FailingSimulator:
            runtime_world = None

            def run(self) -> object:
                raise RuntimeError("运行失败")

        context = SimulationContext()
        return type(
            "StubAssembled",
            (),
            {
                "context": context,
                "simulator": _FailingSimulator(),
            },
        )()


class RecordingResultWriter:
    def __init__(self) -> None:
        self.db_path = Path("results.db")
        self.completed: list[CompletedSimulationRun] = []
        self.failed: list[FailedSimulationRun] = []

    def save_run(self, run: CompletedSimulationRun) -> str:
        self.completed.append(run)
        return run.session_id

    def save_failed_run(self, run: FailedSimulationRun) -> str:
        self.failed.append(run)
        return run.session_id


def _minimal_input() -> SimulationInput:
    return SimulationInput.from_mapping(
        {
            "schema_version": 2,
            "kind": "simulation_input",
            "meta": {"name": "demo", "description": ""},
            "team": [],
            "scene": {"player": {}, "targets": []},
            "input_trace": [],
            "rules": {"enabled": []},
            "run_options": {"max_frames": 10},
        }
    )


def test_executor_does_not_write_failed_run_for_assembly_error():
    writer = RecordingResultWriter()
    executor = SynchronousSimulationExecutor(
        cast(SimulationAssembler, RaisingAssembler()),
        writer,
    )

    with pytest.raises(RuntimeError, match="组装失败"):
        executor.execute_input(_minimal_input())

    assert writer.completed == []
    assert writer.failed == []


def test_executor_writes_failed_run_and_reraises():
    writer = RecordingResultWriter()
    executor = SynchronousSimulationExecutor(
        cast(SimulationAssembler, AssemblerWithFailingSimulation()),
        writer,
    )

    with pytest.raises(RuntimeError, match="运行失败"):
        executor.execute_input(_minimal_input())

    assert writer.completed == []
    assert len(writer.failed) == 1
    failed = writer.failed[0]
    assert failed.state is RunState.FAILED
    assert failed.error_code == "SIMULATION_FAILED"
    assert failed.error_message == "运行失败"
    assert failed.input_snapshot["kind"] == "simulation_input"
    assert failed.session_id


def test_executor_logs_session_id_on_start_and_failure():
    writer = RecordingResultWriter()
    executor = SynchronousSimulationExecutor(
        cast(SimulationAssembler, AssemblerWithFailingSimulation()),
        writer,
    )
    logger = logging.getLogger("genshin_sim.application.execution.executor")
    previous_level = logger.level
    recorder = _RecordHandler()
    logger.setLevel(logging.INFO)
    logger.addHandler(recorder)
    try:
        with pytest.raises(RuntimeError, match="运行失败"):
            executor.execute_input(_minimal_input())
    finally:
        logger.setLevel(previous_level)
        logger.removeHandler(recorder)

    messages = {record.getMessage() for record in recorder.records}
    assert {"仿真组装开始", "仿真执行失败"} <= messages
    failed = writer.failed[0]
    assert all(
        getattr(record, "session_id", "") == failed.session_id for record in recorder.records
    )
    error_records = [record for record in recorder.records if record.levelno == logging.ERROR]
    assert len(error_records) == 1
    assert error_records[0].exc_info is not None
