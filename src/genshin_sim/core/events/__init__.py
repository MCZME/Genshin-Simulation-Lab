"""事件模型、事件分发和事件处理协议。"""

from genshin_sim.core.events.categories import (
    EVENT_CATEGORY_SPECS,
    EventCategory,
    EventCategorySpec,
    get_event_category_spec,
)
from genshin_sim.core.events.engine import (
    EventBus,
    EventCallback,
    EventEngine,
    EventRecordFilter,
    EventSubscriber,
)
from genshin_sim.core.events.handlers import EventHandler
from genshin_sim.core.events.models import GameEvent
from genshin_sim.core.events.payloads import (
    CharacterHealthChangedPayload,
    CharacterMaxHpChangedPayload,
    DamageResolvedPayload,
    EmptyPayload,
    EventPayload,
    InputKeyReceivedPayload,
    InputSessionBoundaryPayload,
    SimulationEndedPayload,
)
from genshin_sim.core.events.specs import (
    EVENT_SPECS,
    EventSpec,
    get_event_spec,
)
from genshin_sim.core.events.types import EventType

__all__ = [
    "EVENT_CATEGORY_SPECS",
    "EVENT_SPECS",
    "EventBus",
    "EventCallback",
    "EventCategory",
    "EventCategorySpec",
    "EventEngine",
    "EventHandler",
    "EmptyPayload",
    "EventPayload",
    "EventSpec",
    "EventRecordFilter",
    "EventSubscriber",
    "EventType",
    "CharacterHealthChangedPayload",
    "CharacterMaxHpChangedPayload",
    "DamageResolvedPayload",
    "GameEvent",
    "InputKeyReceivedPayload",
    "InputSessionBoundaryPayload",
    "SimulationEndedPayload",
    "get_event_category_spec",
    "get_event_spec",
]
