"""芭芭拉元素战技自潮湿效果的纵向集成。

只保留元素战技对施放者施加潮湿的接线验证；伤害、治疗、水环等
行为不在这里重复覆盖（见测试规范内容层边界）。
"""

from __future__ import annotations

from genshin_sim.core.elements import AuraKind, ElementalSubjectRef


def test_barbara_elemental_skill_cast_applies_self_wet(barbara_assembled):
    assembled = barbara_assembled(input_key="keyboard.e", max_frames=20)

    assembled.simulator.run()

    subject = ElementalSubjectRef.character("character:slot_1")
    assert assembled.aura_runtime.view(subject).component_for(AuraKind.HYDRO) is not None
