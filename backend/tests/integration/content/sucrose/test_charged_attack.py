"""砂糖重击的纵向集成。

重击命中行使用「攻击盒」区域（实施规划 §6.2）：目标位于玩家锚点处时处于盒内。
本文件锁定命中帧、主攻击标签与倍率接线，不重复覆盖几何投影（由
``ImpactAreaSpec`` 单元测试承担）。
"""

from __future__ import annotations

import pytest

from tests.helpers import sucrose as sucrose_helpers

_CHARGED_TRACE = [
    *sucrose_helpers.press_release(1, "mouse.left"),
    *sucrose_helpers.press_release(240, "mouse.right"),
]


def test_charged_attack_hit_frame_and_tag(sucrose_assembled):
    assembled = sucrose_assembled(input_trace=_CHARGED_TRACE, max_frames=320)
    assembled.simulator.run()

    results = [record.result for record in assembled.damage_handler.records]
    assert [result.main_attack_tag for result in results] == ["普通攻击1", "重击"]
    # 重击起手帧 241 + hit_frame 54。
    assert [result.frame for result in results] == [16, 295]
    assert results[-1].damage_name == "重击伤害"


def test_charged_attack_ratio_follows_asset_scaling(sucrose_assembled):
    """合成倍率：一段 1.0、重击 5.0，故基础伤害比为 1:5。"""

    assembled = sucrose_assembled(input_trace=_CHARGED_TRACE, max_frames=320)
    assembled.simulator.run()

    base_damages = [record.result.base_damage for record in assembled.damage_handler.records]
    assert len(base_damages) == 2
    assert base_damages[1] == pytest.approx(base_damages[0] * 5)


def test_charged_attack_carries_element_and_crit_audit(sucrose_assembled):
    assembled = sucrose_assembled(input_trace=_CHARGED_TRACE, max_frames=320)
    assembled.simulator.run()

    charged = assembled.damage_handler.records[-1].result
    assert charged.element.value == "anemo"
    assert charged.final_damage > 0
    assert charged.official_damage > 0
