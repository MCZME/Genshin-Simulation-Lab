from __future__ import annotations

from pathlib import Path
from time import monotonic, sleep

from genshin_sim.application.execution import ResultWriter, SynchronousSimulationExecutor
from genshin_sim.application.input import SimulationInput
from genshin_sim.application.jobs import (
    InMemorySimulationJobRunner,
    SimulationJobResult,
    SimulationJobRunner,
    SimulationJobState,
    SimulationJobStatus,
)
from genshin_sim.application.services.errors import ApplicationServiceError
from genshin_sim.assets import AssetRepository

_TERMINAL_STATES = {
    SimulationJobState.COMPLETED,
    SimulationJobState.FAILED,
    SimulationJobState.CANCELLED,
}


class SimulationTaskService:
    """仿真任务对外服务门面。

    UI 可直接使用提交与查询方法；CLI 等同步入口可以使用等待方法。
    """

    def __init__(
        self,
        runner: SimulationJobRunner,
    ) -> None:
        self.runner = runner

    @classmethod
    def create(
        cls,
        asset_repository: AssetRepository,
        result_writer: ResultWriter,
    ) -> SimulationTaskService:
        executor = SynchronousSimulationExecutor.create(
            asset_repository,
            result_writer,
        )
        return cls(
            runner=InMemorySimulationJobRunner(executor),
        )

    def submit_file(self, path: str | Path) -> str:
        return self.runner.submit_file(path)

    def submit_input(self, config: SimulationInput) -> str:
        return self.runner.submit_input(config)

    def get_status(self, job_id: str) -> SimulationJobStatus:
        return self.runner.get_status(job_id)

    def get_result(self, job_id: str) -> SimulationJobResult:
        return self.runner.get_result(job_id)

    def cancel(self, job_id: str) -> SimulationJobStatus:
        return self.runner.cancel(job_id)

    def run_file_and_wait(
        self,
        path: str | Path,
        *,
        poll_interval_seconds: float = 0.05,
        timeout_seconds: float | None = None,
    ) -> SimulationJobResult:
        job_id = self.submit_file(path)
        return self.wait_for_result(
            job_id,
            poll_interval_seconds=poll_interval_seconds,
            timeout_seconds=timeout_seconds,
        )

    def run_config_and_wait(
        self,
        config: SimulationInput,
        *,
        poll_interval_seconds: float = 0.05,
        timeout_seconds: float | None = None,
    ) -> SimulationJobResult:
        job_id = self.submit_input(config)
        return self.wait_for_result(
            job_id,
            poll_interval_seconds=poll_interval_seconds,
            timeout_seconds=timeout_seconds,
        )

    def wait_for_result(
        self,
        job_id: str,
        *,
        poll_interval_seconds: float = 0.05,
        timeout_seconds: float | None = None,
    ) -> SimulationJobResult:
        if poll_interval_seconds < 0:
            raise ValueError("poll_interval_seconds 不能为负数")
        if timeout_seconds is not None and timeout_seconds < 0:
            raise ValueError("timeout_seconds 不能为负数")

        deadline = None if timeout_seconds is None else monotonic() + timeout_seconds
        while True:
            result = self.get_result(job_id)
            if result.state in _TERMINAL_STATES:
                return self._require_completed(result)
            if deadline is not None and monotonic() >= deadline:
                raise ApplicationServiceError(f"等待仿真任务超时：{job_id}")
            sleep(poll_interval_seconds)

    @staticmethod
    def _require_completed(result: SimulationJobResult) -> SimulationJobResult:
        if result.state is SimulationJobState.COMPLETED:
            return result
        message = result.error_message or f"仿真任务未完成：{result.state.value}"
        raise ApplicationServiceError(message)
