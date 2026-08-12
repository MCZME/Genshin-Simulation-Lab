from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from genshin_sim.application.execution.models import CompletedSimulationRun, FailedSimulationRun

if TYPE_CHECKING:
    from genshin_sim.application.execution.executor import SimulationExecutionOutcome
    from genshin_sim.application.input import SimulationInput


class SimulationExecutor(Protocol):
    """执行一次仿真的内部协议。"""

    def execute_input(self, config: SimulationInput) -> SimulationExecutionOutcome: ...

    def execute_file(self, path: str | Path) -> SimulationExecutionOutcome: ...


class ResultWriter(Protocol):
    """持久化已完成的仿真运行。"""

    def save_run(self, run: CompletedSimulationRun) -> str: ...

    def save_failed_run(self, run: FailedSimulationRun) -> str: ...
