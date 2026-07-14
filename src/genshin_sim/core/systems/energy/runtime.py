from __future__ import annotations

import math
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Protocol

from genshin_sim.core.attributes import (
    AttributeQuery,
    AttributeResolveOptions,
    AttributeSubjectRef,
    TraceLevel,
)
from genshin_sim.core.attributes.keys import STAT_ENERGY_RECHARGE
from genshin_sim.core.events import EventEngine, EventType, GameEvent
from genshin_sim.core.systems.energy.errors import (
    EnergyPlanConflictError,
    EnergyReentrancyError,
    InsufficientEnergyAtSpendError,
    InvalidEnergyAttributeError,
    UnsupportedEnergyResourceError,
)
from genshin_sim.core.systems.energy.formulas import (
    element_multiplier,
    field_multiplier,
    pickup_kind_multiplier,
    recharge_multiplier,
)
from genshin_sim.core.systems.energy.models import (
    CharacterEnergyChangeResult,
    DrainEnergyRequest,
    EnergyChangeKind,
    EnergyPickupRecord,
    EnergyPickupSettlementResult,
    EnergyRecipientResolution,
    EnergyRecipientStatus,
    RestoreEnergyRequest,
    SpawnEnergyPickupRequest,
    SpendBurstEnergyRequest,
)
from genshin_sim.core.systems.energy.queue import EnergyTransitQueue
from genshin_sim.core.systems.energy.store import CharacterEnergyStore


class AttributeResolverPort(Protocol):
    def resolve(
        self,
        query: AttributeQuery,
        *,
        options: AttributeResolveOptions | None = None,
    ) -> EnergyRechargeResolution: ...


class EnergyRechargeResolution(Protocol):
    @property
    def final_value(self) -> float: ...


class TeamCharacterReadPort(Protocol):
    slot: int
    combat_entity_id: str


class TeamReadPort(Protocol):
    @property
    def team_size(self) -> int: ...

    @property
    def active_slot(self) -> int: ...

    @property
    def characters(self) -> tuple[TeamCharacterReadPort, ...]: ...


class EnergyReadPort(Protocol):
    def get_current_energy(self, character_ref: AttributeSubjectRef) -> float: ...

    def get_capacity(self, character_ref: AttributeSubjectRef) -> float: ...

    def has_elemental_energy_resource(self, character_ref: AttributeSubjectRef) -> bool: ...

    def is_burst_ready(self, character_ref: AttributeSubjectRef) -> bool: ...


class EnergyRuntime:
    """元素能量唯一写入口，负责在途载体与直接能量变化。"""

    def __init__(
        self,
        attribute_resolver: AttributeResolverPort,
        team_state: TeamReadPort,
        energy_store: CharacterEnergyStore,
        transit_queue: EnergyTransitQueue,
        event_engine: EventEngine,
    ) -> None:
        self.attribute_resolver = attribute_resolver
        self.team_state = team_state
        self.energy_store = energy_store
        self.transit_queue = transit_queue
        self.event_engine = event_engine
        self._spawn_order = 0
        self._mutation_active = False
        self._publishing_events = False
        self._pending_events: list[GameEvent] = []

    def get_current_energy(self, character_ref: AttributeSubjectRef) -> float:
        return self.energy_store.current_energy(character_ref)

    def get_capacity(self, character_ref: AttributeSubjectRef) -> float:
        return self.energy_store.require_profile(character_ref).capacity

    def has_elemental_energy_resource(self, character_ref: AttributeSubjectRef) -> bool:
        return self.get_capacity(character_ref) > 0.0

    def is_burst_ready(self, character_ref: AttributeSubjectRef) -> bool:
        capacity = self.get_capacity(character_ref)
        return capacity > 0.0 and self.get_current_energy(character_ref) >= capacity

    def spawn_pickup(self, request: SpawnEnergyPickupRequest) -> EnergyPickupRecord:
        with self._mutation_scope():
            record = EnergyPickupRecord(
                pickup_id=f"energy-pickup:{request.request_id}",
                request_id=request.request_id,
                created_frame=request.frame,
                settle_frame=request.frame + request.travel_frames,
                pickup_kind=request.pickup_kind,
                element=request.element,
                count=request.count,
                source_ref=request.source_ref,
                source_context=request.source_context,
                tags=request.tags,
                spawn_order=self._spawn_order,
            )
            self.transit_queue.enqueue(record)
            self._spawn_order += 1
            from genshin_sim.core.events.payloads import EnergyPickupSpawnedPayload

            self._emit_event(
                GameEvent(
                    EventType.ENERGY_PICKUP_SPAWNED,
                    request.frame,
                    EnergyPickupSpawnedPayload(record),
                    self,
                )
            )
        return record

    def restore(self, request: RestoreEnergyRequest) -> CharacterEnergyChangeResult:
        return self._apply_direct(request, EnergyChangeKind.DIRECT_RESTORE)

    def drain(self, request: DrainEnergyRequest) -> CharacterEnergyChangeResult:
        return self._apply_direct(request, EnergyChangeKind.DIRECT_DRAIN)

    def spend_burst(self, request: SpendBurstEnergyRequest) -> CharacterEnergyChangeResult:
        with self._mutation_scope():
            profile = self.energy_store.require_profile(request.target_ref)
            if profile.capacity <= 0.0:
                raise UnsupportedEnergyResourceError(
                    f"角色不使用标准元素能量：{request.target_ref.entity_id}"
                )
            before = self.energy_store.current_energy(request.target_ref)
            if before < profile.capacity:
                detail = (
                    f"change_id={request.change_id}, action={request.action_instance_id}, "
                    f"target={request.target_ref.entity_id}"
                )
                raise InsufficientEnergyAtSpendError(f"爆发扣能不足：{detail}")
            result = CharacterEnergyChangeResult(
                change_id=request.change_id,
                frame=request.frame,
                change_kind=EnergyChangeKind.BURST_SPEND,
                target_ref=request.target_ref,
                source_ref=None,
                source_context=request.source_context,
                requested_amount=profile.capacity,
                effective_amount=profile.capacity,
                unapplied_amount=0.0,
                energy_before=before,
                energy_after=0.0,
                capacity=profile.capacity,
                tags=request.tags,
            )
            self._commit_direct(f"direct:{request.change_id}", result)
        return result

    def update_frame(self, context, frame: int) -> None:
        del context
        self._ensure_can_write()
        for record in self.transit_queue.due(frame):
            self.settle_pickup(record, frame)

    def is_idle(self) -> bool:
        return self.transit_queue.is_empty()

    def settle_pickup(
        self, record: EnergyPickupRecord, frame: int | None = None
    ) -> EnergyPickupSettlementResult:
        with self._mutation_scope():
            return self._settle_pickup_unchecked(record, frame)

    def _settle_pickup_unchecked(
        self, record: EnergyPickupRecord, frame: int | None
    ) -> EnergyPickupSettlementResult:
        settled_frame = record.settle_frame if frame is None else frame
        if settled_frame < record.settle_frame:
            raise EnergyPlanConflictError(f"pickup 尚未到达：{record.pickup_id}")
        expected_store_version = self.energy_store.version
        expected_queue_version = self.transit_queue.version
        active_slot = self.team_state.active_slot
        team_size = self.team_state.team_size
        expected_energy: dict[AttributeSubjectRef, float] = {}
        new_energy: dict[AttributeSubjectRef, float] = {}
        recipients: list[EnergyRecipientResolution] = []

        for character in self.team_state.characters:
            slot = character.slot
            ref = AttributeSubjectRef.character(character.combat_entity_id)
            profile = self.energy_store.require_profile(ref)
            before = self.energy_store.current_energy(ref)
            is_active = slot == active_slot
            if profile.capacity == 0.0:
                recipients.append(
                    EnergyRecipientResolution(
                        target_ref=ref,
                        slot=slot,
                        status=EnergyRecipientStatus.NO_ELEMENTAL_ENERGY_RESOURCE,
                        is_active=is_active,
                        character_element=profile.element,
                        pickup_element=record.element,
                        pickup_kind=record.pickup_kind,
                        count=record.count,
                        kind_multiplier=0.0,
                        element_multiplier=0.0,
                        field_multiplier=0.0,
                        recharge_bonus=None,
                        recharge_multiplier=None,
                        base_amount=0.0,
                        requested_amount=0.0,
                        change_result=None,
                    )
                )
                continue
            kind = pickup_kind_multiplier(record.pickup_kind)
            element = element_multiplier(record.element, profile.element)
            field = field_multiplier(is_active=is_active, team_size=team_size)
            base = _finite_non_negative(record.count * kind * element * field, "base_amount")
            bonus = self._resolve_recharge_bonus(ref, settled_frame)
            recharge = recharge_multiplier(bonus)
            requested = _finite_non_negative(base * recharge, "requested_amount")
            effective = min(requested, profile.capacity - before)
            after = _normalize_zero(before + effective)
            unapplied = _normalize_zero(requested - effective)
            change = CharacterEnergyChangeResult(
                change_id=f"{record.pickup_id}:{ref.entity_id}",
                frame=settled_frame,
                change_kind=EnergyChangeKind.PICKUP_RESTORE,
                target_ref=ref,
                source_ref=record.source_ref,
                source_context=record.source_context,
                requested_amount=requested,
                effective_amount=effective,
                unapplied_amount=unapplied,
                energy_before=before,
                energy_after=after,
                capacity=profile.capacity,
                tags=record.tags,
            )
            expected_energy[ref] = before
            new_energy[ref] = after
            recipients.append(
                EnergyRecipientResolution(
                    target_ref=ref,
                    slot=slot,
                    status=EnergyRecipientStatus.APPLIED
                    if effective > 0
                    else EnergyRecipientStatus.CAPPED,
                    is_active=is_active,
                    character_element=profile.element,
                    pickup_element=record.element,
                    pickup_kind=record.pickup_kind,
                    count=record.count,
                    kind_multiplier=kind,
                    element_multiplier=element,
                    field_multiplier=field,
                    recharge_bonus=bonus,
                    recharge_multiplier=recharge,
                    base_amount=base,
                    requested_amount=requested,
                    change_result=change,
                )
            )
        result = EnergyPickupSettlementResult(
            record, settled_frame, active_slot, team_size, tuple(recipients)
        )
        self.energy_store.assert_can_commit(
            operation_id=f"pickup-settlement:{record.pickup_id}",
            expected_version=expected_store_version,
            expected_energy=expected_energy,
        )
        self.transit_queue.assert_current(record, expected_queue_version)
        self.energy_store.commit_prevalidated(
            operation_id=f"pickup-settlement:{record.pickup_id}",
            new_energy=new_energy,
        )
        self.transit_queue.remove_prevalidated(record)
        self._publish_pickup_settlement(result)
        return result

    def snapshot(self, frame: int):
        from genshin_sim.core.systems.energy.snapshots import (
            CharacterEnergySnapshot,
            EnergySnapshot,
        )

        snapshots = []
        for character in self.team_state.characters:
            ref = AttributeSubjectRef.character(character.combat_entity_id)
            profile = self.energy_store.require_profile(ref)
            snapshots.append(
                CharacterEnergySnapshot(
                    character_ref=ref,
                    character_key=profile.character_key,
                    element=profile.element,
                    current_energy=self.get_current_energy(ref),
                    capacity=profile.capacity,
                    burst_ready=self.is_burst_ready(ref),
                )
            )
        return EnergySnapshot(
            frame=frame,
            characters=tuple(snapshots),
            pending_pickups=tuple(record.to_dict() for record in self.transit_queue.records),
        )

    def _apply_direct(
        self, request: RestoreEnergyRequest | DrainEnergyRequest, kind: EnergyChangeKind
    ) -> CharacterEnergyChangeResult:
        with self._mutation_scope():
            profile = self.energy_store.require_profile(request.target_ref)
            if profile.capacity <= 0.0:
                raise UnsupportedEnergyResourceError(
                    f"角色不使用标准元素能量：{request.target_ref.entity_id}"
                )
            before = self.energy_store.current_energy(request.target_ref)
            effective = (
                min(request.amount, profile.capacity - before)
                if kind is EnergyChangeKind.DIRECT_RESTORE
                else min(request.amount, before)
            )
            after = _normalize_zero(
                before + effective
                if kind is EnergyChangeKind.DIRECT_RESTORE
                else before - effective
            )
            result = CharacterEnergyChangeResult(
                change_id=request.change_id,
                frame=request.frame,
                change_kind=kind,
                target_ref=request.target_ref,
                source_ref=request.source_ref,
                source_context=request.source_context,
                requested_amount=request.amount,
                effective_amount=effective,
                unapplied_amount=_normalize_zero(request.amount - effective),
                energy_before=before,
                energy_after=after,
                capacity=profile.capacity,
                tags=request.tags,
            )
            self._commit_direct(f"direct:{request.change_id}", result)
        return result

    def _commit_direct(self, operation_id: str, result: CharacterEnergyChangeResult) -> None:
        expected = {result.target_ref: result.energy_before}
        self.energy_store.assert_can_commit(
            operation_id=operation_id,
            expected_version=self.energy_store.version,
            expected_energy=expected,
        )
        self.energy_store.commit_prevalidated(
            operation_id=operation_id, new_energy={result.target_ref: result.energy_after}
        )
        from genshin_sim.core.events.payloads import (
            CharacterEnergyChangedPayload,
            DirectEnergyChangeResolvedPayload,
        )

        self._emit_event(
            GameEvent(
                EventType.DIRECT_ENERGY_CHANGE_RESOLVED,
                result.frame,
                DirectEnergyChangeResolvedPayload(result),
                self,
            )
        )
        if result.effective_amount > 0:
            self._emit_event(
                GameEvent(
                    EventType.CHARACTER_ENERGY_CHANGED,
                    result.frame,
                    CharacterEnergyChangedPayload(result),
                    self,
                )
            )

    def _resolve_recharge_bonus(self, ref: AttributeSubjectRef, frame: int) -> float:
        try:
            resolution = self.attribute_resolver.resolve(
                AttributeQuery(ref, STAT_ENERGY_RECHARGE, frame),
                options=AttributeResolveOptions(trace_level=TraceLevel.NONE),
            )
            bonus = resolution.final_value
        except Exception as exc:
            raise InvalidEnergyAttributeError(
                f"无法解析 {ref.entity_id} 的 stat.energy_recharge：{exc}"
            ) from exc
        if (
            isinstance(bonus, bool)
            or not isinstance(bonus, int | float)
            or not math.isfinite(bonus)
        ):
            raise InvalidEnergyAttributeError(f"{ref.entity_id} 的 stat.energy_recharge 非法")
        return float(bonus)

    def _publish_pickup_settlement(self, result: EnergyPickupSettlementResult) -> None:
        from genshin_sim.core.events.payloads import (
            CharacterEnergyChangedPayload,
            EnergyPickupSettledPayload,
        )

        self._emit_event(
            GameEvent(
                EventType.ENERGY_PICKUP_SETTLED,
                result.settled_frame,
                EnergyPickupSettledPayload(result),
                self,
            )
        )
        for recipient in result.recipients:
            if recipient.change_result is not None and recipient.change_result.effective_amount > 0:
                self._emit_event(
                    GameEvent(
                        EventType.CHARACTER_ENERGY_CHANGED,
                        result.settled_frame,
                        CharacterEnergyChangedPayload(recipient.change_result),
                        self,
                    )
                )

    @contextmanager
    def _mutation_scope(self) -> Iterator[None]:
        self._ensure_can_write()
        self._mutation_active = True
        try:
            yield
        finally:
            self._mutation_active = False
            self._flush_pending_events()

    def _ensure_can_write(self) -> None:
        if self._mutation_active or self._publishing_events:
            raise EnergyReentrancyError("元素能量提交或事实事件发布期间不允许重入写入")

    def _emit_event(self, event: GameEvent) -> None:
        if self._mutation_active:
            self._pending_events.append(event)
            return
        self._publish_events((event,))

    def _flush_pending_events(self) -> None:
        events = tuple(self._pending_events)
        self._pending_events.clear()
        if events:
            self._publish_events(events)

    def _publish_events(self, events: tuple[GameEvent, ...]) -> None:
        if self._publishing_events:
            raise EnergyReentrancyError("元素能量事实事件发布期间不允许递归发布")
        self._publishing_events = True
        try:
            for event in events:
                self.event_engine.publish(event)
        finally:
            self._publishing_events = False


def _finite_non_negative(value: float, name: str) -> float:
    if not math.isfinite(value) or value < 0:
        raise InvalidEnergyAttributeError(f"{name} 必须是有限非负数")
    return _normalize_zero(value)


def _normalize_zero(value: float) -> float:
    return 0.0 if value == 0.0 else value
