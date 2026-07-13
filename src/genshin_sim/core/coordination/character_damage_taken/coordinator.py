from __future__ import annotations

from genshin_sim.core.coordination.character_damage_taken.errors import (
    CharacterDamageTakenCommitError,
    CharacterDamageTakenPlanConflictError,
    CharacterDamageTakenReentrancyError,
)
from genshin_sim.core.coordination.character_damage_taken.models import (
    CharacterDamageTakenRecord,
    CharacterIncomingDamage,
)
from genshin_sim.core.coordination.character_damage_taken.protocols import (
    CharacterHealthDamagePort,
    ShieldAbsorptionPort,
)
from genshin_sim.core.events import DamageAppliedPayload, EventEngine, EventType, GameEvent
from genshin_sim.core.systems.health import CharacterDamageApplication
from genshin_sim.core.systems.shield import ShieldAbsorptionRequest


class CharacterDamageTakenCoordinator:
    """把已结算角色伤害原子应用到护盾和血量。"""

    def __init__(
        self,
        shield_port: ShieldAbsorptionPort,
        health_port: CharacterHealthDamagePort,
        event_engine: EventEngine,
    ) -> None:
        self.shield_port = shield_port
        self.health_port = health_port
        self.event_engine = event_engine
        self._records: list[CharacterDamageTakenRecord] = []
        self._active = False

    @property
    def records(self) -> tuple[CharacterDamageTakenRecord, ...]:
        return tuple(self._records)

    def apply(self, request: CharacterIncomingDamage) -> CharacterDamageTakenRecord:
        if self._active:
            raise CharacterDamageTakenReentrancyError("角色受伤协调器不允许同步重入")
        self._active = True
        try:
            shield_plan = self.shield_port.prepare_absorption(
                ShieldAbsorptionRequest(
                    damage_id=request.damage_id,
                    frame=request.frame,
                    target_ref=request.target_ref,
                    incoming_amount=request.amount,
                    element=request.element,
                    source_ref=request.source_ref,
                    source_context=request.source_context,
                    tags=request.tags,
                )
            )
            health_application = CharacterDamageApplication(
                change_id=request.damage_id,
                frame=request.frame,
                target_ref=request.target_ref,
                amount=shield_plan.result.health_bound_damage,
                source_ref=request.source_ref,
                source_context=request.source_context,
                tags=request.tags,
            )
            health_plan = self.health_port.prepare_damage(health_application)
            self._validate_cross_plan(request, shield_plan, health_plan)
            self.shield_port.validate(shield_plan)
            self.health_port.validate(health_plan)
            try:
                shield_receipt = self.shield_port.commit_prevalidated(shield_plan)
                health_receipt = self.health_port.commit_prevalidated(health_plan)
            except Exception as exc:
                raise CharacterDamageTakenCommitError(
                    f"预校验后的领域提交违反不得失败契约：{exc}"
                ) from exc
            record = CharacterDamageTakenRecord(
                incoming_damage=request,
                shield_result=shield_plan.result,
                health_application=health_application,
                health_result=health_plan.result,
            )
            self._records.append(record)
            for event in self.shield_port.events_for(shield_receipt):
                self.event_engine.publish(event)
            for event in self.health_port.events_for(health_receipt):
                self.event_engine.publish(event)
            if request.amount > 0:
                self.event_engine.publish(
                    GameEvent(
                        event_type=EventType.DAMAGE_APPLIED,
                        frame=request.frame,
                        payload=DamageAppliedPayload(record),
                        source=self,
                    )
                )
            return record
        finally:
            self._active = False

    @staticmethod
    def _validate_cross_plan(request, shield_plan, health_plan) -> None:
        if (
            shield_plan.damage_id != request.damage_id
            or shield_plan.frame != request.frame
            or shield_plan.target_ref != request.target_ref
        ):
            raise CharacterDamageTakenPlanConflictError("护盾计划与角色伤害请求不一致")
        application = health_plan.application
        if (
            application.change_id != request.damage_id
            or application.frame != request.frame
            or application.target_ref != request.target_ref
            or application.amount != shield_plan.result.health_bound_damage
        ):
            raise CharacterDamageTakenPlanConflictError("血量计划与护盾穿透结果不一致")
