from __future__ import annotations

from pathlib import Path
from typing import Protocol

from genshin_sim.application.input import SimulationInput
from genshin_sim.application.jobs.models import SimulationJobResult, SimulationJobStatus


class SimulationJobRunner(Protocol):
    """仿真任务调度器协议。"""

    def submit_input(self, config: SimulationInput) -> str: ...

    def submit_file(self, path: str | Path) -> str: ...

    def get_status(self, job_id: str) -> SimulationJobStatus: ...

    def get_result(self, job_id: str) -> SimulationJobResult: ...

    def cancel(self, job_id: str) -> SimulationJobStatus: ...
