from __future__ import annotations

from collections.abc import Callable

from genshin_sim.core.events.types import EventHandler, EventType, GameEvent

EventCallback = Callable[[GameEvent], None]
EventSubscriber = EventCallback | EventHandler
EventRecordFilter = Callable[[GameEvent], bool]


class EventEngine:
    """实例级事件分发器。

    事件分发器只负责内存中的订阅、发布和帧缓冲，不负责日志、持久化或 UI。
    """

    def __init__(
        self,
        record_filter: EventRecordFilter | None = None,
    ) -> None:
        self._handlers: dict[EventType, list[EventSubscriber]] = {}
        self._frame_events: list[GameEvent] = []
        self._record_filter = record_filter or (lambda event: event.record)

    @property
    def frame_events(self) -> tuple[GameEvent, ...]:
        """当前帧中被记录的事件。"""

        return tuple(self._frame_events)

    def subscribe(self, event_type: EventType, handler: EventSubscriber) -> None:
        handlers = self._handlers.setdefault(event_type, [])
        if handler not in handlers:
            handlers.append(handler)

    def unsubscribe(self, event_type: EventType, handler: EventSubscriber) -> None:
        handlers = self._handlers.get(event_type)
        if not handlers:
            return
        if handler in handlers:
            handlers.remove(handler)
        if not handlers:
            del self._handlers[event_type]

    def publish(self, event: GameEvent) -> None:
        if self._record_filter(event):
            self._frame_events.append(event)

        handlers = self._handlers.get(event.event_type, []).copy()
        for handler in handlers:
            if event.cancelled:
                return
            self._dispatch(handler, event)

    def clear_frame_events(self) -> None:
        self._frame_events.clear()

    def clear_handlers(self) -> None:
        self._handlers.clear()

    def clear(self) -> None:
        self.clear_handlers()
        self.clear_frame_events()

    def _dispatch(self, handler: EventSubscriber, event: GameEvent) -> None:
        if isinstance(handler, EventHandler):
            handler.handle_event(event)
            return
        handler(event)


EventBus = EventEngine
