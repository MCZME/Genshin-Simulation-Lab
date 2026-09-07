"""治疗结算事件发布与生命系统提交入口。"""

from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.core.events import EventEngine, EventType, GameEvent, HealingResolvedPayload
from genshin_sim.core.systems.healing.errors import HealingValidationError
from genshin_sim.core.systems.healing.models import HealingRequest, HealingResult
from genshin_sim.core.systems.healing.resolver import HealingResolver
from genshin_sim.core.systems.health import (
    CharacterHealingApplication,
    CharacterHealthChangeResult,
    HealthRuntime,
)


@dataclass(frozen=True, slots=True)
class HealingApplicationRecord:
    """一次治疗理论结算和生命提交的完整编排结果。"""

    request: HealingRequest
    result: HealingResult
    health_result: CharacterHealthChangeResult


class HealingRequestHandler:
    """类型化单目标治疗请求的同步处理入口。"""

    def __init__(
        self,
        resolver: HealingResolver,
        health_runtime: HealthRuntime,
        event_engine: EventEngine | None = None,
    ) -> None:
        """保存治疗结算器、生命系统入口和事件发布器。"""

        if event_engine is None:
            event_engine = health_runtime.event_engine
        elif event_engine is not health_runtime.event_engine:
            raise HealingValidationError("event_engine 必须与 health_runtime.event_engine 相同")
        self.resolver = resolver
        self.health_runtime = health_runtime
        self.event_engine = event_engine
        self._records: list[HealingApplicationRecord] = []

    @property
    def records(self) -> tuple[HealingApplicationRecord, ...]:
        """返回已经完成生命提交的治疗编排记录快照。"""

        return tuple(self._records)

    def handle(self, request: HealingRequest) -> HealingApplicationRecord:
        """结算治疗、发布结算事实，并把最终治疗量提交给生命系统。"""

        result = self.resolver.resolve(request)
        self.event_engine.publish(
            GameEvent(
                event_type=EventType.HEALING_RESOLVED,
                frame=result.frame,
                payload=HealingResolvedPayload(result),
                source=self,
            )
        )
        health_result = self.health_runtime.apply_healing(healing_result_to_application(result))
        record = HealingApplicationRecord(
            request=request,
            result=result,
            health_result=health_result,
        )
        self._records.append(record)
        return record


def healing_result_to_application(result: HealingResult) -> CharacterHealingApplication:
    """把理论治疗结果转换为生命系统可提交的恢复请求。"""

    return CharacterHealingApplication(
        change_id=result.healing_id,
        frame=result.frame,
        target_ref=result.target_ref,
        amount=result.final_healing,
        source_ref=result.source_ref,
        source_context=result.source_context,
        tags=result.tags,
    )
