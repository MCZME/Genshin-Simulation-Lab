from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class EventCategory(Enum):
    """事件语义分类。

    分类用于描述事件在运行时中的作用，而不是具体业务领域。
    具体事件类型通过 EventSpec 绑定载荷类型与运行时规则。
    """

    BOUNDARY = auto()
    INTENT = auto()
    INTERCEPT = auto()
    FACT = auto()
    STATE_CHANGE = auto()
    AUDIT = auto()


@dataclass(frozen=True, slots=True)
class EventCategorySpec:
    """事件分类的默认规则。"""

    cancelable: bool
    mutable_payload: bool
    record_by_default: bool
    result_committed: bool
    mechanic_driver: bool


EVENT_CATEGORY_SPECS: dict[EventCategory, EventCategorySpec] = {
    EventCategory.BOUNDARY: EventCategorySpec(
        cancelable=False,
        mutable_payload=False,
        record_by_default=False,
        result_committed=True,
        mechanic_driver=False,
    ),
    EventCategory.INTENT: EventCategorySpec(
        cancelable=False,
        mutable_payload=False,
        record_by_default=True,
        result_committed=False,
        mechanic_driver=False,
    ),
    EventCategory.INTERCEPT: EventCategorySpec(
        cancelable=True,
        mutable_payload=True,
        record_by_default=False,
        result_committed=False,
        mechanic_driver=True,
    ),
    EventCategory.FACT: EventCategorySpec(
        cancelable=False,
        mutable_payload=False,
        record_by_default=True,
        result_committed=True,
        mechanic_driver=True,
    ),
    EventCategory.STATE_CHANGE: EventCategorySpec(
        cancelable=False,
        mutable_payload=False,
        record_by_default=True,
        result_committed=True,
        mechanic_driver=True,
    ),
    EventCategory.AUDIT: EventCategorySpec(
        cancelable=False,
        mutable_payload=False,
        record_by_default=False,
        result_committed=True,
        mechanic_driver=False,
    ),
}


def get_event_category_spec(category: EventCategory) -> EventCategorySpec:
    """返回事件分类的默认规则。"""

    return EVENT_CATEGORY_SPECS[category]
