from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ProcessPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from types import TracebackType

from genshin_sim.application.errors_kinds import execution_error_code
from genshin_sim.application.execution import SynchronousSimulationExecutor
from genshin_sim.application.input import SimulationInput
from genshin_sim.application.jobs import (
    SimulationJobNotFoundError,
    SimulationJobPayloadError,
    SimulationJobResult,
    SimulationJobState,
    SimulationJobStatus,
    SimulationWorkerPayload,
    run_simulation_worker,
)
from genshin_sim.application.jobs.models import _utc_now
from genshin_sim.infrastructure.assets_sqlite import SQLiteAssetRepository
from genshin_sim.infrastructure.results_sqlite import SQLiteResultWriter

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _ProcessJobRecord:
    status: SimulationJobStatus
    future: Future[SimulationJobResult]
    result: SimulationJobResult | None = None


class ProcessSimulationJobRunner:
    """基于子进程池的仿真任务 runner。"""

    def __init__(
        self,
        *,
        asset_db_path: str | Path,
        result_db_path: str | Path,
        max_workers: int = 1,
        job_id_factory: Callable[[], str] | None = None,
    ) -> None:
        if max_workers <= 0:
            raise ValueError("max_workers 必须大于 0")
        self.asset_db_path = Path(asset_db_path)
        self.result_db_path = Path(result_db_path)
        self._job_id_factory = job_id_factory or (lambda: uuid.uuid4().hex)
        self._pool = ProcessPoolExecutor(max_workers=max_workers)
        self._jobs: dict[str, _ProcessJobRecord] = {}
        self._closed = False

    def submit_input(self, config: SimulationInput) -> str:
        status = self._create_status()
        payload = SimulationWorkerPayload.from_input(
            job_id=status.job_id,
            simulation_input=config,
            asset_db_path=str(self.asset_db_path),
            result_db_path=str(self.result_db_path),
            created_at=status.created_at,
        )
        logger.info(
            "提交进程模拟输入任务",
            extra={"job_id": status.job_id, "input_name": config.meta.name},
        )
        return self._submit_payload(status, payload)

    def submit_file(self, path: str | Path) -> str:
        status = self._create_status()
        payload = SimulationWorkerPayload.from_file(
            job_id=status.job_id,
            input_path=str(path),
            asset_db_path=str(self.asset_db_path),
            result_db_path=str(self.result_db_path),
            created_at=status.created_at,
        )
        logger.info(
            "提交进程模拟输入文件任务",
            extra={"job_id": status.job_id, "input_path": str(path)},
        )
        return self._submit_payload(status, payload)

    def get_status(self, job_id: str) -> SimulationJobStatus:
        return self._refresh_record(self._require_record(job_id)).status

    def get_result(self, job_id: str) -> SimulationJobResult:
        record = self._refresh_record(self._require_record(job_id))
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
        record = self._refresh_record(self._require_record(job_id))
        if record.result is not None:
            return record.status

        if record.future.cancel():
            finished_at = _utc_now()
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
            logger.info("进程仿真任务已取消", extra={"job_id": job_id})
            return record.status

        logger.info("运行中的进程仿真任务暂未取消", extra={"job_id": job_id})
        return self._refresh_record(record).status

    def shutdown(self, *, wait: bool = True, cancel_futures: bool = False) -> None:
        if self._closed:
            return
        self._closed = True
        self._pool.shutdown(wait=wait, cancel_futures=cancel_futures)

    def __enter__(self) -> ProcessSimulationJobRunner:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc, traceback
        self.shutdown(cancel_futures=True)

    def _create_status(self) -> SimulationJobStatus:
        if self._closed:
            raise RuntimeError("仿真进程 runner 已关闭")
        return SimulationJobStatus(
            job_id=self._job_id_factory(),
            state=SimulationJobState.QUEUED,
        )

    def _submit_payload(
        self,
        status: SimulationJobStatus,
        payload: SimulationWorkerPayload,
    ) -> str:
        future = self._pool.submit(run_sqlite_simulation_worker, payload)
        self._jobs[status.job_id] = _ProcessJobRecord(status=status, future=future)
        return status.job_id

    def _refresh_record(self, record: _ProcessJobRecord) -> _ProcessJobRecord:
        if record.result is not None:
            return record

        future = record.future
        if future.cancelled():
            record.result = self._cancelled_result(record.status)
            record.status = _status_from_result(record.result)
            return record

        if future.done():
            record.result = self._future_result(record)
            record.status = _status_from_result(record.result)
            logger.info(
                "进程仿真任务已结束",
                extra={"job_id": record.status.job_id, "state": record.status.state.value},
            )
            return record

        if future.running() and record.status.state is SimulationJobState.QUEUED:
            record.status = replace(
                record.status,
                state=SimulationJobState.RUNNING,
                started_at=record.status.started_at or _utc_now(),
            )
        return record

    def _future_result(self, record: _ProcessJobRecord) -> SimulationJobResult:
        try:
            return record.future.result()
        except Exception as exc:
            logger.info(
                "进程仿真任务失败",
                extra={"job_id": record.status.job_id, "error": str(exc) or exc.__class__.__name__},
            )
            return SimulationJobResult(
                job_id=record.status.job_id,
                state=SimulationJobState.FAILED,
                error_code=execution_error_code(exc),
                error_message=str(exc) or exc.__class__.__name__,
                created_at=record.status.created_at,
                started_at=record.status.started_at or _utc_now(),
                finished_at=_utc_now(),
            )

    def _cancelled_result(self, status: SimulationJobStatus) -> SimulationJobResult:
        finished_at = _utc_now()
        return SimulationJobResult(
            job_id=status.job_id,
            state=SimulationJobState.CANCELLED,
            created_at=status.created_at,
            started_at=status.started_at,
            finished_at=finished_at,
        )

    def _require_record(self, job_id: str) -> _ProcessJobRecord:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise SimulationJobNotFoundError(f"仿真任务不存在：{job_id}") from exc


def run_sqlite_simulation_worker(payload: SimulationWorkerPayload) -> SimulationJobResult:
    """在 worker 进程中重建 SQLite 依赖并执行仿真。"""

    if not payload.asset_db_path:
        raise SimulationJobPayloadError("asset_db_path 不能为空")
    if not payload.result_db_path:
        raise SimulationJobPayloadError("result_db_path 不能为空")

    executor = SynchronousSimulationExecutor.create(
        asset_repository=SQLiteAssetRepository(payload.asset_db_path),
        result_writer=SQLiteResultWriter(payload.result_db_path),
    )
    return run_simulation_worker(payload, executor)


def _status_from_result(result: SimulationJobResult) -> SimulationJobStatus:
    return SimulationJobStatus(
        job_id=result.job_id,
        state=result.state,
        session_id=result.session_id,
        error_code=result.error_code,
        error_message=result.error_message,
        created_at=result.created_at,
        started_at=result.started_at,
        finished_at=result.finished_at,
    )
