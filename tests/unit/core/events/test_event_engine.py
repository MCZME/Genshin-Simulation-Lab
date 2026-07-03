from genshin_sim.core.events import EventEngine, EventType, GameEvent


def test_publish_dispatches_subscribers():
    engine = EventEngine()
    received: list[GameEvent] = []

    engine.subscribe(EventType.AFTER_DAMAGE, received.append)
    event = GameEvent(EventType.AFTER_DAMAGE, frame=12, data={"damage": 100})

    engine.publish(event)

    assert received == [event]


def test_unsubscribe_removes_handler():
    engine = EventEngine()
    received: list[GameEvent] = []

    engine.subscribe(EventType.AFTER_DAMAGE, received.append)
    engine.unsubscribe(EventType.AFTER_DAMAGE, received.append)

    engine.publish(GameEvent(EventType.AFTER_DAMAGE, frame=1))

    assert received == []


def test_object_handler_can_receive_event():
    class Handler:
        def __init__(self):
            self.received: list[GameEvent] = []

        def handle_event(self, event: GameEvent) -> None:
            self.received.append(event)

    engine = EventEngine()
    handler = Handler()
    event = GameEvent(EventType.AFTER_HEAL, frame=3)

    engine.subscribe(EventType.AFTER_HEAL, handler)
    engine.publish(event)

    assert handler.received == [event]


def test_cancelled_event_stops_later_handlers():
    engine = EventEngine()
    calls: list[str] = []

    def first(event: GameEvent) -> None:
        calls.append("first")
        event.cancel()

    def second(event: GameEvent) -> None:
        calls.append("second")

    engine.subscribe(EventType.BEFORE_DAMAGE, first)
    engine.subscribe(EventType.BEFORE_DAMAGE, second)

    engine.publish(GameEvent(EventType.BEFORE_DAMAGE, frame=1))

    assert calls == ["first"]


def test_frame_events_use_event_record_flag():
    engine = EventEngine()
    recorded = GameEvent(EventType.AFTER_DAMAGE, frame=1)
    ignored = GameEvent(EventType.FRAME_END, frame=1, record=False)

    engine.publish(recorded)
    engine.publish(ignored)

    assert engine.frame_events == (recorded,)

    engine.clear_frame_events()

    assert engine.frame_events == ()
