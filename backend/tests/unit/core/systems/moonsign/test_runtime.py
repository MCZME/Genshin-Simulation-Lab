"""月兆运行时测试：动作触发、公式应用、覆盖与到期。"""

from __future__ import annotations

from types import SimpleNamespace

from genshin_sim.core.attributes import (
    STAT_ATK_TOTAL,
    STAT_DEF_TOTAL,
    STAT_ELEMENTAL_MASTERY,
    STAT_HP_MAX,
    AttributeSubjectRef,
)
from genshin_sim.core.elements import Element
from genshin_sim.core.events import EventEngine, EventType
from genshin_sim.core.systems.moonsign import (
    MoonsignLevel,
    MoonsignRuntime,
    MoonsignScaling,
    MoonsignStore,
)
from tests.helpers.events import make_action_started_event, make_event_context

_LOCAL_SCALING = {
    Element.PYRO: MoonsignScaling(divisor=100.0, ratio=0.01),
}
_LOCAL_CAP = 0.25


class _FakeResolver:
    def __init__(self, values: dict[str, float]) -> None:
        self.values = values

    def resolve(self, query, *, options=None):
        del options
        return SimpleNamespace(final_value=self.values[str(query.attribute_key)])


def _resolver(atk=2000.0, hp=30000.0, defense=2000.0, em=800.0) -> _FakeResolver:
    return _FakeResolver(
        {
            str(STAT_ATK_TOTAL): atk,
            str(STAT_HP_MAX): hp,
            str(STAT_DEF_TOTAL): defense,
            str(STAT_ELEMENTAL_MASTERY): em,
        }
    )


def _runtime(
    *,
    level: MoonsignLevel = MoonsignLevel.ASCENDANT,
    moonsign_slots: tuple[int, ...] = (2,),
    element_by_slot: dict[int, Element] | None = None,
) -> tuple[MoonsignRuntime, EventEngine]:
    store = MoonsignStore()
    store.set_level(
        level,
        tuple(AttributeSubjectRef.character(f"character:slot_{slot}") for slot in moonsign_slots),
    )
    events = EventEngine()
    runtime = MoonsignRuntime(
        store,
        events,
        _resolver(),
        _LOCAL_SCALING,
        cap=_LOCAL_CAP,
        duration_frames=1200,
        element_by_slot=element_by_slot or {1: Element.PYRO},
    )
    return runtime, events


def test_runtime_publishes_level_fact_once():
    runtime, events = _runtime()
    runtime.update_frame(make_event_context(1), 1)
    runtime.update_frame(make_event_context(2), 2)
    assert [event.event_type for event in events.frame_events] == [EventType.MOONSIGN_LEVEL_SET]


def test_runtime_skips_bonus_when_level_not_ascendant():
    runtime, _ = _runtime(level=MoonsignLevel.NASCENT)
    runtime.update_frame(
        make_event_context(10, (make_action_started_event(10, 1, "elemental_skill"),)),
        10,
    )
    assert runtime.lunar_reaction_bonus(10) == 0.0


def test_runtime_skips_bonus_for_non_ability_actions():
    runtime, _ = _runtime()
    runtime.update_frame(
        make_event_context(10, (make_action_started_event(10, 1, "normal_attack"),)),
        10,
    )
    assert runtime.lunar_reaction_bonus(10) == 0.0


def test_runtime_skips_bonus_for_moonsign_characters():
    runtime, _ = _runtime()
    runtime.update_frame(
        make_event_context(10, (make_action_started_event(10, 2, "elemental_skill"),)),
        10,
    )
    assert runtime.lunar_reaction_bonus(10) == 0.0


def test_runtime_applies_bonus_for_non_moonsign_skill_and_overrides():
    runtime, events = _runtime()

    runtime.update_frame(
        make_event_context(10, (make_action_started_event(10, 1, "elemental_skill"),)),
        10,
    )
    assert runtime.lunar_reaction_bonus(10) == 0.2
    assert runtime.lunar_reaction_bonus(1209) == 0.2
    assert runtime.lunar_reaction_bonus(1210) == 0.0
    assert events.frame_events[-1].event_type is EventType.MOONSIGN_BONUS_APPLIED

    runtime.update_frame(
        make_event_context(300, (make_action_started_event(300, 1, "elemental_burst"),)),
        300,
    )
    assert runtime.store.bonus is not None
    assert runtime.store.bonus.applied_frame == 300


def test_runtime_expires_bonus_and_publishes_expired_fact():
    runtime, events = _runtime()
    runtime.update_frame(
        make_event_context(10, (make_action_started_event(10, 1, "elemental_skill"),)),
        10,
    )
    runtime.update_frame(make_event_context(1210), 1210)

    assert runtime.store.bonus is None
    assert runtime.lunar_reaction_bonus(1210) == 0.0
    assert events.frame_events[-1].event_type is EventType.MOONSIGN_BONUS_EXPIRED
