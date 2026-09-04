from __future__ import annotations

from pathlib import Path
from typing import Literal

from genshin_sim.application.execution import (
    CompletedSimulationRun,
    RecordedEvent,
    SimulationExecutionOutcome,
    SimulationRunSummary,
)
from genshin_sim.application.input import SimulationInput


class FakeExecutor:
    """仿真执行协议的内存假实现，供任务层测试复用。"""

    def __init__(self, mode: Literal["success", "failure"] = "success") -> None:
        self.mode = mode
        self.calls: list[tuple[str, str]] = []

    def execute_input(self, config: SimulationInput) -> SimulationExecutionOutcome:
        self.calls.append(("input", config.meta.name))
        return self._execute()

    def execute_file(self, path: str | Path) -> SimulationExecutionOutcome:
        self.calls.append(("file", str(path)))
        return self._execute()

    def _execute(self) -> SimulationExecutionOutcome:
        if self.mode == "failure":
            raise RuntimeError("执行失败")
        run = CompletedSimulationRun(
            input_schema_version=2,
            input_kind="simulation_input",
            input_meta={"name": "demo"},
            input_snapshot={"schema_version": 2, "kind": "simulation_input"},
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
