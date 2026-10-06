"""阿罗夏轰霆猎场纵向集成：Q 创建实体、双攻击通道时序、P4 周期回血、
C1 雷相关反应回能、C2 时长延长。

时序断言从创建帧推导（首拍 +81 / 首咬 +127、间隔 120 帧），不复制帧数据
真值；回血与回能数值取合成效果行（见测试规范 §3.2）。
"""

from __future__ import annotations

from genshin_sim.core.elements import AuraKind, Element, ElementalSubjectRef
from genshin_sim.core.events import EventType
from genshin_sim.core.systems.energy import EnergyRuntime
from tests.helpers import alyosha as alyosha_helpers

FIELD_FIRST_TICK_OFFSET = 81
TUGARIN_FIRST_BITE_OFFSET = 127
TICK_PERIOD_FRAMES = 120


def _burst_payload(max_frames: int, *, constellation: int = 0):
    payload = alyosha_helpers.alyosha_input_payload(
        max_frames=max_frames,
        constellation=constellation,
        input_trace=[
            {"frame": 1, "events": [{"key": "keyboard.q", "phase": "press"}]},
            {"frame": 2, "events": [{"key": "keyboard.q", "phase": "release"}]},
        ],
    )
    payload["rules"] = {"active": ["start_with_full_energy"]}
    return payload


def test_burst_creates_fulgurite_entity_with_dual_ticks(alyosha_assembled):
    assembled = alyosha_assembled(payload=_burst_payload(320))
    events = alyosha_helpers.alyosha_damage_events(assembled)

    assembled.simulator.run()

    objects = alyosha_helpers.fulgurite_objects(assembled)
    assert len(objects) == 1
    created_frame = objects[0].entity.lifecycle.created_frame
    field_frames = sorted(e.frame for e in events if e.payload.result.damage_name == "轰霆猎场伤害")
    bite_frames = sorted(e.frame for e in events if e.payload.result.damage_name == "图加林伤害")
    # 首拍/首咬锚定施放帧（创建帧即召唤影响点帧），此后固定 120 帧间隔。
    assert field_frames == [
        created_frame + FIELD_FIRST_TICK_OFFSET,
        created_frame + FIELD_FIRST_TICK_OFFSET + TICK_PERIOD_FRAMES,
    ]
    assert bite_frames == [
        created_frame + TUGARIN_FIRST_BITE_OFFSET,
        created_frame + TUGARIN_FIRST_BITE_OFFSET + TICK_PERIOD_FRAMES,
    ]


def test_field_tick_applies_electro_aura_to_targets_inside(alyosha_assembled):
    # 轰霆猎场 tick 命中范围内所有敌人并施加雷附着（共享 ICD 序列下
    # 120f 间隔 > 96f 重置，场内目标每次 tick 均附着）。
    assembled = alyosha_assembled(payload=_burst_payload(140))

    assembled.simulator.run()

    subject = ElementalSubjectRef.target("target:target_1")
    assert assembled.aura_runtime.view(subject).component_for(AuraKind.ELECTRO) is not None


def test_p4_heals_active_character_on_bite_ticks(alyosha_assembled):
    # P4（合成比例 120% 攻击力）随图加林攻击动作固定产出，无敌人也回血——
    # 本用例不放置任何目标，治疗仍按期触发。
    payload = alyosha_helpers.alyosha_input_payload(
        max_frames=200,
        input_trace=[
            {"frame": 1, "events": [{"key": "keyboard.q", "phase": "press"}]},
            {"frame": 2, "events": [{"key": "keyboard.q", "phase": "release"}]},
        ],
        targets=[],
    )
    payload["rules"] = {"active": ["start_with_full_energy"]}
    assembled = alyosha_assembled(payload=payload)
    heal_events: list = []
    assembled.context.events.subscribe(EventType.HEALING_RESOLVED, heal_events.append)

    assembled.simulator.run()

    objects = alyosha_helpers.fulgurite_objects(assembled)
    assert len(objects) == 1
    created_frame = objects[0].entity.lifecycle.created_frame
    heal_frames = sorted(event.frame for event in heal_events)
    assert heal_frames == [created_frame + TUGARIN_FIRST_BITE_OFFSET]


def test_c2_extends_field_duration(alyosha_assembled):
    # C2：Q 持续 +6s（合成 14s + 6s = 20s = 1200 帧）。
    assembled = alyosha_assembled(payload=_burst_payload(200, constellation=2))

    assembled.simulator.run()

    objects = alyosha_helpers.fulgurite_objects(assembled)
    assert len(objects) == 1
    entity = objects[0].entity
    assert entity.lifecycle.expires_at_frame - entity.lifecycle.created_frame == 1200


def test_c1_grants_energy_on_electro_reaction(alyosha_assembled):
    # C1：场域 tick 的雷附着对预置冰附着触发超导（雷元素相关反应）→ 阿罗夏
    # 回复 15 点能量（合成行数值；场域不产微粒，窗口内无其他回能源）。
    assembled = alyosha_assembled(payload=_burst_payload(140, constellation=1))
    alyosha_helpers.apply_aura(assembled, Element.CRYO)

    assembled.simulator.run()

    runtime = assembled.context.get_system(EnergyRuntime)
    assert isinstance(runtime, EnergyRuntime)
    assert alyosha_helpers.current_energy(assembled) == 15.0
