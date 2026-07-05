from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from genshin_sim.application.assembly import SimulationAssembler
from genshin_sim.application.config import SimulationConfig
from genshin_sim.application.execution.models import (
    CompletedSimulationRun,
    RecordedEvent,
    SimulationRunSummary,
)
from genshin_sim.application.execution.protocols import ResultWriter
from genshin_sim.assets import AssetRepository
from genshin_sim.content import HandlerRegistry
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
    ) -> None:
        self.assembler = assembler
        self.result_writer = result_writer

    @classmethod
    def create(
        cls,
        asset_repository: AssetRepository,
        handler_registry: HandlerRegistry,
        result_writer: ResultWriter,
    ) -> SynchronousSimulationExecutor:
        return cls(
            assembler=SimulationAssembler(asset_repository, handler_registry),
            result_writer=result_writer,
        )

    def execute_file(self, path: str | Path) -> SimulationExecutionOutcome:
        logger.info("执行仿真配置文件", extra={"config_path": str(path)})
        return self.execute_config(SimulationConfig.from_json_file(path))

    def execute_config(self, config: SimulationConfig) -> SimulationExecutionOutcome:
        logger.info("仿真组装开始", extra={"config_name": config.meta.name})
        assembled = self.assembler.assemble(config)
        logger.info("仿真运行开始", extra={"config_name": config.meta.name})
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
                    source_type=None if event.source is None else event.source.__class__.__name__,
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
                "frames_run": result.frames_run,
                "stop_reason": result.stop_reason.name,
            },
        )
        run = CompletedSimulationRun(
            config_schema_version=config.schema_version,
            config_kind=config.kind,
            config_meta=config.meta.to_dict(),
            config_snapshot=config.to_dict(),
            summary=SimulationRunSummary.from_result(result),
            events=tuple(collected_events),
        )
        session_id = self.result_writer.save_run(run)
        logger.info(
            "仿真结果已保存",
            extra={"config_name": config.meta.name, "session_id": session_id},
        )
        return SimulationExecutionOutcome(session_id=session_id, run=run)
