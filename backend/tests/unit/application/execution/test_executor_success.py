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


class FakeAssetRepository:
    def get_meta(self) -> dict[str, str]:
        return {
            "schema_version": "1",
            "data_version": "2026.08.1",
            "source_version": "sources-1",
            "importer_version": "importer-1",
        }


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


def test_executor_writes_completed_run_with_asset_version():
    writer = RecordingResultWriter()
    executor = SynchronousSimulationExecutor(
        cast(SimulationAssembler, StubAssembler()),
        writer,
        asset_repository=cast(AssetRepository, FakeAssetRepository()),
    )

    executor.execute_input(_minimal_input())

    assert len(writer.completed) == 1
    run = writer.completed[0]
    assert run.asset_version == "2026.08.1"
    assert run.content_version is None
    assert run.seed is None
    assert run.input_snapshot["kind"] == "simulation_input"
    assert run.summary.stop_reason == "COMPLETED"


def test_executor_without_asset_repository_leaves_asset_version_empty():
    writer = RecordingResultWriter()
    executor = SynchronousSimulationExecutor(
        cast(SimulationAssembler, StubAssembler()),
        writer,
    )

    executor.execute_input(_minimal_input())

    assert writer.completed[0].asset_version is None
