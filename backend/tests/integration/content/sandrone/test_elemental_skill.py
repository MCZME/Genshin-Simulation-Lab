"""桑多涅元素战技的纵向集成：两枚棱晶弹的帧表命中与冰附着。"""

from __future__ import annotations

from genshin_sim.core.elements import AuraKind, Element, ElementalSubjectRef
from genshin_sim.core.events import EventType


def test_elemental_skill_fires_two_prisms_at_measured_frames(sandrone_assembled):
    assembled = sandrone_assembled(input_key="keyboard.e", max_frames=60)
    events: list = []
    assembled.context.events.subscribe(EventType.DAMAGE_RESOLVED, events.append)

    assembled.simulator.run()

    damage_events = [e for e in events if e.event_type is EventType.DAMAGE_RESOLVED]
    # 帧表：动作自释放帧（2）起算，棱晶弹 +16/+32。
    assert [e.frame for e in damage_events] == [18, 34]
    assert all(e.payload.result.main_attack_tag == "元素战技" for e in damage_events)
    assert all(e.payload.result.element is Element.CRYO for e in damage_events)


def test_elemental_skill_prism_applies_cryo_to_target(sandrone_assembled):
    assembled = sandrone_assembled(input_key="keyboard.e", max_frames=60)

    assembled.simulator.run()

    target_subject = ElementalSubjectRef.target("target:target_1")
    component = assembled.aura_runtime.view(target_subject).component_for(AuraKind.CRYO)
    assert component is not None
