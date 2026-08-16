from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from genshin_sim.application.execution import SimulationExecutionOutcome, SimulationExecutor
from genshin_sim.application.input import SimulationInput
from genshin_sim.application.jobs.errors import SimulationJobNotFoundError
from genshin_sim.application.jobs.models import (
    SimulationJobResult,
    SimulationJobState,
    SimulationJobStatus,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _MemoryJobRecord:
    status: SimulationJobStatus
    result: SimulationJobResult | None = None


class InMemorySimulationJobRunner:
    """内存版仿真任务 runner。

    当前实现会同步执行提交的任务，只用于验证任务接口和状态模型。
    """

    def __init__(
        self,
        executor: SimulationExecutor,
        *,
        job_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.executor = executor
        self._job_id_factory = job_id_factory or (lambda: uuid.uuid4().hex)
        self._jobs: dict[str, _MemoryJobRecord] = {}

    def submit_input(self, config: SimulationInput) -> str:
        job_id = self._create_job()
        logger.info("提交模拟输入任务", extra={"job_id": job_id, "input_name": config.meta.name})
        self._execute_job(job_id, lambda: self.executor.execute_input(config))
        return job_id

    def submit_file(self, path: str | Path) -> str:
        job_id = self._create_job()
        logger.info("提交模拟输入文件任务", extra={"job_id": job_id, "input_path": str(path)})
        self._execute_job(job_id, lambda: self.executor.execute_file(path))
        return job_id

    def get_status(self, job_id: str) -> SimulationJobStatus:
        return self._require_record(job_id).status

    def get_result(self, job_id: str) -> SimulationJobResult:
        record = self._require_record(job_id)
        if record.result is not None:
            return record.result
        status = record.status
        return SimulationJobResult(
            job_id=status.job_id,
            state=status.state,
            session_id=status.session_id,
            error_message=status.error_message,
            created_at=status.created_at,
            started_at=status.started_at,
            finished_at=status.finished_at,
        )

    def cancel(self, job_id: str) -> SimulationJobStatus:
        record = self._require_record(job_id)
        if record.status.state in {
            SimulationJobState.COMPLETED,
            SimulationJobState.FAILED,
            SimulationJobState.CANCELLED,
        }:
            return record.status

        finished_at = _now()
        record.status = replace(
            record.status,
            state=SimulationJobState.CANCELLED,
            finished_at=finished_at,
        )
        record.result = SimulationJobResult(
            job_id=record.status.job_id,
            state=SimulationJobState.CANCELLED,
            created_at=record.status.created_at,
            started_at=record.status.started_at,
            finished_at=finished_at,
        )
        logger.info("仿真任务已取消", extra={"job_id": job_id})
        return record.status

    def _create_job(self) -> str:
        job_id = self._job_id_factory()
        status = SimulationJobStatus(job_id=job_id, state=SimulationJobState.QUEUED)
        self._jobs[job_id] = _MemoryJobRecord(status=status)
        return job_id

    def _execute_job(
        self,
        job_id: str,
        execute: Callable[[], SimulationExecutionOutcome],
    ) -> None:
        record = self._require_record(job_id)
        started_at = _now()
        record.status = replace(
            record.status,
            state=SimulationJobState.RUNNING,
            started_at=started_at,
        )
        try:
            outcome = execute()
        except Exception as exc:
            finished_at = _now()
            message = str(exc) or exc.__class__.__name__
            record.status = replace(
                record.status,
                state=SimulationJobState.FAILED,
                error_message=message,
                finished_at=finished_at,
            )
            record.result = SimulationJobResult(
                job_id=job_id,
                state=SimulationJobState.FAILED,
                error_message=message,
                created_at=record.status.created_at,
                started_at=record.status.started_at,
                finished_at=finished_at,
            )
            logger.info("仿真任务失败", extra={"job_id": job_id})
            return

        finished_at = _now()
        record.status = replace(
            record.status,
            state=SimulationJobState.COMPLETED,
            session_id=outcome.session_id,
            finished_at=finished_at,
        )
        record.result = SimulationJobResult(
            job_id=job_id,
            state=SimulationJobState.COMPLETED,
            session_id=outcome.session_id,
            summary=outcome.run.summary,
            created_at=record.status.created_at,
            started_at=record.status.started_at,
            finished_at=finished_at,
        )
        logger.info("仿真任务完成", extra={"job_id": job_id, "session_id": outcome.session_id})

    def _require_record(self, job_id: str) -> _MemoryJobRecord:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise SimulationJobNotFoundError(f"仿真任务不存在：{job_id}") from exc


def _now() -> str:
    return _utc_now()


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="seconds")
