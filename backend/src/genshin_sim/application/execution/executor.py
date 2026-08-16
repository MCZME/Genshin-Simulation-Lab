from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from genshin_sim.application.assembly import AssembledSimulation, SimulationAssembler
from genshin_sim.application.execution.models import (
    CompletedSimulationRun,
    FailedSimulationRun,
    RecordedEvent,
    SimulationRunSummary,
)
from genshin_sim.application.execution.protocols import ResultWriter
from genshin_sim.application.input import SimulationInput
from genshin_sim.assets import AssetRepository
from genshin_sim.core.events import EventSubscriber, EventType, GameEvent

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SimulationExecutionOutcome:
    session_id: str
    run: CompletedSimulationRun


class SynchronousSimulationExecutor:
    """同步执行一次仿真的内部执行器。"""

    def __init__(
        self,
        assembler: SimulationAssembler,
        result_writer: ResultWriter,
        *,
        asset_repository: AssetRepository | None = None,
    ) -> None:
        self.assembler = assembler
        self.result_writer = result_writer
        self.asset_repository = asset_repository

    @classmethod
    def create(
        cls,
        asset_repository: AssetRepository,
        result_writer: ResultWriter,
    ) -> SynchronousSimulationExecutor:
        return cls(
            assembler=SimulationAssembler(asset_repository),
            result_writer=result_writer,
            asset_repository=asset_repository,
        )

    def execute_file(self, path: str | Path) -> SimulationExecutionOutcome:
        logger.info("执行模拟输入文件", extra={"input_path": str(path)})
        return self.execute_input(SimulationInput.from_json_file(path))

    def execute_input(self, config: SimulationInput) -> SimulationExecutionOutcome:
        session_id = uuid.uuid4().hex
        started_at = _utc_now()
        asset_version = _asset_version(self.asset_repository)
        logger.info(
            "仿真组装开始",
            extra={"config_name": config.meta.name, "session_id": session_id},
        )
        try:
            assembled = self.assembler.assemble(config)
            logger.info(
                "仿真运行开始",
                extra={"config_name": config.meta.name, "session_id": session_id},
            )
            collected_events: list[RecordedEvent] = []
            subscriptions: list[tuple[EventType, EventSubscriber]] = []

            def recorder(event: GameEvent) -> None:
                if not event.should_record:
                    return
                collected_events.append(
                    RecordedEvent(
                        frame=event.frame,
                        event_type=event.event_type.name,
                        data=event.payload.to_dict(),
                    )
                )

            for event_type in EventType:
                assembled.context.events.subscribe(event_type, recorder)
                subscriptions.append((event_type, recorder))

            try:
                result = assembled.simulator.run()
            finally:
                for event_type, handler in subscriptions:
                    assembled.context.events.unsubscribe(event_type, handler)

            logger.info(
                "仿真运行完成",
                extra={
                    "config_name": config.meta.name,
                    "session_id": session_id,
                    "frames_run": result.frames_run,
                    "stop_reason": result.stop_reason.name,
                },
            )
            run = CompletedSimulationRun(
                session_id=session_id,
                input_schema_version=config.schema_version,
                input_kind=config.kind,
                input_meta=config.meta.to_dict(),
                input_snapshot=config.to_dict(),
                summary=SimulationRunSummary.from_result(result),
                events=tuple(collected_events),
                initial_snapshot=_initial_snapshot(assembled),
                asset_version=asset_version,
                started_at=started_at,
                finished_at=_utc_now(),
            )
            self.result_writer.save_run(run)
            logger.info(
                "仿真结果已保存",
                extra={"config_name": config.meta.name, "session_id": session_id},
            )
            return SimulationExecutionOutcome(session_id=session_id, run=run)
        except Exception as exc:
            self.result_writer.save_failed_run(
                FailedSimulationRun(
                    session_id=session_id,
                    input_schema_version=config.schema_version,
                    input_kind=config.kind,
                    input_meta=config.meta.to_dict(),
                    input_snapshot=config.to_dict(),
                    error_code=exc.__class__.__name__,
                    error_message=str(exc) or exc.__class__.__name__,
                    started_at=started_at,
                )
            )
            logger.error(
                "仿真执行失败",
                extra={"config_name": config.meta.name, "session_id": session_id},
                exc_info=True,
            )
            raise


def _initial_snapshot(assembled: AssembledSimulation) -> dict[str, Any] | None:
    snapshot_runtime = getattr(assembled.simulator.runtime_world, "snapshot_runtime", None)
    if snapshot_runtime is None:
        return None
    frame_snapshot = snapshot_runtime.snapshot_at(0)
    return None if frame_snapshot is None else frame_snapshot.to_dict()


def _asset_version(repository: AssetRepository | None) -> str | None:
    """读取资产库数据版本作为运行记录 provenance。"""

    if repository is None:
        return None
    return repository.get_meta().get("data_version")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
