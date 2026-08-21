"""芭芭拉普攻、重击与下落攻击的数值闭环。"""

from __future__ import annotations

import pytest

from genshin_sim.content import (
    BARBARA_CHARGED_ATTACK_IMPACT_KEY,
    BARBARA_NORMAL_ATTACK_1_IMPACT_KEY,
    BARBARA_PLUNGE_COLLISION_IMPACT_KEY,
    BARBARA_PLUNGE_LANDING_IMPACT_KEY,
)
from genshin_sim.core.events import EventType
from genshin_sim.core.space import ACTIVE_CHARACTER_ENTITY_ID, Vector3


def test_barbara_normal_attack_scaling_resolves_damage(
    barbara_assembled,
):
    assembled = barbara_assembled()
    damage_events = []
    assembled.context.events.subscribe(EventType.DAMAGE_RESOLVED, damage_events.append)
    aura_events = []
    assembled.context.events.subscribe(EventType.AURA_APPLIED, aura_events.append)
    icd_events = []
    assembled.context.events.subscribe(EventType.AURA_ICD_RESOLVED, icd_events.append)

    result = assembled.simulator.run()

    assert result.end_frame >= 17
    assert len(assembled.impact_runtime.dispatch_records) == 1
    dispatched = assembled.impact_runtime.dispatch_records[0].requests[0]
    assert dispatched.impact_key == BARBARA_NORMAL_ATTACK_1_IMPACT_KEY
    assert dispatched.damage_spec is not None
    assert len(assembled.damage_handler.records) == 1
    damage = assembled.damage_handler.records[0].result
    assert damage.base_damage == pytest.approx(75.68)
    assert damage.defense.multiplier == 0.5
    assert damage.final_damage == pytest.approx(37.84)
    assert [event.event_type for event in damage_events] == [EventType.DAMAGE_RESOLVED]
    assert [event.event_type for event in aura_events] == [EventType.AURA_APPLIED]
    assert aura_events[0].payload.to_dict()["aura_kind"] == "hydro"
    assert len(icd_events) == 1
    assert icd_events[0].payload.to_dict()["sequence_key"] == "默认"
    assert icd_events[0].payload.to_dict()["tag_key"] == "普通攻击"


def test_barbara_charged_attack_scaling_resolves_damage(
    barbara_assembled,
):
    assembled = barbara_assembled(input_key="mouse.right", max_frames=60)
    damage_events = []
    assembled.context.events.subscribe(EventType.DAMAGE_RESOLVED, damage_events.append)
    aura_events = []
    assembled.context.events.subscribe(EventType.AURA_APPLIED, aura_events.append)
    icd_events = []
    assembled.context.events.subscribe(EventType.AURA_ICD_RESOLVED, icd_events.append)

    result = assembled.simulator.run()

    assert result.end_frame >= 58
    assert len(assembled.impact_runtime.dispatch_records) == 1
    dispatched = assembled.impact_runtime.dispatch_records[0].requests[0]
    assert dispatched.impact_key == BARBARA_CHARGED_ATTACK_IMPACT_KEY
    assert dispatched.damage_spec is not None
    assert len(assembled.damage_handler.records) == 1
    damage = assembled.damage_handler.records[0].result
    assert damage.base_damage == pytest.approx(332.48)
    assert damage.final_damage == pytest.approx(166.24)
    assert [event.event_type for event in damage_events] == [EventType.DAMAGE_RESOLVED]
    assert [event.event_type for event in aura_events] == [EventType.AURA_APPLIED]
    assert aura_events[0].payload.to_dict()["aura_kind"] == "hydro"
    assert len(icd_events) == 1
    assert icd_events[0].payload.to_dict()["sequence_key"] is None


def test_barbara_plunge_from_high_air_resolves_damage_and_lands(
    barbara_assembled,
):
    assembled = barbara_assembled(max_frames=60)
    assert assembled.context.space_runtime is not None
    assembled.context.space_runtime.apply_displacement(
        ACTIVE_CHARACTER_ENTITY_ID,
        Vector3(0.0, 2.3, 0.0),
    )
    aura_events = []
    assembled.context.events.subscribe(EventType.AURA_APPLIED, aura_events.append)

    result = assembled.simulator.run()

    assert result.end_frame >= 35
    assert [record.impact_key for record in assembled.impact_runtime.dispatch_records] == [
        BARBARA_PLUNGE_COLLISION_IMPACT_KEY,
        BARBARA_PLUNGE_LANDING_IMPACT_KEY,
    ]
    assert [record.result.final_damage for record in assembled.damage_handler.records] == [
        pytest.approx(56.8288),
        pytest.approx(141.9344),
    ]
    landed = assembled.context.space_runtime.get_entity(ACTIVE_CHARACTER_ENTITY_ID)
    assert landed is not None
    assert landed.position.y == pytest.approx(0.0)
    assert len(aura_events) == 1
