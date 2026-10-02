"""通用能量恢复的系统能力集成。

链路对齐通用回能规则：伤害结算事实 -> FACT_RESPONSE 概率判定 -> 统一意图队列
能量恢复请求 -> 直接恢复提交，全部经生产帧管线与意图结算路径完成。伤害以合成
影响请求预置进统一意图队列（测试规范 §3.2 合成输入），不依赖角色 content。
夹具角色为双手剑（初始 0%、每次失败 +10%）：首判必败可确定性验证累积，概率经
领域状态接口预置到封顶 100% 后判定必成功，结论与随机种子无关。
"""

from __future__ import annotations

import pytest

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.contracts.intents import IntentEnvelope, IntentKind
from genshin_sim.core.contracts.phases import FramePhase
from genshin_sim.core.elements import Element
from genshin_sim.core.events import EventType
from tests.helpers.reactions import reaction_damage_request

CHARACTER_REF = AttributeSubjectRef.character("character:slot_1")
RECOVERY_SOURCE_KEY = "energy.recovery.restore"


def _recovery_events(assembled) -> list:
    events: list = []
    assembled.context.events.subscribe(EventType.DIRECT_ENERGY_CHANGE_RESOLVED, events.append)
    return events


def _seed_damage_fact(assembled, *, main_attack_tag: str) -> None:
    """把一条合成伤害请求预置进意图队列，由下一帧的结算轮次分发。"""

    request_id = "test.energy_recovery.damage:1"
    assembled.intent_queue.enqueue(
        IntentEnvelope(
            intent_id=request_id,
            kind=IntentKind.IMPACT,
            frame=1,
            phase=FramePhase.SETTLEMENT,
            round=0,
            source_ref="testing.energy_recovery",
            payload=reaction_damage_request(
                Element.CRYO,
                request_id,
                main_attack_tag=main_attack_tag,
                frame=1,
                scaling_value=0.01,
            ),
        )
    )


def _recovery_results(recovery_events: list) -> list:
    return [
        event.payload.result
        for event in recovery_events
        if event.payload.result.source_context is not None
        and event.payload.result.source_context.source_key == RECOVERY_SOURCE_KEY
    ]


@pytest.mark.parametrize(
    "main_attack_tag",
    ["普通攻击1", "重击"],
    ids=["普攻标签", "重击标签"],
)
def test_capped_probability_recovers_one_point(energy_assembled, main_attack_tag):
    # 概率经领域状态接口预置到封顶 100%（11 次失败钳位）：判定确定成功且
    # 不消耗随机序列，恢复恰 1 点并把概率重置回初始 0%。
    assembled = energy_assembled()
    for _ in range(11):
        assembled.energy_recovery_store.record_failure(CHARACTER_REF)
    assert assembled.energy_recovery_store.next_probability(CHARACTER_REF) == 1.0
    recovery_events = _recovery_events(assembled)
    _seed_damage_fact(assembled, main_attack_tag=main_attack_tag)

    assembled.simulator.run()

    recoveries = _recovery_results(recovery_events)
    assert len(recoveries) == 1
    result = recoveries[0]
    assert result.change_kind.value == "direct_restore"
    assert result.requested_amount == 1.0
    assert result.effective_amount == 1.0
    assert result.target_ref == CHARACTER_REF
    assert "energy.recovery" in result.tags
    assert assembled.energy_store.current_energy(CHARACTER_REF) == 1.0
    assert assembled.energy_recovery_store.next_probability(CHARACTER_REF) == 0.0


def test_first_judgment_fails_and_accumulates(energy_assembled):
    # 初始 0%：首次判定必然失败（roll(0) 确定短路），概率累积到 0.1，无能量变化。
    assembled = energy_assembled()
    recovery_events = _recovery_events(assembled)
    _seed_damage_fact(assembled, main_attack_tag="普通攻击1")

    assembled.simulator.run()

    assert _recovery_results(recovery_events) == []
    assert assembled.energy_store.current_energy(CHARACTER_REF) == 0.0
    assert assembled.energy_recovery_store.next_probability(CHARACTER_REF) == pytest.approx(0.1)


def test_non_trigger_tag_damage_does_not_judge(energy_assembled):
    # 元素战技标签不在触发词表内：不判定、不累积、无能量变化。
    assembled = energy_assembled()
    recovery_events = _recovery_events(assembled)
    _seed_damage_fact(assembled, main_attack_tag="元素战技")

    assembled.simulator.run()

    assert recovery_events == []
    assert assembled.energy_store.current_energy(CHARACTER_REF) == 0.0
    assert assembled.energy_recovery_store.next_probability(CHARACTER_REF) == 0.0
