from __future__ import annotations

from typing import Protocol

from genshin_sim.core.attributes import (
    STAT_HP_MAX,
    AttributeQuery,
    AttributeResolution,
    AttributeResolveOptions,
    AttributeResolver,
    AttributeSubjectRef,
    TraceLevel,
)
from genshin_sim.core.entity_states import HealthState
from genshin_sim.core.events import (
    CharacterHealthChangedPayload,
    CharacterMaxHpChangedPayload,
    EventEngine,
    EventType,
    GameEvent,
)
from genshin_sim.core.systems.health.errors import (
    HealthValidationError,
    InvalidCurrentHealthError,
    InvalidMaxHealthError,
)
from genshin_sim.core.systems.health.models import (
    CharacterDamageApplication,
    CharacterHealingApplication,
    CharacterHealthChangeResult,
    CharacterHpDeduction,
    CharacterMaxHpReconcileResult,
    HealthChangeKind,
    validate_health_float,
    validate_non_negative_health_float,
)
from genshin_sim.core.systems.health.store import CharacterHealthStore


class AttributeResolverLike(Protocol):
    def resolve(
        self,
        query: AttributeQuery,
        *,
        options: AttributeResolveOptions | None = None,
    ) -> AttributeResolution: ...


class HealthRuntime:
    """角色生命值的只读查询与受控写入口。"""

    def __init__(
        self,
        attribute_resolver: AttributeResolver | AttributeResolverLike,
        character_health_store: CharacterHealthStore,
        event_engine: EventEngine,
    ) -> None:
        self.attribute_resolver = attribute_resolver
        self.character_health_store = character_health_store
        self.event_engine = event_engine

    def get_current_hp(self, character_ref: AttributeSubjectRef) -> float:
        return self.character_health_store.require(character_ref).current_hp

    def get_max_hp(self, character_ref: AttributeSubjectRef, frame: int) -> float:
        _validate_frame(frame)
        self.character_health_store.require(character_ref)
        try:
            resolution = self.attribute_resolver.resolve(
                AttributeQuery(character_ref, STAT_HP_MAX, frame=frame),
                options=AttributeResolveOptions(trace_level=TraceLevel.NONE),
            )
        except Exception as exc:
            raise InvalidMaxHealthError(f"无法解析角色最大生命：{exc}") from exc
        return _validate_max_hp(resolution.final_value)

    def get_hp_ratio(self, character_ref: AttributeSubjectRef, frame: int) -> float:
        max_hp = self.get_max_hp(character_ref, frame)
        current_hp = self.get_current_hp(character_ref)
        _validate_current_hp(current_hp, max_hp)
        return current_hp / max_hp

    def is_zero(self, character_ref: AttributeSubjectRef) -> bool:
        return self.character_health_store.require(character_ref).is_zero

    def apply_damage(self, request: CharacterDamageApplication) -> CharacterHealthChangeResult:
        health, hp_before, max_hp = self._prepare_commit(request.target_ref, request.frame)
        requested_amount = request.amount
        effective_amount = min(requested_amount, hp_before)
        hp_after = _normalize_zero(hp_before - effective_amount)
        unapplied_amount = _normalize_zero(requested_amount - effective_amount)
        result = CharacterHealthChangeResult(
            change_id=request.change_id,
            frame=request.frame,
            change_kind=HealthChangeKind.DAMAGE,
            target_ref=request.target_ref,
            source_ref=request.source_ref,
            source_context=request.source_context,
            requested_amount=requested_amount,
            effective_amount=effective_amount,
            unapplied_amount=unapplied_amount,
            hp_before=hp_before,
            hp_after=hp_after,
            max_hp=max_hp,
            tags=request.tags,
        )
        health.current_hp = result.hp_after
        self._publish_health_changed(result)
        return result

    def apply_healing(self, request: CharacterHealingApplication) -> CharacterHealthChangeResult:
        health, hp_before, max_hp = self._prepare_commit(request.target_ref, request.frame)
        requested_amount = request.amount
        missing_hp = max_hp - hp_before
        effective_amount = min(requested_amount, missing_hp)
        hp_after = _normalize_zero(hp_before + effective_amount)
        unapplied_amount = _normalize_zero(requested_amount - effective_amount)
        result = CharacterHealthChangeResult(
            change_id=request.change_id,
            frame=request.frame,
            change_kind=HealthChangeKind.HEALING,
            target_ref=request.target_ref,
            source_ref=request.source_ref,
            source_context=request.source_context,
            requested_amount=requested_amount,
            effective_amount=effective_amount,
            unapplied_amount=unapplied_amount,
            hp_before=hp_before,
            hp_after=hp_after,
            max_hp=max_hp,
            tags=request.tags,
        )
        health.current_hp = result.hp_after
        self._publish_health_changed(result)
        return result

    def deduct_hp(self, request: CharacterHpDeduction) -> CharacterHealthChangeResult:
        health, hp_before, max_hp = self._prepare_commit(request.target_ref, request.frame)
        minimum_remaining_hp = _validate_minimum_remaining_hp(
            request.minimum_remaining_hp,
            max_hp,
        )
        requested_amount = request.amount
        available = max(0.0, hp_before - minimum_remaining_hp)
        effective_amount = min(requested_amount, available)
        hp_after = _normalize_zero(hp_before - effective_amount)
        unapplied_amount = _normalize_zero(requested_amount - effective_amount)
        result = CharacterHealthChangeResult(
            change_id=request.change_id,
            frame=request.frame,
            change_kind=HealthChangeKind.HP_DEDUCTION,
            target_ref=request.target_ref,
            source_ref=request.source_ref,
            source_context=request.source_context,
            requested_amount=requested_amount,
            effective_amount=effective_amount,
            unapplied_amount=unapplied_amount,
            hp_before=hp_before,
            hp_after=hp_after,
            max_hp=max_hp,
            minimum_remaining_hp=minimum_remaining_hp,
            tags=request.tags,
        )
        health.current_hp = result.hp_after
        self._publish_health_changed(result)
        return result

    def reconcile_max_hp(
        self,
        character_ref: AttributeSubjectRef,
        old_max_hp: float,
        new_max_hp: float,
        frame: int,
    ) -> CharacterMaxHpReconcileResult:
        _validate_frame(frame)
        old_max_hp = _validate_max_hp(old_max_hp, field_name="old_max_hp")
        new_max_hp = _validate_max_hp(new_max_hp, field_name="new_max_hp")
        health = self.character_health_store.require(character_ref)
        hp_before = _validate_current_hp(health.current_hp, old_max_hp)
        hp_after = _normalize_zero((hp_before / old_max_hp) * new_max_hp)
        result = CharacterMaxHpReconcileResult(
            frame=frame,
            target_ref=character_ref,
            old_max_hp=old_max_hp,
            new_max_hp=new_max_hp,
            hp_before=hp_before,
            hp_after=hp_after,
        )
        health.current_hp = result.hp_after
        if old_max_hp != new_max_hp:
            self.event_engine.publish(
                GameEvent(
                    event_type=EventType.CHARACTER_MAX_HP_CHANGED,
                    frame=frame,
                    payload=CharacterMaxHpChangedPayload(result),
                    source=self,
                )
            )
        return result

    def _prepare_commit(
        self,
        character_ref: AttributeSubjectRef,
        frame: int,
    ) -> tuple[HealthState, float, float]:
        _validate_frame(frame)
        health = self.character_health_store.require(character_ref)
        max_hp = self.get_max_hp(character_ref, frame)
        hp_before = _validate_current_hp(health.current_hp, max_hp)
        return health, hp_before, max_hp

    def _publish_health_changed(self, result: CharacterHealthChangeResult) -> None:
        if result.effective_amount <= 0:
            return
        self.event_engine.publish(
            GameEvent(
                event_type=EventType.CHARACTER_HEALTH_CHANGED,
                frame=result.frame,
                payload=CharacterHealthChangedPayload(result),
                source=self,
            )
        )


def _validate_frame(frame: int) -> None:
    if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
        raise HealthValidationError("frame 必须是非负整数")


def _validate_max_hp(value: float | int, *, field_name: str = "max_hp") -> float:
    max_hp = validate_health_float(value, field_name)
    if max_hp <= 0:
        raise InvalidMaxHealthError(f"{field_name} 必须是正数")
    return max_hp


def _validate_current_hp(current_hp: float | int, max_hp: float) -> float:
    value = validate_non_negative_health_float(current_hp, "current_hp")
    if value > max_hp:
        raise InvalidCurrentHealthError("当前生命值不能大于最大生命值")
    return value


def _validate_minimum_remaining_hp(value: float | int, max_hp: float) -> float:
    minimum = validate_non_negative_health_float(value, "minimum_remaining_hp")
    if minimum > max_hp:
        raise HealthValidationError("minimum_remaining_hp 不能大于最大生命")
    return minimum


def _normalize_zero(value: float) -> float:
    if value == 0.0:
        return 0.0
    return value
