from __future__ import annotations

from pathlib import Path
from typing import cast

from genshin_sim.application.assembly import SimulationAssembler
from genshin_sim.application.execution import (
    CompletedSimulationRun,
    SynchronousSimulationExecutor,
)
from genshin_sim.application.input import SimulationInput
from genshin_sim.assets import AssetRepository
from genshin_sim.core.simulation import SimulationContext, SimulationResult, SimulationStopReason
from tests.helpers.assembly import minimal_input
from tests.helpers.asset_repository import FakeAssetRepository


class StubSimulator:
    def __init__(self) -> None:
        self.runtime_world = None

    def run(self) -> SimulationResult:
        return SimulationResult(
            stop_reason=SimulationStopReason.COMPLETED,
            end_frame=0,
            frames_run=0,
        )


class StubAssembler:
    def assemble(self, config: SimulationInput) -> object:
        context = SimulationContext()
        return type(
            "StubAssembled",
            (),
            {
                "context": context,
                "simulator": StubSimulator(),
            },
        )()


class RecordingResultWriter:
    def __init__(self) -> None:
        self.db_path = Path("results.db")
        self.completed: list[CompletedSimulationRun] = []

    def save_run(self, run: CompletedSimulationRun) -> str:
        self.completed.append(run)
        return run.session_id

    def save_failed_run(self, run: object) -> str:
        raise AssertionError("成功路径不应写入失败记录")


_ASSET_META = {
    "schema_version": "1",
    "data_version": "2026.08.1",
    "source_version": "sources-1",
    "importer_version": "importer-1",
}


def _input(seed: int | None = None) -> SimulationInput:
    if seed is None:
        return minimal_input()
    return minimal_input(run_options={"max_frames": 10, "seed": seed})


def _executor(
    writer: RecordingResultWriter,
    *,
    with_asset_repository: bool = False,
) -> SynchronousSimulationExecutor:
    asset_repository: AssetRepository | None = None
    if with_asset_repository:
        asset_repository = cast(AssetRepository, FakeAssetRepository(meta=_ASSET_META))
    return SynchronousSimulationExecutor(
        cast(SimulationAssembler, StubAssembler()),
        writer,
        asset_repository=asset_repository,
    )


def test_executor_writes_completed_run_with_asset_version():
    writer = RecordingResultWriter()
    executor = _executor(writer, with_asset_repository=True)

    executor.execute_input(_input())

    assert len(writer.completed) == 1
    run = writer.completed[0]
    assert run.asset_version == "2026.08.1"
    assert run.content_version is None
    assert run.seed == "0"
    assert run.input_snapshot["kind"] == "simulation_input"
    assert run.summary.stop_reason == "COMPLETED"


def test_executor_records_run_options_seed():
    writer = RecordingResultWriter()
    executor = _executor(writer, with_asset_repository=True)

    executor.execute_input(_input(seed=42))

    assert writer.completed[0].seed == "42"


def test_executor_without_asset_repository_leaves_asset_version_empty():
    writer = RecordingResultWriter()
    executor = _executor(writer)

    executor.execute_input(_input())

    assert writer.completed[0].asset_version is None
