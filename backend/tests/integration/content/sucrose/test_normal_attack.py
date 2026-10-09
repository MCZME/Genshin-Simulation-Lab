"""砂糖普攻四段连段的纵向集成。

锁定三件事：① 连段推进按动作表逐段切换（普攻 1–4 循环）；② 每段命中帧等于
「起手帧 + 该段动作的 hit_frame」；③ 逐段倍率接线正确（合成倍率 1/2/3/4，
断言基础伤害比例，避开暴击与防御/抗性乘区）。

帧表数值本身由 ``data.py`` 与实施规划承担，这里只验证解释器与动作编译对这些
数据的消费是否正确。
"""

from __future__ import annotations

import pytest

from tests.helpers import sucrose as sucrose_helpers

# 四段连段输入：press 帧分别为 1 / 40 / 90 / 150，release 在下一帧；起手帧取
# release 帧，故各段起手帧为 2 / 41 / 91 / 151。
_COMBO_TRACE = [
    *sucrose_helpers.press_release(1),
    *sucrose_helpers.press_release(40),
    *sucrose_helpers.press_release(90),
    *sucrose_helpers.press_release(150),
]

_EXPECTED_COMBO_FRAMES = (16, 59, 118, 179)
_EXPECTED_SEGMENT_TAGS = ("普通攻击1", "普通攻击2", "普通攻击3", "普通攻击4")
_EXPECTED_DAMAGE_NAMES = ("一段伤害", "二段伤害", "三段伤害", "四段伤害")


def test_normal_attack_combo_advances_through_four_segments(sucrose_assembled):
    assembled = sucrose_assembled(input_trace=_COMBO_TRACE, max_frames=240)
    assembled.simulator.run()

    results = [record.result for record in assembled.damage_handler.records]

    assert [result.main_attack_tag for result in results] == list(_EXPECTED_SEGMENT_TAGS)
    assert [result.damage_name for result in results] == list(_EXPECTED_DAMAGE_NAMES)
    assert [result.frame for result in results] == list(_EXPECTED_COMBO_FRAMES)


def test_normal_attack_segment_ratios_follow_asset_scaling(sucrose_assembled):
    assembled = sucrose_assembled(input_trace=_COMBO_TRACE, max_frames=240)
    assembled.simulator.run()

    base_damages = [record.result.base_damage for record in assembled.damage_handler.records]
    assert len(base_damages) == 4

    unit = base_damages[0]
    for index, base_damage in enumerate(base_damages, start=1):
        assert base_damage == pytest.approx(unit * index)


def test_normal_attack_combo_restarts_at_first_segment_after_last(sucrose_assembled):
    """五连击：第四段之后回到普攻 1（动作表内循环推进）。"""

    trace = [
        *sucrose_helpers.press_release(1),
        *sucrose_helpers.press_release(40),
        *sucrose_helpers.press_release(90),
        *sucrose_helpers.press_release(150),
        *sucrose_helpers.press_release(210),
    ]
    assembled = sucrose_assembled(input_trace=trace, max_frames=300)
    assembled.simulator.run()

    tags = [record.result.main_attack_tag for record in assembled.damage_handler.records]
    assert tags == [
        "普通攻击1",
        "普通攻击2",
        "普通攻击3",
        "普通攻击4",
        "普通攻击1",
    ]


def test_unmapped_input_key_starts_nothing(sucrose_assembled):
    """S1 只开放普攻 / 重击 / 跳跃：元素战技输入键尚未映射，不产生任何动作。

    本条是分期边界保护——S2 接入元素战技输入映射时，本用例需要随期更新。
    """

    assembled = sucrose_assembled(
        input_trace=sucrose_helpers.press_release(1, "keyboard.e"),
        max_frames=60,
    )
    assembled.simulator.run()

    assert assembled.damage_handler.records == ()
