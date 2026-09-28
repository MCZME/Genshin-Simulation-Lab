"""桑多涅元素战技的纵向集成：两枚棱晶弹的帧表命中与冰附着。"""

from __future__ import annotations

from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    SANDRONE_ACTION_TABLE,
    SANDRONE_ELEMENTAL_SKILL_ACTION_KEY,
)
from genshin_sim.core.elements import AuraKind, Element, ElementalSubjectRef
from genshin_sim.core.events import EventType

RELEASE_FRAME = 2
PRISM_FRAMES = [
    RELEASE_FRAME + point.frame
    for point in SANDRONE_ACTION_TABLE[SANDRONE_ELEMENTAL_SKILL_ACTION_KEY].impact_points
]


def test_elemental_skill_fires_two_prisms_per_frame_table(sandrone_assembled):
    assembled = sandrone_assembled(input_key="keyboard.e", max_frames=60)
    events: list = []
    assembled.context.events.subscribe(EventType.DAMAGE_RESOLVED, events.append)

    assembled.simulator.run()

    damage_events = [e for e in events if e.event_type is EventType.DAMAGE_RESOLVED]
    # 命中帧 = 释放帧 + 动作表两枚棱晶弹影响点帧（+16/+32）。
    assert [e.frame for e in damage_events] == PRISM_FRAMES
    assert all(e.payload.result.main_attack_tag == "元素战技" for e in damage_events)
    assert all(e.payload.result.element is Element.CRYO for e in damage_events)


def test_elemental_skill_prism_applies_cryo_to_target(sandrone_assembled):
    assembled = sandrone_assembled(input_key="keyboard.e", max_frames=60)

    assembled.simulator.run()

    target_subject = ElementalSubjectRef.target("target:target_1")
    component = assembled.aura_runtime.view(target_subject).component_for(AuraKind.CRYO)
    assert component is not None
