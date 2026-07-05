from genshin_sim.core.events import (
    EmptyPayload,
    EventEngine,
    EventType,
    GameEvent,
    InputKeyConsumedPayload,
)


def test_publish_dispatches_subscribers():
    engine = EventEngine()
    received: list[GameEvent] = []

    engine.subscribe(EventType.INPUT_KEY_CONSUMED, received.append)
    event = GameEvent(
        EventType.INPUT_KEY_CONSUMED,
        frame=12,
        payload=InputKeyConsumedPayload(key="keyboard.e", phase="press"),
    )

    engine.publish(event)

    assert received == [event]


def test_unsubscribe_removes_handler():
    engine = EventEngine()
    received: list[GameEvent] = []

    engine.subscribe(EventType.INPUT_KEY_CONSUMED, received.append)
    engine.unsubscribe(EventType.INPUT_KEY_CONSUMED, received.append)

    engine.publish(
        GameEvent(
            EventType.INPUT_KEY_CONSUMED,
            frame=1,
            payload=InputKeyConsumedPayload(key="keyboard.e", phase="press"),
        )
    )

    assert received == []


def test_object_handler_can_receive_event():
    class Handler:
        def __init__(self):
            self.received: list[GameEvent] = []

        def handle_event(self, event: GameEvent) -> None:
            self.received.append(event)

    engine = EventEngine()
    handler = Handler()
    event = GameEvent(EventType.SIMULATION_STARTED, frame=3, payload=EmptyPayload())

    engine.subscribe(EventType.SIMULATION_STARTED, handler)
    engine.publish(event)

    assert handler.received == [event]


def test_cancelled_event_stops_later_handlers():
    engine = EventEngine()
    calls: list[str] = []

    def first(event: GameEvent) -> None:
        calls.append("first")
        event.cancelled = True

    def second(event: GameEvent) -> None:
        calls.append("second")

    engine.subscribe(EventType.FRAME_STARTED, first)
    engine.subscribe(EventType.FRAME_STARTED, second)

    engine.publish(GameEvent(EventType.FRAME_STARTED, frame=1, payload=EmptyPayload()))

    assert calls == ["first"]


def test_frame_events_use_event_record_flag():
    engine = EventEngine()
    recorded = GameEvent(
        EventType.INPUT_KEY_CONSUMED,
        frame=1,
        payload=InputKeyConsumedPayload(key="keyboard.e", phase="press"),
    )
    ignored = GameEvent(
        EventType.FRAME_ENDED,
        frame=1,
        payload=EmptyPayload(),
        record=False,
    )

    engine.publish(recorded)
    engine.publish(ignored)

    assert engine.frame_events == (recorded,)

    engine.clear_frame_events()

    assert engine.frame_events == ()
