import pytest

from genshin_sim.core.events import EventType, GameEvent, InputKeyConsumedPayload
from genshin_sim.core.simulation import SimulationContext, get_context


def test_context_manager_sets_and_restores_active_context():
    outer = SimulationContext()
    inner = SimulationContext()

    with outer:
        assert get_context() is outer
        with inner:
            assert get_context() is inner
        assert get_context() is outer


def test_get_context_raises_without_active_context():
    with pytest.raises(RuntimeError, match="没有活动的 SimulationContext"):
        get_context()


def test_context_starts_without_space_runtime():
    ctx = SimulationContext()

    assert ctx.space_runtime is None


def test_advance_frame_clears_previous_frame_events():
    ctx = SimulationContext()
    ctx.events.publish(
        GameEvent(
            EventType.INPUT_KEY_CONSUMED,
            frame=0,
            payload=InputKeyConsumedPayload(key="keyboard.e", phase="press"),
        )
    )

    assert len(ctx.events.frame_events) == 1

    frame = ctx.advance_frame()

    assert frame == 1
    assert ctx.current_frame == 1
    assert ctx.events.frame_events == ()


def test_reset_clears_clock_and_frame_events():
    ctx = SimulationContext()
    ctx.advance_frame(3)
    ctx.events.publish(
        GameEvent(
            EventType.INPUT_KEY_CONSUMED,
            frame=3,
            payload=InputKeyConsumedPayload(key="keyboard.e", phase="press"),
        )
    )

    assert ctx.current_frame == 3
    assert len(ctx.events.frame_events) == 1

    ctx.reset()

    assert ctx.current_frame == 0
    assert ctx.events.frame_events == ()


def test_register_system_initializes_and_allows_lookup():
    class DemoSystem:
        def __init__(self):
            self.context = None

        def initialize(self, context: SimulationContext) -> None:
            self.context = context

    ctx = SimulationContext()
    system = ctx.register_system(DemoSystem())

    assert system.context is ctx
    assert ctx.get_system(DemoSystem) is system
    assert ctx.get_system("DemoSystem") is system
