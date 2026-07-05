from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from genshin_sim.application.config import SimulationConfig
from genshin_sim.application.execution import SimulationExecutor
from genshin_sim.application.jobs.errors import SimulationJobPayloadError
from genshin_sim.application.jobs.models import SimulationJobResult, SimulationJobState, _utc_now


@dataclass(frozen=True, slots=True)
class SimulationWorkerPayload:
    """可序列化的仿真 worker 输入。"""

    job_id: str
    config_payload: dict[str, Any] | None = None
    config_path: str | None = None
    asset_db_path: str | None = None
    result_db_path: str | None = None
    created_at: str = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if not self.job_id:
            raise SimulationJobPayloadError("job_id 不能为空")
        has_config_payload = self.config_payload is not None
        has_config_path = self.config_path is not None
        if has_config_payload == has_config_path:
            raise SimulationJobPayloadError("必须且只能提供 config_payload 或 config_path")
        if self.config_path is not None and not self.config_path:
            raise SimulationJobPayloadError("config_path 不能为空")

    @classmethod
    def from_config(
        cls,
        *,
        job_id: str,
        config: SimulationConfig,
        asset_db_path: str | None = None,
        result_db_path: str | None = None,
        created_at: str | None = None,
    ) -> SimulationWorkerPayload:
        return cls(
            job_id=job_id,
            config_payload=config.to_dict(),
            asset_db_path=asset_db_path,
            result_db_path=result_db_path,
            created_at=created_at or _utc_now(),
        )

    @classmethod
    def from_file(
        cls,
        *,
        job_id: str,
        config_path: str,
        asset_db_path: str | None = None,
        result_db_path: str | None = None,
        created_at: str | None = None,
    ) -> SimulationWorkerPayload:
        return cls(
            job_id=job_id,
            config_path=config_path,
            asset_db_path=asset_db_path,
            result_db_path=result_db_path,
            created_at=created_at or _utc_now(),
        )


def run_simulation_worker(
    payload: SimulationWorkerPayload,
    executor: SimulationExecutor,
) -> SimulationJobResult:
    """执行一个仿真 worker payload 并返回任务结果。"""

    started_at = _utc_now()
    try:
        if payload.config_payload is not None:
            config = SimulationConfig.from_mapping(payload.config_payload)
            outcome = executor.execute_config(config)
        elif payload.config_path is not None:
            outcome = executor.execute_file(payload.config_path)
        else:
            raise SimulationJobPayloadError("必须提供仿真配置")
    except Exception as exc:
        return SimulationJobResult(
            job_id=payload.job_id,
            state=SimulationJobState.FAILED,
            error_message=str(exc) or exc.__class__.__name__,
            created_at=payload.created_at or _utc_now(),
            started_at=started_at,
            finished_at=_utc_now(),
        )

    return SimulationJobResult(
        job_id=payload.job_id,
        state=SimulationJobState.COMPLETED,
        session_id=outcome.session_id,
        summary=outcome.run.summary,
        created_at=payload.created_at or _utc_now(),
        started_at=started_at,
        finished_at=_utc_now(),
    )
