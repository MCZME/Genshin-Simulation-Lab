"""阿罗夏重击纵向集成：前置一段普攻 + 突进段的完整重击链。

实现口径（规划文档 §3.1 重击行，2026-10-06 用户定案）：记录段即重击时序
（段长 55 帧、命中自段起点 +28，录制八参考口径），在前拼接第一段普攻
（帧位取 N1：时长 74、命中 +21）构成完整重击链；按住左键达到输入分界按
重击解释，快速点按仍走普攻连段。数值全部为合成数据（助手资产库）。
"""

from __future__ import annotations

from genshin_sim.content.characters.snezhnaya.alyosha.data import (
    ALYOSHA_CHARGED_PREFIX_FRAMES,
    ALYOSHA_CHARGED_PREFIX_HIT_FRAME_OFFSET,
    ALYOSHA_CHARGED_THRUST_HIT_FRAME_OFFSET,
)
from tests.helpers import alyosha as alyosha_helpers

PRESS_FRAME = 1
RELEASE_FRAME = 61
PREFIX_HIT_FRAME = RELEASE_FRAME + ALYOSHA_CHARGED_PREFIX_HIT_FRAME_OFFSET
THRUST_HIT_FRAME = (
    RELEASE_FRAME + ALYOSHA_CHARGED_PREFIX_FRAMES + ALYOSHA_CHARGED_THRUST_HIT_FRAME_OFFSET
)


def test_charged_attack_chain_deals_prefix_and_thrust_hits(alyosha_assembled):
    # 按住左键：完整重击链 = 一段普攻（命中 段起点 +21）+ 突进段（命中段
    # 起点 +28，即动作起点 +102），两段各结算一次；突进段属「重击」标签。
    assembled = alyosha_assembled(
        max_frames=200,
        input_trace=[
            {"frame": PRESS_FRAME, "events": [{"key": "mouse.left", "phase": "press"}]},
            {"frame": RELEASE_FRAME, "events": [{"key": "mouse.left", "phase": "release"}]},
        ],
    )
    events = alyosha_helpers.alyosha_damage_events(assembled)

    assembled.simulator.run()

    hits = [
        (e.frame, e.payload.result.damage_name, e.payload.result.main_attack_tag) for e in events
    ]
    assert hits == [
        (PREFIX_HIT_FRAME, "一段伤害", "普通攻击1"),
        (THRUST_HIT_FRAME, "重击伤害", "重击"),
    ]


def test_quick_tap_stays_normal_attack(alyosha_assembled):
    # 快速点按（按住 1 帧 < 输入分界）仍走普攻连段，不展开重击链。
    assembled = alyosha_assembled(max_frames=60)
    events = alyosha_helpers.alyosha_damage_events(assembled)

    assembled.simulator.run()

    names = [e.payload.result.damage_name for e in events]
    assert names == ["一段伤害"]
    assert "重击伤害" not in names


def test_charged_attack_does_not_apply_mark(alyosha_assembled):
    # 重击链两段（一段普攻前段 + 突进段）都不带「施加印记」标签：命中不
    # 施加弋猎印记（印记只随 NA4 与 E 命中施加）。
    assembled = alyosha_assembled(
        max_frames=200,
        input_trace=[
            {"frame": PRESS_FRAME, "events": [{"key": "mouse.left", "phase": "press"}]},
            {"frame": RELEASE_FRAME, "events": [{"key": "mouse.left", "phase": "release"}]},
        ],
    )

    assembled.simulator.run()

    assert not alyosha_helpers.mark_records(assembled, frame=200)


def test_charged_attack_restarts_normal_attack_combo(alyosha_assembled):
    # 重击不改变普攻连段位置：重击后下一次点按从一段普攻重新起手。
    assembled = alyosha_assembled(
        max_frames=240,
        input_trace=[
            {"frame": PRESS_FRAME, "events": [{"key": "mouse.left", "phase": "press"}]},
            {"frame": RELEASE_FRAME, "events": [{"key": "mouse.left", "phase": "release"}]},
            {"frame": 200, "events": [{"key": "mouse.left", "phase": "press"}]},
            {"frame": 201, "events": [{"key": "mouse.left", "phase": "release"}]},
        ],
    )
    events = alyosha_helpers.alyosha_damage_events(assembled)

    assembled.simulator.run()

    hits = [
        (e.frame, e.payload.result.damage_name, e.payload.result.main_attack_tag) for e in events
    ]
    # 第二次点按在 201 帧松开起手，N1 命中 +21。
    assert hits == [
        (PREFIX_HIT_FRAME, "一段伤害", "普通攻击1"),
        (THRUST_HIT_FRAME, "重击伤害", "重击"),
        (222, "一段伤害", "普通攻击1"),
    ]
