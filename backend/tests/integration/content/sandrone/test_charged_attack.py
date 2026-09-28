"""桑多涅重击与法洁欧状态机的纵向集成。

场景几何：玩家在原点、朝向 +Z，目标摆在 (0, 0, 4)——位于射击直线上，
子弹距离 4，飞行延迟按占位弹速折算，射线即时穿透。帧序列期望值由 data.py
节奏常量推导（测试规范 §3.3：不复制数据真值）；射击次数由功率涌现与释放
窗口决定，保留字面断言。
"""

from __future__ import annotations

from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    FAGEOU_BULLET_SPEED_M_PER_S,
    FAGEOU_OVERLOAD_SHOT_INTERVAL_FRAMES,
    FAGEOU_POWER_MAX,
    FAGEOU_POWER_RISE_PER_SECOND,
    FAGEOU_PRE_SWING_FRAMES,
    FAGEOU_RAY_HIT_POWER_GAIN,
    FAGEOU_SOLVE_SHOT_INTERVAL_FRAMES,
    SANDRONE_ACTION_TABLE,
    SANDRONE_ELEMENTAL_SKILL_ACTION_KEY,
    SANDRONE_NORMAL_ATTACK_1_ACTION_KEY,
)
from genshin_sim.core.elements import AuraKind, ElementalSubjectRef
from tests.helpers import sandrone as sandrone_helpers

_PRESS_FRAME = 2
_SOLVE_START = _PRESS_FRAME + FAGEOU_PRE_SWING_FRAMES
# 目标距离 4m：子弹飞行帧 = round(4 / 占位弹速 × 60)。
_FLIGHT_FRAMES = round(4 / FAGEOU_BULLET_SPEED_M_PER_S * 60)

SWEEP_DISPLAY_NAME = "重击扫射伤害"
RAY_DISPLAY_NAME = "重击冷凝射线伤害"
OVERLOAD_DISPLAY_NAME = "功率过载时伤害"


def _sweep_hits(shot_count: int) -> list[int]:
    return [
        _SOLVE_START + k * FAGEOU_SOLVE_SHOT_INTERVAL_FRAMES + _FLIGHT_FRAMES
        for k in range(shot_count)
    ]


def _ray_frames(ray_count: int) -> list[int]:
    return sandrone_helpers.charged_ray_frames(_PRESS_FRAME, ray_count)


def _overload_hits(shot_count: int) -> list[int]:
    # 满功率转过载：翻转帧由功率动力学涌现——自然上升与三次射线命中增量
    # 恰好补满功率上限；射击轨自翻转帧 +30 起按过载间隔换节奏，命中含飞行帧。
    flip = _SOLVE_START + round(
        (FAGEOU_POWER_MAX - 3 * FAGEOU_RAY_HIT_POWER_GAIN) * 60 / FAGEOU_POWER_RISE_PER_SECOND
    )
    first = flip + FAGEOU_OVERLOAD_SHOT_INTERVAL_FRAMES + _FLIGHT_FRAMES
    return [first + k * FAGEOU_OVERLOAD_SHOT_INTERVAL_FRAMES for k in range(shot_count)]


def _na1_hit_frame(release_frame: int) -> int:
    hit = SANDRONE_ACTION_TABLE[SANDRONE_NORMAL_ATTACK_1_ACTION_KEY].hit_frame
    assert hit is not None
    return release_frame + hit


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


def _hold_trace_args(input_trace: list[dict[str, object]]) -> tuple[int, int]:
    press = input_trace[0]["frame"]
    release = input_trace[1]["frame"]
    assert isinstance(press, int) and isinstance(release, int)
    return press, release


def test_solve_entry_fires_sweep_shots_on_rhythm(sandrone_assembled):
    # 按下 + 前摇进入解算；扫射 21F 节奏出膛，子弹飞行 4 帧后命中。
    assembled = _sandrone_with_line_target(
        sandrone_assembled,
        input_trace=_hold_trace(2, 88),
        max_frames=90,
    )
    damage_events = sandrone_helpers.sandrone_damage_events(assembled)

    assembled.simulator.run()

    sweeps = [e for e in damage_events if e.payload.result.damage_name == SWEEP_DISPLAY_NAME]
    assert [e.frame for e in sweeps] == _sweep_hits(3)
    for event in sweeps:
        assert event.payload.result.main_attack_tag == "重击"
        assert event.payload.result.element.value == "cryo"
    state = _fageou_state(assembled)
    # 输入契约要求松开（88 帧），松开即退出解算：终态待机、锚点清零。
    assert state["fageou_mode"] == "idle"
    assert state["fageou_solve_start_frame"] == 0


def test_ray_track_emerges_exactly_three_rays_before_overload(sandrone_assembled):
    # 核心不变量：0 命 0→100 恰好 3 发射线，第三发命中后封顶。
    # 射线按解算起点 + 首法偏移与间隔推导；功率 98 < 100 时第三发照常
    # 发射，命中后封顶转入过载 → 射线轨停止，无第四发。
    assembled = _sandrone_with_line_target(
        sandrone_assembled,
        input_trace=_hold_trace(2, 376),
        max_frames=380,
    )
    damage_events = sandrone_helpers.sandrone_damage_events(assembled)

    assembled.simulator.run()

    rays = [e for e in damage_events if e.payload.result.damage_name == RAY_DISPLAY_NAME]
    assert [e.frame for e in rays] == _ray_frames(3)
    assert all(e.payload.result.main_attack_tag == "重击" for e in rays)
    # 过载射击 30F 节奏；376 松开后停火。
    overloads = [e for e in damage_events if e.payload.result.damage_name == OVERLOAD_DISPLAY_NAME]
    assert [e.frame for e in overloads] == _overload_hits(4)
    state = _fageou_state(assembled)
    assert state["fageou_mode"] == "overload"
    # 按住过载功率冻结；松开（376）后至仿真结束仅衰减个别帧。
    assert 99.0 < state["fageou_power"] <= 100.0
    assert state["fageou_next_ray_frame"] == 0


def test_release_exits_solve_and_stops_tracks(sandrone_assembled):
    # 松开即退出解算：首条射线（92）后再无射线（第二条在 152），扫射在松开
    # 帧后停止。松开帧（118）取在第五颗子弹出膛（120）之前，所有命中先于
    # 松开帧结算完毕。
    assembled = _sandrone_with_line_target(
        sandrone_assembled,
        input_trace=_hold_trace(2, 118),
        max_frames=180,
    )
    damage_events = sandrone_helpers.sandrone_damage_events(assembled)

    assembled.simulator.run()

    sweeps = [e for e in damage_events if e.payload.result.damage_name == SWEEP_DISPLAY_NAME]
    assert [e.frame for e in sweeps] == _sweep_hits(4)
    assert [e.frame for e in damage_events if e.payload.result.damage_name == RAY_DISPLAY_NAME] == (
        _ray_frames(1)
    )
    state = _fageou_state(assembled)
    assert state["fageou_mode"] == "idle"
    # 场上衰减 5.5/s：松开时功率 = 80F 自然上升 + 一次射线命中（约 38.7），
    # 仿真在输入耗尽后提前结束，只衰减了个别帧。
    assert 30.0 < state["fageou_power"] < 40.0


def test_overload_release_stops_overload_shots(sandrone_assembled):
    # 过载期间松开：停火（此后不再有过载伤害），模式保持过载、功率从冻结的
    # 100 开始衰减但未越过 50（仿真在输入耗尽后按空闲提前结束，完整的
    # "<50 退回待机" 由 fageou hook 单元测试覆盖）。
    assembled = _sandrone_with_line_target(
        sandrone_assembled,
        input_trace=_hold_trace(2, 300),
        max_frames=950,
    )
    damage_events = sandrone_helpers.sandrone_damage_events(assembled)

    assembled.simulator.run()

    overloads = [e for e in damage_events if e.payload.result.damage_name == OVERLOAD_DISPLAY_NAME]
    assert overloads and max(e.frame for e in overloads) <= 300 + _FLIGHT_FRAMES
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
            {"frame": 2, "events": [{"key": "mouse.left", "phase": "press"}]},
            {"frame": 59, "events": [{"key": "keyboard.e", "phase": "press"}]},
            {"frame": 60, "events": [{"key": "keyboard.e", "phase": "release"}]},
            {"frame": 70, "events": [{"key": "mouse.left", "phase": "release"}]},
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
    damage_events = sandrone_helpers.sandrone_damage_events(assembled)

    assembled.simulator.run()

    sweeps = [e for e in damage_events if e.payload.result.damage_name == SWEEP_DISPLAY_NAME]
    assert [e.frame for e in sweeps] == _sweep_hits(2)
    assert not [e for e in damage_events if e.payload.result.damage_name == RAY_DISPLAY_NAME]
    prism_frames = [
        60 + point.frame
        for point in SANDRONE_ACTION_TABLE[SANDRONE_ELEMENTAL_SKILL_ACTION_KEY].impact_points
    ]
    prisms = [e for e in damage_events if e.payload.result.damage_name == "棱晶弹伤害"]
    assert [e.frame for e in prisms] == prism_frames
    state = _fageou_state(assembled)
    assert state["fageou_mode"] == "idle"
    assert state["fageou_power"] == 0.0
    assert state["fageou_drain_active"] is False


def test_tap_below_pre_swing_becomes_normal_attack(sandrone_assembled):
    # 点按改判：按住不足前摇 36F（28F）松开 = 点按普攻——清除本次按下写入
    # 的蓄力状态，普攻 1 从松开帧起手，此后无任何扫射/射线。
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

    na1_hit = _na1_hit_frame(release_frame)
    assert [e.payload.result.main_attack_tag for e in damage_events] == ["普通攻击1"]
    assert damage_events[0].frame == na1_hit
    state = _fageou_state(assembled)
    assert state["fageou_mode"] == "idle"
    assert state["fageou_solve_start_frame"] == 0
    assert state["fageou_next_shot_frame"] == 0
    assert state["fageou_next_ray_frame"] == 0


def test_hold_at_pre_swing_boundary_is_charged_not_normal_attack(sandrone_assembled):
    # 前摇边界：按住跨过前摇 36F（41F）后松开按重击处理——解算内首颗扫射
    # 在 solve_start 出膛并命中，无普攻；松开即退出解算（锚点清零）。松开帧
    # 选在首颗扫射命中（solve_start + 4F 飞行）之后：在途子弹不在 world 空闲
    # 判定内，更早松开会让仿真在输入耗尽后提前结束、丢掉该次命中结算。
    assembled = _sandrone_with_line_target(
        sandrone_assembled,
        input_trace=_hold_trace(2, 43),
        max_frames=60,
    )
    damage_events = sandrone_helpers.sandrone_damage_events(assembled)

    assembled.simulator.run()

    assert not [e for e in damage_events if e.payload.result.main_attack_tag == "普通攻击1"]
    sweeps = [e for e in damage_events if e.payload.result.damage_name == SWEEP_DISPLAY_NAME]
    assert [e.frame for e in sweeps] == _sweep_hits(1)
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
    damage_events = sandrone_helpers.sandrone_damage_events(assembled)

    assembled.simulator.run()

    charged = [
        e
        for e in damage_events
        if e.payload.result.damage_name
        in {SWEEP_DISPLAY_NAME, RAY_DISPLAY_NAME, OVERLOAD_DISPLAY_NAME}
    ]
    assert charged == []
