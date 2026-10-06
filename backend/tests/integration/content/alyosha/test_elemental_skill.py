"""阿罗夏骨架纵向集成：普攻直伤与 E 点按雷附着。

只保留骨架阶段「动作 -> 影响点 -> 伤害/附着」的接线验证；印记、创建物与
命座行为不在这里覆盖（随核心机制切片补测试，见测试规范内容层边界）。
"""

from __future__ import annotations

from genshin_sim.core.elements import AuraKind, ElementalSubjectRef
from tests.helpers import alyosha as alyosha_helpers


def test_elemental_skill_press_applies_electro_aura(alyosha_assembled):
    assembled = alyosha_assembled(input_key="keyboard.e", max_frames=80)

    assembled.simulator.run()

    subject = ElementalSubjectRef.target("target:target_1")
    assert assembled.aura_runtime.view(subject).component_for(AuraKind.ELECTRO) is not None


def test_elemental_skill_deals_electro_damage(alyosha_assembled):
    assembled = alyosha_assembled(input_key="keyboard.e", max_frames=80)
    events = alyosha_helpers.alyosha_damage_events(assembled)

    assembled.simulator.run()

    skill_hits = [event for event in events if event.payload.result.main_attack_tag == "元素战技"]
    assert len(skill_hits) == 1
    assert skill_hits[0].payload.result.damage_name == "点按伤害"


def test_normal_attack_combo_deals_physical_damage_per_segment(alyosha_assembled):
    # 连续左键：N1（命中 +21）在 40 帧衔接点后接 N2，两段各结算一次物理伤害。
    assembled = alyosha_assembled(
        input_key="mouse.left",
        max_frames=90,
        input_trace=[
            {"frame": 1, "events": [{"key": "mouse.left", "phase": "press"}]},
            {"frame": 2, "events": [{"key": "mouse.left", "phase": "release"}]},
            {"frame": 45, "events": [{"key": "mouse.left", "phase": "press"}]},
            {"frame": 46, "events": [{"key": "mouse.left", "phase": "release"}]},
        ],
    )
    events = alyosha_helpers.alyosha_damage_events(assembled)

    assembled.simulator.run()

    assert [e.payload.result.main_attack_tag for e in events] == ["普通攻击1", "普通攻击2"]
    # 普攻为物理，不携带雷附着证据：目标身上不应出现雷元素分量。
    subject = ElementalSubjectRef.target("target:target_1")
    assert assembled.aura_runtime.view(subject).component_for(AuraKind.ELECTRO) is None
