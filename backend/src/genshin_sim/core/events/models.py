from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.core.events.payloads import EventPayload
from genshin_sim.core.events.specs import get_event_spec
from genshin_sim.core.events.types import EventType


@dataclass(slots=True)
class GameEvent:
    """一次仿真事件。

    ``record`` 为 None 时使用事件类型的默认记录规则。
    """

    event_type: EventType
    frame: int
    payload: EventPayload
    source: object | None = None
    cancelled: bool = False
    record: bool | None = None

    def __post_init__(self) -> None:
        expected_payload_type = get_event_spec(self.event_type).payload_type
        if not isinstance(self.payload, expected_payload_type):
            msg = (
                f"{self.event_type.name} 事件载荷类型错误："
                f"期望 {expected_payload_type.__name__}，"
                f"实际 {self.payload.__class__.__name__}"
            )
            raise TypeError(msg)

    @property
    def should_record(self) -> bool:
        if self.record is not None:
            return self.record
        return get_event_spec(self.event_type).effective_record_by_default

    def cancel(self) -> None:
        if not get_event_spec(self.event_type).effective_cancelable:
            msg = f"{self.event_type.name} 事件不允许取消"
            raise RuntimeError(msg)
        self.cancelled = True
