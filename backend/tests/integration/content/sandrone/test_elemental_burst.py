"""桑多涅元素爆发的纵向集成：能量门槛、扣能与轰炸/光束时间轴。"""

from __future__ import annotations

from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    SANDRONE_ACTION_TABLE,
    SANDRONE_ELEMENTAL_BURST_ACTION_KEY,
    SANDRONE_ELEMENTAL_BURST_BEAM_IMPACT_KEY,
    SANDRONE_ELEMENTAL_BURST_BOMBARDMENT_1_IMPACT_KEY,
    SANDRONE_ELEMENTAL_BURST_BOMBARDMENT_2_IMPACT_KEY,
    SANDRONE_ELEMENTAL_BURST_BOMBARDMENT_3_IMPACT_KEY,
)
from genshin_sim.core.elements import Element
from genshin_sim.core.events import EventType
from tests.helpers import sandrone as sandrone_helpers

Q_RELEASE_FRAME = 2
IMPACT_FRAMES = {
    point.impact_key: Q_RELEASE_FRAME + point.frame
    for point in SANDRONE_ACTION_TABLE[SANDRONE_ELEMENTAL_BURST_ACTION_KEY].impact_points
}
DAMAGE_NAMES_BY_IMPACT_KEY = {
    SANDRONE_ELEMENTAL_BURST_BOMBARDMENT_1_IMPACT_KEY: "轰炸伤害",
    SANDRONE_ELEMENTAL_BURST_BOMBARDMENT_2_IMPACT_KEY: "轰炸伤害",
    SANDRONE_ELEMENTAL_BURST_BOMBARDMENT_3_IMPACT_KEY: "轰炸伤害",
    SANDRONE_ELEMENTAL_BURST_BEAM_IMPACT_KEY: "聚能光束伤害",
}


def test_burst_without_energy_is_rejected_and_deals_no_damage(sandrone_assembled):
    assembled = sandrone_assembled(input_key="keyboard.q", max_frames=330)
    events = sandrone_helpers.sandrone_damage_events(assembled)

    assembled.simulator.run()

    assert not [e for e in events if e.event_type is EventType.DAMAGE_RESOLVED]


def test_burst_spends_energy_then_fires_bombardments_and_beam(sandrone_assembled):
    # 满能量起步：Q 扣能帧（动作第 1 帧）消耗全部爆发充能，轰炸三段与光束
    # 按动作表影响点帧依序结算。
    payload = sandrone_helpers.sandrone_input_payload(
        max_frames=560,
        input_trace=[
            {"frame": 1, "events": [{"key": "keyboard.q", "phase": "press"}]},
            {"frame": Q_RELEASE_FRAME, "events": [{"key": "keyboard.q", "phase": "release"}]},
        ],
        targets=[
            {
                "id": "target_1",
                "level": 90,
                "position": {"x": 0, "y": 0, "z": 4},
                "resistance": {},
            }
        ],
    )
    payload["rules"] = {"active": ["start_with_full_energy"]}
    assembled = sandrone_assembled(payload=payload)
    events = sandrone_helpers.sandrone_damage_events(assembled)
    changes: list = []
    assembled.context.events.subscribe(EventType.CHARACTER_ENERGY_CHANGED, changes.append)

    assembled.simulator.run()

    for impact_key, name in DAMAGE_NAMES_BY_IMPACT_KEY.items():
        hits = [e for e in events if e.payload.result.damage_name == name]
        assert IMPACT_FRAMES[impact_key] in [e.frame for e in hits], impact_key
    assert all(e.payload.result.element is Element.CRYO for e in events)

    # 扣能帧先于全部伤害：满能量（60）经爆发消耗归零。
    spends = [
        change for change in changes if change.payload.result.change_kind.value == "burst_spend"
    ]
    assert len(spends) == 1
    assert spends[0].frame < min(e.frame for e in events if e.payload.result.damage_name)
    assert assembled.energy_store.current_energy(sandrone_helpers.SANDRONE_REF) == 0.0
