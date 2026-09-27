"""桑多涅通用回能判定的纵向集成（切片 S0 临时测试）。

链路对齐通用回能规则："NA/重击标签伤害
结算事实 -> FACT_RESPONSE 概率判定 -> 统一意图队列能量恢复请求 -> 直接恢复
提交"。桑多涅为双手剑（初始 0%、每次失败 +10%）：重击按住场景中扫射与射线
的判定次数在 11 次后概率封顶 100%，因此无论随机种子如何，至少成功恢复一次；
普攻首段（初始 0%）必然失败但累积概率；战技棱晶弹（元素战技标签）不参与判定。
"""

from __future__ import annotations

import pytest

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.events import EventType
from tests.helpers import sandrone as sandrone_helpers

SANDRONE_REF = AttributeSubjectRef.character("character:slot_1")
RECOVERY_SOURCE_KEY = "energy.recovery.restore"


def _energy_change_events(assembled) -> list:
    events: list = []
    assembled.context.events.subscribe(EventType.DIRECT_ENERGY_CHANGE_RESOLVED, events.append)
    return events


def _charged_attack_payload(max_frames: int, press: int, release: int) -> dict[str, object]:
    return sandrone_helpers.sandrone_input_payload(
        max_frames=max_frames,
        input_trace=[
            {"frame": press, "events": [{"key": "mouse.right", "phase": "press"}]},
            {"frame": release, "events": [{"key": "mouse.right", "phase": "release"}]},
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


def test_charged_attack_hold_recovers_energy_through_probability_ladder(
    sandrone_assembled,
):
    # 重击按住：扫射（重击标签，21F 节奏）与冷凝射线（重击标签，66F 节奏）
    # 的每次命中各判定一次。双手剑前 10 次判定把概率推到 100%，第 11 次判定
    # 起必然成功——380 帧内判定远多于 11 次，恢复量至少 1 点且每次恰 1 点。
    assembled = sandrone_assembled(payload=_charged_attack_payload(380, 2, 376))
    recovery_events = _energy_change_events(assembled)

    assembled.simulator.run()

    recoveries = [
        event.payload.result
        for event in recovery_events
        if event.payload.result.source_context is not None
        and event.payload.result.source_context.source_key == RECOVERY_SOURCE_KEY
    ]
    assert len(recoveries) >= 1
    # 每次成功恢复恰 1 点且无其他能量来源，终值等于成功次数。
    assert assembled.energy_store.current_energy(SANDRONE_REF) == float(len(recoveries))
    for result in recoveries:
        assert result.change_kind.value == "direct_restore"
        assert result.requested_amount == 1.0
        assert result.effective_amount == 1.0
        assert result.target_ref == SANDRONE_REF
        assert "energy.recovery" in result.tags


def test_skill_damage_does_not_trigger_judgment(sandrone_assembled):
    # 战技棱晶弹为元素战技标签：不触发判定，概率保持初始 0%，能量无变化。
    assembled = sandrone_assembled(input_key="keyboard.e", max_frames=60)
    recovery_events = _energy_change_events(assembled)

    assembled.simulator.run()

    assert recovery_events == []
    assert assembled.energy_store.current_energy(SANDRONE_REF) == 0.0
    assert assembled.energy_recovery_store.next_probability(SANDRONE_REF) == 0.0


def test_first_normal_attack_fails_initial_zero_and_accumulates(sandrone_assembled):
    # 普攻一段为「普通攻击1」标签（前缀词表命中）：初始 0% 判定必然失败，
    # 概率递增到 0.1，无能量变化。
    assembled = sandrone_assembled(max_frames=60)
    recovery_events = _energy_change_events(assembled)

    assembled.simulator.run()

    assert recovery_events == []
    assert assembled.energy_store.current_energy(SANDRONE_REF) == 0.0
    assert assembled.energy_recovery_store.next_probability(SANDRONE_REF) == pytest.approx(0.1)
