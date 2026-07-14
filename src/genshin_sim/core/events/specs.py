from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.core.events.categories import EventCategory, get_event_category_spec
from genshin_sim.core.events.payloads import (
    BuffAppliedPayload,
    BuffRemovedPayload,
    CharacterHealthChangedPayload,
    CharacterMaxHpChangedPayload,
    DamageAppliedPayload,
    DamageResolvedPayload,
    EmptyPayload,
    HealingResolvedPayload,
    InputKeyReceivedPayload,
    InputSessionBoundaryPayload,
    ShieldAbsorptionResolvedPayload,
    ShieldCapacityChangedPayload,
    ShieldGrantedPayload,
    ShieldRemovedPayload,
    SimulationEndedPayload,
)
from genshin_sim.core.events.types import EventType


@dataclass(frozen=True, slots=True)
class EventSpec:
    """具体事件类型的运行时元信息。

    布尔规则为 None 时继承事件分类的默认规则。
    """

    category: EventCategory
    payload_type: type[object]
    cancelable: bool | None = None
    mutable_payload: bool | None = None
    record_by_default: bool | None = None
    result_committed: bool | None = None
    mechanic_driver: bool | None = None

    @property
    def effective_cancelable(self) -> bool:
        if self.cancelable is not None:
            return self.cancelable
        return get_event_category_spec(self.category).cancelable

    @property
    def effective_mutable_payload(self) -> bool:
        if self.mutable_payload is not None:
            return self.mutable_payload
        return get_event_category_spec(self.category).mutable_payload

    @property
    def effective_record_by_default(self) -> bool:
        if self.record_by_default is not None:
            return self.record_by_default
        return get_event_category_spec(self.category).record_by_default

    @property
    def effective_result_committed(self) -> bool:
        if self.result_committed is not None:
            return self.result_committed
        return get_event_category_spec(self.category).result_committed

    @property
    def effective_mechanic_driver(self) -> bool:
        if self.mechanic_driver is not None:
            return self.mechanic_driver
        return get_event_category_spec(self.category).mechanic_driver


EVENT_SPECS: dict[EventType, EventSpec] = {
    EventType.SIMULATION_STARTED: EventSpec(
        category=EventCategory.BOUNDARY,
        payload_type=EmptyPayload,
        record_by_default=True,
    ),
    EventType.SIMULATION_ENDED: EventSpec(
        category=EventCategory.BOUNDARY,
        payload_type=SimulationEndedPayload,
        record_by_default=True,
    ),
    EventType.FRAME_STARTED: EventSpec(
        category=EventCategory.BOUNDARY,
        payload_type=EmptyPayload,
    ),
    EventType.FRAME_ENDED: EventSpec(
        category=EventCategory.BOUNDARY,
        payload_type=EmptyPayload,
    ),
    EventType.INPUT_KEY_RECEIVED: EventSpec(
        category=EventCategory.INTENT,
        payload_type=InputKeyReceivedPayload,
    ),
    EventType.INPUT_SESSION_BOUNDARY_REACHED: EventSpec(
        category=EventCategory.INTENT,
        payload_type=InputSessionBoundaryPayload,
    ),
    EventType.DAMAGE_RESOLVED: EventSpec(
        category=EventCategory.FACT,
        payload_type=DamageResolvedPayload,
    ),
    EventType.HEALING_RESOLVED: EventSpec(
        category=EventCategory.FACT,
        payload_type=HealingResolvedPayload,
    ),
    EventType.CHARACTER_HEALTH_CHANGED: EventSpec(
        category=EventCategory.STATE_CHANGE,
        payload_type=CharacterHealthChangedPayload,
    ),
    EventType.CHARACTER_MAX_HP_CHANGED: EventSpec(
        category=EventCategory.AUDIT,
        payload_type=CharacterMaxHpChangedPayload,
    ),
    EventType.SHIELD_GRANTED: EventSpec(
        category=EventCategory.STATE_CHANGE,
        payload_type=ShieldGrantedPayload,
    ),
    EventType.SHIELD_CAPACITY_CHANGED: EventSpec(
        category=EventCategory.STATE_CHANGE,
        payload_type=ShieldCapacityChangedPayload,
    ),
    EventType.SHIELD_REMOVED: EventSpec(
        category=EventCategory.STATE_CHANGE,
        payload_type=ShieldRemovedPayload,
    ),
    EventType.SHIELD_ABSORPTION_RESOLVED: EventSpec(
        category=EventCategory.FACT,
        payload_type=ShieldAbsorptionResolvedPayload,
    ),
    EventType.DAMAGE_APPLIED: EventSpec(
        category=EventCategory.FACT,
        payload_type=DamageAppliedPayload,
    ),
    EventType.BUFF_APPLIED: EventSpec(
        category=EventCategory.STATE_CHANGE,
        payload_type=BuffAppliedPayload,
    ),
    EventType.BUFF_REMOVED: EventSpec(
        category=EventCategory.STATE_CHANGE,
        payload_type=BuffRemovedPayload,
    ),
}


def get_event_spec(event_type: EventType) -> EventSpec:
    """返回具体事件类型的运行时元信息。"""

    return EVENT_SPECS[event_type]
