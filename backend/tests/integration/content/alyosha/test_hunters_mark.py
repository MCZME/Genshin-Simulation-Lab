"""阿罗夏弋猎印记与猎者之准纵向集成：E/NA4 命中施加印记、图加林激活印记
授予猎者之准（前台主体）、C6 叠层与叠满精通。

数值全部为合成数据（助手资产库，见测试规范 §3.2）；印记/猎者之准的持续
时长只做「存在性」断言，不复制资产数值真值。
"""

from __future__ import annotations

from tests.helpers import alyosha as alyosha_helpers


def test_elemental_skill_applies_hunters_mark(alyosha_assembled):
    assembled = alyosha_assembled(input_key="keyboard.e", max_frames=80)

    assembled.simulator.run()

    records = alyosha_helpers.mark_records(assembled, frame=80)
    assert len(records) == 1
    assert records[0].state.stack_count == 1


def test_na4_applies_hunters_mark(alyosha_assembled):
    # 连续四段普攻：N1(40f)→N2(35f)→N3(72f)→N4，N4 命中帧 +23 处施加印记。
    assembled = alyosha_assembled(
        input_key="mouse.left",
        max_frames=260,
        input_trace=[
            {"frame": 1, "events": [{"key": "mouse.left", "phase": "press"}]},
            {"frame": 2, "events": [{"key": "mouse.left", "phase": "release"}]},
            {"frame": 42, "events": [{"key": "mouse.left", "phase": "press"}]},
            {"frame": 43, "events": [{"key": "mouse.left", "phase": "release"}]},
            {"frame": 78, "events": [{"key": "mouse.left", "phase": "press"}]},
            {"frame": 79, "events": [{"key": "mouse.left", "phase": "release"}]},
            {"frame": 151, "events": [{"key": "mouse.left", "phase": "press"}]},
            {"frame": 152, "events": [{"key": "mouse.left", "phase": "release"}]},
        ],
    )
    events = alyosha_helpers.alyosha_damage_events(assembled)

    assembled.simulator.run()

    assert events[-1].payload.result.main_attack_tag == "普通攻击4"
    assert len(alyosha_helpers.mark_records(assembled, frame=260)) == 1


def test_tugarin_bite_consumes_mark_and_grants_precision(alyosha_assembled):
    # E 点按施加印记（命中 +43）→ Q 取消接爆发（E 55 帧衔接点）→ 图加林首咬
    # （施放后 127 帧）激活印记：印记清除、猎者之准挂前台主体（stack 1）。
    payload = alyosha_helpers.alyosha_input_payload(
        max_frames=280,
        input_trace=[
            {"frame": 1, "events": [{"key": "keyboard.e", "phase": "press"}]},
            {"frame": 2, "events": [{"key": "keyboard.e", "phase": "release"}]},
            {"frame": 58, "events": [{"key": "keyboard.q", "phase": "press"}]},
            {"frame": 59, "events": [{"key": "keyboard.q", "phase": "release"}]},
        ],
    )
    payload["rules"] = {"active": ["start_with_full_energy"]}
    assembled = alyosha_assembled(payload=payload)

    assembled.simulator.run()

    assert len(alyosha_helpers.mark_records(assembled, frame=280)) == 0
    precision = alyosha_helpers.precision_records(assembled, frame=280)
    assert len(precision) == 1
    assert precision[0].state.stack_count == 1


def test_bite_without_mark_does_not_grant_precision(alyosha_assembled):
    # 无 C2 时撕咬未带印记的目标不激活、不授予猎者之准。
    payload = alyosha_helpers.alyosha_input_payload(
        max_frames=280,
        input_trace=[
            {"frame": 1, "events": [{"key": "keyboard.q", "phase": "press"}]},
            {"frame": 2, "events": [{"key": "keyboard.q", "phase": "release"}]},
        ],
    )
    payload["rules"] = {"active": ["start_with_full_energy"]}
    assembled = alyosha_assembled(payload=payload)

    assembled.simulator.run()

    assert len(alyosha_helpers.precision_records(assembled, frame=280)) == 0


def test_c6_precision_stacks_and_mastery_at_full(alyosha_assembled):
    # C6：猎者之准可叠 2 层（C2 先施加印记再攻击激活，每次撕咬都触发）。
    # 两次撕咬后 stack 2 且伴生精通 Buff 在场；精通面板 +100。
    payload = alyosha_helpers.alyosha_input_payload(
        max_frames=420,
        constellation=6,
        input_trace=[
            {"frame": 1, "events": [{"key": "keyboard.q", "phase": "press"}]},
            {"frame": 2, "events": [{"key": "keyboard.q", "phase": "release"}]},
        ],
    )
    payload["rules"] = {"active": ["start_with_full_energy"]}
    assembled = alyosha_assembled(payload=payload)

    assembled.simulator.run()

    precision = alyosha_helpers.precision_records(assembled, frame=420)
    assert len(precision) == 1
    assert precision[0].state.stack_count == 2
    assert len(alyosha_helpers.mastery_records(assembled, frame=420)) == 1
