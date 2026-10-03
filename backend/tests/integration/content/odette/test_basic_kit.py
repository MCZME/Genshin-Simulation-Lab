"""奥黛塔基础招式（普攻/战技/特殊战技窗口/爆发）的纵向集成。

帧位与节奏数值来自维护者提供的 gcsim 动作帧数据、不作断言目标之外的
数值口径（测试规范 §3.3）；本文件锁定：普攻连段推进与三段双命中、
未转化普攻的物理口径、战技冰伤与附着、特殊战技 6 秒窗口分派与独立冷却、
爆发伤害越过动画结束帧的时间轴。
"""

from __future__ import annotations

from genshin_sim.content.characters.snezhnaya.odette.data import (
    ODETTE_CHARACTER_HANDLER_KEY,
    ODETTE_ELEMENTAL_SKILL_ACTION_KEY,
    ODETTE_SPECIAL_ELEMENTAL_SKILL_ACTION_KEY,
)
from genshin_sim.core.elements import Element
from tests.helpers import odette as odette_helpers

CHAIN_STATE_LAST_ACTION_KEY = "chain_last_action_key"


def _last_action_key(assembled) -> str | None:
    character = assembled.context.space_runtime.team_state.get_character(1)
    mount = character.content_states.get(ODETTE_CHARACTER_HANDLER_KEY)
    assert mount is not None
    value = mount.values.get(CHAIN_STATE_LAST_ACTION_KEY)
    assert isinstance(value, str)
    return value


def _release_trace(*press_release_frames: int) -> list[dict[str, object]]:
    """交替 press/release 轨迹：入参为 (press, release) 帧对展开序列。"""

    frames = list(press_release_frames)
    assert len(frames) % 2 == 0
    keys = ("mouse.left", "mouse.left", "mouse.left", "mouse.left")
    trace: list[dict[str, object]] = []
    for index in range(0, len(frames), 2):
        key = keys[(index // 2) % len(keys)]
        trace.append({"frame": frames[index], "events": [{"key": key, "phase": "press"}]})
        trace.append({"frame": frames[index + 1], "events": [{"key": key, "phase": "release"}]})
    return trace


def test_normal_attack_first_hit_is_physical(odette_assembled):
    assembled = odette_assembled(max_frames=40)
    damage_events = odette_helpers.odette_damage_events(assembled)

    assembled.simulator.run()

    hits = [e.payload.result for e in damage_events]
    assert [hit.main_attack_tag for hit in hits] == ["普通攻击1"]
    assert hits[0].element is Element.PHYSICAL
    assert hits[0].damage_name == "一段伤害"


def test_normal_attack_chain_third_segment_dual_hit(odette_assembled):
    # 连段三次点按：N1（起始 2，命中 11）→ N2（起始 21，命中 30）→
    # N3（起始 41，双命中 57/72）。三段为 3A/3B 两个影响点。
    payload = odette_helpers.odette_input_payload(
        max_frames=80,
        input_trace=_release_trace(1, 2, 20, 21, 40, 41),
    )
    assembled = odette_assembled(payload=payload)
    damage_events = odette_helpers.odette_damage_events(assembled)

    assembled.simulator.run()

    tags = [e.payload.result.main_attack_tag for e in damage_events]
    assert tags == ["普通攻击1", "普通攻击2", "普通攻击3", "普通攻击3"]
    frames = [e.payload.result.frame for e in damage_events]
    assert frames == [11, 30, 57, 72]
    names = [e.payload.result.damage_name for e in damage_events]
    assert names == ["一段伤害", "二段伤害", "三段伤害", "三段伤害"]


def test_elemental_skill_hits_cryo_and_arms_special_window(odette_assembled):
    # E 命中为冰元素；窗口内再次按 E（越过 E→E 衔接帧 43）分派特殊战技。
    payload = odette_helpers.odette_input_payload(
        max_frames=60,
        input_trace=[
            {"frame": 1, "events": [{"key": "keyboard.e", "phase": "press"}]},
            {"frame": 2, "events": [{"key": "keyboard.e", "phase": "release"}]},
            {"frame": 50, "events": [{"key": "keyboard.e", "phase": "press"}]},
            {"frame": 51, "events": [{"key": "keyboard.e", "phase": "release"}]},
        ],
    )
    assembled = odette_assembled(payload=payload)
    damage_events = odette_helpers.odette_damage_events(assembled)

    assembled.simulator.run()

    hits = [e.payload.result for e in damage_events]
    assert [hit.main_attack_tag for hit in hits] == ["元素战技"]
    assert hits[0].element is Element.CRYO
    assert hits[0].damage_name == "技能伤害"
    assert _last_action_key(assembled) == ODETTE_SPECIAL_ELEMENTAL_SKILL_ACTION_KEY


def test_special_window_expires_after_six_seconds(odette_assembled):
    # 窗口过期（>360 帧）后按 E 走普对战技路径：普对战技冷却未就绪 → 拒绝，
    # 状态停留在普对战技（若窗口误判为激活，特殊战技会启动并改写状态）。
    payload = odette_helpers.odette_input_payload(
        max_frames=420,
        input_trace=[
            {"frame": 1, "events": [{"key": "keyboard.e", "phase": "press"}]},
            {"frame": 2, "events": [{"key": "keyboard.e", "phase": "release"}]},
            {"frame": 400, "events": [{"key": "keyboard.e", "phase": "press"}]},
            {"frame": 401, "events": [{"key": "keyboard.e", "phase": "release"}]},
        ],
    )
    assembled = odette_assembled(payload=payload)

    assembled.simulator.run()

    assert _last_action_key(assembled) == ODETTE_ELEMENTAL_SKILL_ACTION_KEY


def test_elemental_burst_slash_timeline_across_animation_end(odette_assembled):
    # 爆发动画 126f 结束但伤害持续到 144f：四段斩击全部结算。
    payload = odette_helpers.odette_input_payload(
        max_frames=150,
        input_trace=[
            {"frame": 1, "events": [{"key": "keyboard.q", "phase": "press"}]},
            {"frame": 2, "events": [{"key": "keyboard.q", "phase": "release"}]},
        ],
    )
    payload["rules"] = {"active": ["start_with_full_energy"]}
    assembled = odette_assembled(payload=payload)
    damage_events = odette_helpers.odette_damage_events(assembled)

    assembled.simulator.run()

    hits = [e.payload.result for e in damage_events]
    assert [hit.main_attack_tag for hit in hits] == ["元素爆发"] * 4
    assert [hit.frame for hit in hits] == [114, 130, 142, 146]
    assert [hit.damage_name for hit in hits] == [
        "斩击伤害",
        "斩击伤害",
        "斩击伤害",
        "斩击最终段伤害",
    ]


def test_elemental_burst_arms_special_window(odette_assembled):
    # Q 施放同样解锁 6 秒窗口：Q→E 衔接帧 107 起按 E 分派特殊战技。
    payload = odette_helpers.odette_input_payload(
        max_frames=130,
        input_trace=[
            {"frame": 1, "events": [{"key": "keyboard.q", "phase": "press"}]},
            {"frame": 2, "events": [{"key": "keyboard.q", "phase": "release"}]},
            {"frame": 115, "events": [{"key": "keyboard.e", "phase": "press"}]},
            {"frame": 116, "events": [{"key": "keyboard.e", "phase": "release"}]},
        ],
    )
    payload["rules"] = {"active": ["start_with_full_energy"]}
    assembled = odette_assembled(payload=payload)

    assembled.simulator.run()

    assert _last_action_key(assembled) == ODETTE_SPECIAL_ELEMENTAL_SKILL_ACTION_KEY
