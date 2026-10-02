"""桑多涅重击与法洁欧状态机的纵向集成。

场景几何：玩家在原点、朝向 +Z，目标摆在 (0, 0, 4)——位于射击直线上，
射线即时穿透。帧位与节奏数值来自实测资料、不作断言目标（测试规范 §3.3）；
本文件只锁定与帧位无关的行为：输入改判（点按/长按边界）、状态机退出门、
附着接线与射程边界。
"""

from __future__ import annotations

from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    FAGEOU_RAY_LENGTH,
)
from genshin_sim.core.elements import AuraKind, ElementalSubjectRef
from tests.helpers import sandrone as sandrone_helpers

SWEEP_DISPLAY_NAME = "重击扫射伤害"
RAY_DISPLAY_NAME = "重击冷凝射线伤害"
OVERLOAD_DISPLAY_NAME = "功率过载时伤害"


def _fageou_state(assembled) -> dict:
    character = assembled.context.space_runtime.team_state.get_character(1)
    mount = character.content_states.get("character.sandrone")
    assert mount is not None
    return dict(mount.values)


def _hold_trace(press_frame: int, release_frame: int) -> list[dict[str, object]]:
    """长按轨迹：重击 = 长按左键（按下即蓄力），release 放在断言窗口之后。"""

    return [
        {"frame": press_frame, "events": [{"key": "mouse.left", "phase": "press"}]},
        {"frame": release_frame, "events": [{"key": "mouse.left", "phase": "release"}]},
    ]


def _hold_trace_args(input_trace: list[dict[str, object]]) -> tuple[int, int]:
    press = input_trace[0]["frame"]
    release = input_trace[1]["frame"]
    assert isinstance(press, int) and isinstance(release, int)
    return press, release


def _sandrone_with_line_target(
    sandrone_assembled,
    *,
    input_trace: list[dict[str, object]],
    max_frames: int,
):
    return sandrone_assembled(
        max_frames=max_frames,
        payload=sandrone_helpers.charged_line_payload(max_frames, *_hold_trace_args(input_trace)),
    )


def test_tap_below_pre_swing_becomes_normal_attack(sandrone_assembled):
    # 点按改判：按住不足前摇（28F < 36F）松开 = 点按普攻——清除本次按下写入
    # 的蓄力状态，普攻 1 起手命中，此后无任何扫射/射线。
    press_frame = 2
    release_frame = 30
    assembled = sandrone_assembled(
        max_frames=120,
        payload=sandrone_helpers.sandrone_input_payload(
            max_frames=120,
            input_trace=_hold_trace(press_frame, release_frame),
        ),
    )
    damage_events = sandrone_helpers.sandrone_damage_events(assembled)

    assembled.simulator.run()

    assert [e.payload.result.main_attack_tag for e in damage_events] == ["普通攻击1"]
    state = _fageou_state(assembled)
    assert state["fageou_mode"] == "idle"
    assert state["fageou_solve_start_frame"] == 0
    assert state["fageou_next_shot_frame"] == 0
    assert state["fageou_next_ray_frame"] == 0


def test_hold_at_pre_swing_boundary_is_charged_not_normal_attack(sandrone_assembled):
    # 前摇边界：按住跨过前摇（41F > 36F）后松开按重击处理——解算内首颗扫射
    # 出膛并命中，无普攻；松开即退出解算（锚点清零）。松开帧取在首颗扫射
    # 命中之后：更早松开会让仿真在输入耗尽后提前结束、丢掉该次命中结算。
    assembled = _sandrone_with_line_target(
        sandrone_assembled,
        input_trace=_hold_trace(2, 43),
        max_frames=60,
    )
    damage_events = sandrone_helpers.sandrone_damage_events(assembled)

    assembled.simulator.run()

    assert not [e for e in damage_events if e.payload.result.main_attack_tag == "普通攻击1"]
    sweeps = [e for e in damage_events if e.payload.result.damage_name == SWEEP_DISPLAY_NAME]
    assert sweeps, "跨过前摇的长按应产生扫射命中"
    state = _fageou_state(assembled)
    assert state["fageou_mode"] == "idle"
    assert state["fageou_solve_start_frame"] == 0


def test_sweep_shot_applies_cryo_via_custom_icd_sequence(sandrone_assembled):
    # 扫射弱冰附着走自定义 ICD 组（84F 窗口、序列 (1,0)）：窗口内首段附着。
    assembled = _sandrone_with_line_target(
        sandrone_assembled,
        input_trace=_hold_trace(2, 48),
        max_frames=50,
    )

    assembled.simulator.run()

    target_subject = ElementalSubjectRef.target("target:target_1")
    component = assembled.aura_runtime.view(target_subject).component_for(AuraKind.CRYO)
    assert component is not None


def test_bullet_range_cap_matches_ray_length(sandrone_assembled):
    # 射程上限与射线一致（12m）：正轴但超程的目标既不被扫射也不被射线命中，
    # 且不会排入在途子弹队列。
    payload = sandrone_helpers.sandrone_input_payload(
        max_frames=140,
        input_trace=_hold_trace(2, 138),
        targets=[
            {
                "id": "target_1",
                "level": 90,
                "position": {"x": 0, "y": 0, "z": FAGEOU_RAY_LENGTH + 2},
                "resistance": {},
            }
        ],
    )
    assembled = sandrone_assembled(max_frames=140, payload=payload)
    damage_events = sandrone_helpers.sandrone_damage_events(assembled)

    assembled.simulator.run()

    charged = [
        e
        for e in damage_events
        if e.payload.result.damage_name
        in {SWEEP_DISPLAY_NAME, RAY_DISPLAY_NAME, OVERLOAD_DISPLAY_NAME}
    ]
    assert charged == []
