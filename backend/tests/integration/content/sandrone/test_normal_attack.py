"""桑多涅普攻的纵向集成：帧表命中、伤害标签与冰附着接线。"""

from __future__ import annotations

from genshin_sim.core.elements import AuraKind, Element, ElementalSubjectRef
from genshin_sim.core.events import EventType
from tests.helpers import sandrone as sandrone_helpers


def _damage_events(assembled) -> list:
    events: list = []
    assembled.context.events.subscribe(EventType.DAMAGE_RESOLVED, events.append)
    return events


def test_first_normal_attack_hits_at_measured_frame(sandrone_assembled):
    assembled = sandrone_assembled(max_frames=60)
    events = _damage_events(assembled)

    assembled.simulator.run()

    damage_events = [e for e in events if e.event_type is EventType.DAMAGE_RESOLVED]
    assert len(damage_events) == 1
    damage = damage_events[0]
    # 帧表：动作自释放帧（2）起算，一段命中 +44。
    assert damage.frame == 46
    result = damage.payload.result
    assert result.main_attack_tag == "普通攻击1"
    assert result.element is Element.CRYO
    assert result.final_damage > 0


def test_normal_attack_chain_starts_at_measured_window(sandrone_assembled):
    payload = sandrone_helpers.sandrone_input_payload(
        max_frames=120,
        input_trace=[
            {"frame": 1, "events": [{"key": "mouse.left", "phase": "press"}]},
            {"frame": 2, "events": [{"key": "mouse.left", "phase": "release"}]},
            {"frame": 60, "events": [{"key": "mouse.left", "phase": "press"}]},
            {"frame": 61, "events": [{"key": "mouse.left", "phase": "release"}]},
        ],
    )
    assembled = sandrone_assembled(max_frames=120, payload=payload)
    events = _damage_events(assembled)

    assembled.simulator.run()

    damage_events = [e for e in events if e.event_type is EventType.DAMAGE_RESOLVED]
    assert [e.payload.result.main_attack_tag for e in damage_events] == [
        "普通攻击1",
        "普通攻击2",
    ]
    # 一段命中 2+44=46；二段自衔接窗口（2+59=61）起的释放帧 61 起算，命中 61+24=85。
    assert [e.frame for e in damage_events] == [46, 85]


def test_normal_attack_applies_cryo_to_target(sandrone_assembled):
    assembled = sandrone_assembled(max_frames=60)

    assembled.simulator.run()

    target_subject = ElementalSubjectRef.target("target:target_1")
    component = assembled.aura_runtime.view(target_subject).component_for(AuraKind.CRYO)
    assert component is not None
