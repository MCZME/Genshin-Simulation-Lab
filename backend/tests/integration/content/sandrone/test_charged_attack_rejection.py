"""桑多涅重击输入的接线验证：切片内确定性拒绝，不产生动作与伤害。"""

from __future__ import annotations

from genshin_sim.core.events import EventType


def test_charged_attack_input_is_rejected_before_fageiou_slice(sandrone_assembled):
    assembled = sandrone_assembled(input_key="mouse.right", max_frames=40)
    events: list = []
    for event_type in (EventType.DAMAGE_RESOLVED,):
        assembled.context.events.subscribe(event_type, events.append)

    assembled.simulator.run()

    assert not [e for e in events if e.event_type is EventType.DAMAGE_RESOLVED]
