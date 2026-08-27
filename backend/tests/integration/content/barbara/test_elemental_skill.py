"""芭芭拉元素战技与水环治疗的纵向集成。"""

from __future__ import annotations

from genshin_sim.content import (
    BARBARA_ELEMENTAL_SKILL_ON_HIT_HEAL_IMPACT_KEY,
    BARBARA_NORMAL_ATTACK_1_ACTION_KEY,
    BARBARA_RING_OBJECT_KEY,
)
from genshin_sim.core.elements import AuraKind, ElementalSubjectRef
from tests.helpers import barbara as barbara_helpers


def test_barbara_elemental_skill_cast_resolves_damage_self_wet_and_ring(
    barbara_assembled,
):
    assembled = barbara_assembled(input_key="keyboard.e", max_frames=80)

    result = assembled.simulator.run()

    assert result.end_frame >= 46
    assert len(assembled.damage_handler.records) == 1
    subject = ElementalSubjectRef.character("character:slot_1")
    assert assembled.aura_runtime.view(subject).component_for(AuraKind.HYDRO) is not None
    ring_objects = assembled.space_runtime.created_object_runtime.objects
    assert ring_objects[0].object_key == BARBARA_RING_OBJECT_KEY
    assert assembled.impact_request_dispatcher.healing_records


def test_barbara_ring_on_hit_heal_heals_team_on_normal_attack(
    barbara_assembled,
):
    payload = barbara_helpers.barbara_input_payload(max_frames=80)
    payload["input_trace"] = _ring_attack_trace("mouse.left")
    assembled = barbara_assembled(payload=payload)

    assembled.simulator.run()

    assert len(_on_hit_healing_values(assembled)) == 1


def test_barbara_ring_on_hit_heal_triggered_once_per_normal_attack(
    barbara_assembled,
):
    payload = barbara_helpers.barbara_input_payload(
        max_frames=80,
        targets=(
            {
                "id": "target_1",
                "level": 90,
                "position": {"x": 0, "y": 0, "z": 0},
                "resistance": {},
            },
            {
                "id": "target_2",
                "level": 90,
                "position": {"x": 0.5, "y": 0, "z": 0},
                "resistance": {},
            },
        ),
    )
    payload["input_trace"] = _ring_attack_trace("mouse.left")
    assembled = barbara_assembled(payload=payload)

    assembled.simulator.run()

    na_records = [
        record
        for record in assembled.damage_handler.records
        if record.impact_request.action_key == BARBARA_NORMAL_ATTACK_1_ACTION_KEY
    ]
    assert len(na_records) == 2
    assert len(_on_hit_healing_values(assembled)) == 1


def _ring_attack_trace(attack_key: str) -> list[dict[str, object]]:
    return [
        {"frame": 1, "events": [{"key": "keyboard.e", "phase": "press"}]},
        {"frame": 2, "events": [{"key": "keyboard.e", "phase": "release"}]},
        {"frame": 57, "events": [{"key": attack_key, "phase": "press"}]},
        {"frame": 58, "events": [{"key": attack_key, "phase": "release"}]},
    ]


def _on_hit_healing_values(assembled) -> list[float]:
    return [
        record.records[0].result.final_healing
        for record in assembled.impact_request_dispatcher.healing_records
        if record.impact_request.impact_key == BARBARA_ELEMENTAL_SKILL_ON_HIT_HEAL_IMPACT_KEY
    ]
