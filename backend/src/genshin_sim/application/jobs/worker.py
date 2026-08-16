from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from genshin_sim.application.execution import SimulationExecutor
from genshin_sim.application.input import SimulationInput
from genshin_sim.application.jobs.errors import SimulationJobPayloadError
from genshin_sim.application.jobs.models import SimulationJobResult, SimulationJobState, _utc_now


@dataclass(frozen=True, slots=True)
class SimulationWorkerPayload:
    """可序列化的仿真 worker 输入。"""

    job_id: str
    input_payload: dict[str, Any] | None = None
    input_path: str | None = None
    asset_db_path: str | None = None
    result_db_path: str | None = None
    created_at: str = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if not self.job_id:
            raise SimulationJobPayloadError("job_id 不能为空")
        has_input_payload = self.input_payload is not None
        has_input_path = self.input_path is not None
        if has_input_payload == has_input_path:
            raise SimulationJobPayloadError("必须且只能提供 input_payload 或 input_path")
        if self.input_path is not None and not self.input_path:
            raise SimulationJobPayloadError("input_path 不能为空")

    @classmethod
    def from_input(
        cls,
        *,
        job_id: str,
        simulation_input: SimulationInput,
        asset_db_path: str | None = None,
        result_db_path: str | None = None,
        created_at: str | None = None,
    ) -> SimulationWorkerPayload:
        return cls(
            job_id=job_id,
            input_payload=simulation_input.to_dict(),
            asset_db_path=asset_db_path,
            result_db_path=result_db_path,
            created_at=created_at or _utc_now(),
        )

    @classmethod
    def from_file(
        cls,
        *,
        job_id: str,
        input_path: str,
        asset_db_path: str | None = None,
        result_db_path: str | None = None,
        created_at: str | None = None,
    ) -> SimulationWorkerPayload:
        return cls(
            job_id=job_id,
            input_path=input_path,
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
        if payload.input_payload is not None:
            simulation_input = SimulationInput.from_mapping(payload.input_payload)
            outcome = executor.execute_input(simulation_input)
        elif payload.input_path is not None:
            outcome = executor.execute_file(payload.input_path)
        else:
            raise SimulationJobPayloadError("必须提供模拟输入")
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
