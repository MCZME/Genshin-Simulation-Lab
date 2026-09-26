"""桑多涅元素爆发的纵向集成：能量门槛接线验证。

切片 1 只验证爆发伤害链路的公共条件门槛（能量/冷却未就绪时确定性拒绝）；
轰炸与光束的完整时间轴行为在能量来源接入后覆盖。
"""

from __future__ import annotations

from genshin_sim.core.events import EventType


def test_burst_without_energy_is_rejected_and_deals_no_damage(sandrone_assembled):
    assembled = sandrone_assembled(input_key="keyboard.q", max_frames=330)
    events: list = []
    assembled.context.events.subscribe(EventType.DAMAGE_RESOLVED, events.append)

    assembled.simulator.run()

    assert not [e for e in events if e.event_type is EventType.DAMAGE_RESOLVED]
