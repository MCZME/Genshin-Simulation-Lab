"""砂糖风元素直伤的附着边界集成。

风元素不形成持久 Aura：目标裸身时砂糖普攻只结算直伤，不写任何 Aura、不发布
反应事件。本条同时是「无反应附着分支的元素持久性」在角色链路上的回归保护
（核心边界见 ``tests/integration/reactions/test_anemo_aura_boundary.py``）。
"""

from __future__ import annotations

from genshin_sim.core.elements import AuraKind, ElementalSubjectRef
from genshin_sim.core.events import EventType
from tests.helpers import sucrose as sucrose_helpers

_TARGET_SUBJECT = ElementalSubjectRef.target("target_1")


def test_sucrose_normal_attack_leaves_no_aura_on_bare_target(sucrose_assembled):
    assembled = sucrose_assembled(max_frames=60)
    damage_events = sucrose_helpers.sucrose_damage_events(assembled)

    assembled.simulator.run()

    assert len(damage_events) == 1
    assert len(assembled.damage_handler.records) == 1
    assert assembled.aura_runtime.view(_TARGET_SUBJECT).components == ()


def test_sucrose_damage_does_not_publish_reaction_occurrence(sucrose_assembled):
    assembled = sucrose_assembled(max_frames=60)
    reaction_events: list = []
    assembled.context.events.subscribe(EventType.REACTION_OCCURRED, reaction_events.append)

    assembled.simulator.run()

    view = assembled.aura_runtime.view(_TARGET_SUBJECT)
    for aura_kind in AuraKind:
        assert view.component_for(aura_kind) is None
    assert reaction_events == []


def test_sucrose_damage_element_is_anemo(sucrose_assembled):
    assembled = sucrose_assembled(max_frames=60)
    assembled.simulator.run()

    result = assembled.damage_handler.records[0].result
    assert result.element.value == "anemo"
