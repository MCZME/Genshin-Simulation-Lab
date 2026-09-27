"""桑多涅重击与法洁欧状态机的纵向集成（切片 2 临时测试）。

场景几何：玩家在原点、朝向 +Z，目标摆在 (0, 0, 4)——位于射击直线上，
子弹距离 4 → 飞行延迟 4 帧（60 m/s 占位 = 1 m/帧），射线即时穿透。
"""

from __future__ import annotations

from genshin_sim.core.elements import AuraKind, ElementalSubjectRef
from genshin_sim.core.events import EventType
from tests.helpers import sandrone as sandrone_helpers

SWEEP_DISPLAY_NAME = "重击扫射伤害"
RAY_DISPLAY_NAME = "重击冷凝射线伤害"
OVERLOAD_DISPLAY_NAME = "功率过载时伤害"


def _damage_events(assembled) -> list:
    """订阅 DAMAGE_RESOLVED 并返回活列表（运行期间持续填充）。"""

    events: list = []
    assembled.context.events.subscribe(EventType.DAMAGE_RESOLVED, events.append)
    return events


def _fageou_state(assembled) -> dict:
    character = assembled.context.space_runtime.team_state.get_character(1)
    mount = character.content_states.get("character.sandrone")
    assert mount is not None
    return dict(mount.values)


def _hold_trace(press_frame: int, release_frame: int) -> list[dict[str, object]]:
    """按住轨迹：输入契约要求按键在轨迹结束前释放，release 放在断言窗口之后。"""

    return [
        {"frame": press_frame, "events": [{"key": "mouse.right", "phase": "press"}]},
        {"frame": release_frame, "events": [{"key": "mouse.right", "phase": "release"}]},
    ]


def _sandrone_with_line_target(
    sandrone_assembled,
    *,
    input_trace: list[dict[str, object]],
    max_frames: int,
):
    payload = sandrone_helpers.sandrone_input_payload(
        max_frames=max_frames,
        input_trace=input_trace,
        targets=[
            {
                "id": "target_1",
                "level": 90,
                "position": {"x": 0, "y": 0, "z": 4},
                "resistance": {},
            }
        ],
    )
    return sandrone_assembled(max_frames=max_frames, payload=payload)


def test_solve_entry_fires_sweep_shots_on_rhythm(sandrone_assembled):
    # 按下 +36F 进入解算（solve_start=38）；扫射 21F 节奏：38/59/80 出膛，
    # 子弹距离 4 → 延迟 4 帧命中：42/63/84。
    assembled = _sandrone_with_line_target(
        sandrone_assembled,
        input_trace=_hold_trace(2, 88),
        max_frames=90,
    )
    damage_events = _damage_events(assembled)

    assembled.simulator.run()

    sweeps = [e for e in damage_events if e.payload.result.damage_name == SWEEP_DISPLAY_NAME]
    assert [e.frame for e in sweeps] == [42, 63, 84]
    for event in sweeps:
        assert event.payload.result.main_attack_tag == "重击"
        assert event.payload.result.element.value == "cryo"
    state = _fageou_state(assembled)
    # 输入契约要求松开（88 帧），松开即退出解算：终态待机、锚点清零。
    assert state["fageou_mode"] == "idle"
    assert state["fageou_solve_start_frame"] == 0


def test_ray_track_emerges_exactly_three_rays_before_overload(sandrone_assembled):
    # 核心不变量：0 命 0→100 恰好 3 发射线，第三发命中后封顶。
    # 射线 128/194/260（解算起算 +90、间隔 66）；功率 98 < 100 时第三发照常
    # 发射，命中后封顶转入过载 → 射线轨停止，无第四发。
    assembled = _sandrone_with_line_target(
        sandrone_assembled,
        input_trace=_hold_trace(2, 376),
        max_frames=380,
    )
    damage_events = _damage_events(assembled)

    assembled.simulator.run()

    rays = [e for e in damage_events if e.payload.result.damage_name == RAY_DISPLAY_NAME]
    assert [e.frame for e in rays] == [128, 194, 260]
    assert all(e.payload.result.main_attack_tag == "重击" for e in rays)
    # 过载射击 30F 节奏（过载起点 260 +30 起射，延迟 4 帧）；376 松开后停火。
    overloads = [e for e in damage_events if e.payload.result.damage_name == OVERLOAD_DISPLAY_NAME]
    assert [e.frame for e in overloads] == [294, 324, 354]
    state = _fageou_state(assembled)
    assert state["fageou_mode"] == "overload"
    # 按住过载功率冻结；松开（376）后至仿真结束仅衰减个别帧。
    assert 99.0 < state["fageou_power"] <= 100.0
    assert state["fageou_next_ray_frame"] == 0


def test_release_exits_solve_and_stops_tracks(sandrone_assembled):
    # 松开即退出解算：射线（128）不再发射，扫射在松开帧后停止。
    assembled = _sandrone_with_line_target(
        sandrone_assembled,
        input_trace=_hold_trace(2, 100),
        max_frames=180,
    )
    damage_events = _damage_events(assembled)

    assembled.simulator.run()

    sweeps = [e for e in damage_events if e.payload.result.damage_name == SWEEP_DISPLAY_NAME]
    assert [e.frame for e in sweeps] == [42, 63, 84]
    assert not [e for e in damage_events if e.payload.result.damage_name == RAY_DISPLAY_NAME]
    state = _fageou_state(assembled)
    assert state["fageou_mode"] == "idle"
    # 场上衰减 5.5/s：松开时功率约 20.7，仿真在输入耗尽后提前结束，
    # 只衰减了个别帧。
    assert 10.0 < state["fageou_power"] < 21.0


def test_overload_release_stops_overload_shots(sandrone_assembled):
    # 过载期间松开：停火（此后不再有过载伤害），模式保持过载、功率从冻结的
    # 100 开始衰减但未越过 50（仿真在输入耗尽后按空闲提前结束，完整的
    # "<50 退回待机" 由 fageou hook 单元测试覆盖）。
    assembled = _sandrone_with_line_target(
        sandrone_assembled,
        input_trace=_hold_trace(2, 300),
        max_frames=950,
    )
    damage_events = _damage_events(assembled)

    assembled.simulator.run()

    overloads = [e for e in damage_events if e.payload.result.damage_name == OVERLOAD_DISPLAY_NAME]
    assert overloads and max(e.frame for e in overloads) <= 304
    state = _fageou_state(assembled)
    assert state["fageou_mode"] == "overload"
    assert state["fageou_next_shot_frame"] == 0
    assert 90.0 < state["fageou_power"] <= 100.0


def test_elemental_skill_drains_power_and_stops_tracks(sandrone_assembled):
    # E 施放即退出解算并快速排空：扫射停火、射线取消、功率归零；
    # E 本体棱晶弹伤害照常结算。
    payload = sandrone_helpers.sandrone_input_payload(
        max_frames=140,
        input_trace=[
            {"frame": 2, "events": [{"key": "mouse.right", "phase": "press"}]},
            {"frame": 59, "events": [{"key": "keyboard.e", "phase": "press"}]},
            {"frame": 60, "events": [{"key": "keyboard.e", "phase": "release"}]},
            {"frame": 70, "events": [{"key": "mouse.right", "phase": "release"}]},
        ],
        targets=[
            {
                "id": "target_1",
                "level": 90,
                "position": {"x": 0, "y": 0, "z": 4},
                "resistance": {},
            }
        ],
    )
    assembled = sandrone_assembled(max_frames=140, payload=payload)
    damage_events = _damage_events(assembled)

    assembled.simulator.run()

    sweeps = [e for e in damage_events if e.payload.result.damage_name == SWEEP_DISPLAY_NAME]
    assert [e.frame for e in sweeps] == [42, 63]
    assert not [e for e in damage_events if e.payload.result.damage_name == RAY_DISPLAY_NAME]
    prisms = [e for e in damage_events if e.payload.result.damage_name == "棱晶弹伤害"]
    assert [e.frame for e in prisms] == [76, 92]
    state = _fageou_state(assembled)
    assert state["fageou_mode"] == "idle"
    assert state["fageou_power"] == 0.0
    assert state["fageou_drain_active"] is False


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


def test_line_geometry_misses_off_axis_target(sandrone_assembled):
    # 直线几何的诚实行为：横向偏移超出碰撞半径的目标不被扫射/射线命中。
    payload = sandrone_helpers.sandrone_input_payload(
        max_frames=140,
        input_trace=_hold_trace(2, 138),
        targets=[
            {
                "id": "target_1",
                "level": 90,
                "position": {"x": 3, "y": 0, "z": 4},
                "resistance": {},
            }
        ],
    )
    assembled = sandrone_assembled(max_frames=140, payload=payload)
    damage_events = _damage_events(assembled)

    assembled.simulator.run()

    charged = [
        e
        for e in damage_events
        if e.payload.result.damage_name
        in {SWEEP_DISPLAY_NAME, RAY_DISPLAY_NAME, OVERLOAD_DISPLAY_NAME}
    ]
    assert not charged
