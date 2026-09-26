"""法洁欧状态机 hook 的单元测试：功率动力学边界与模式退出门。

集成测试受仿真"输入耗尽即空闲结束"约束，衰减长尾与 <50 退出门在这里以
合成状态直接驱动验证。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import pytest

from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    FAGEOU_MODE_IDLE,
    FAGEOU_MODE_OVERLOAD,
    FAGEOU_MODE_SOLVE,
    FAGEOU_STATE_DRAIN_ACTIVE,
    FAGEOU_STATE_MODE,
    FAGEOU_STATE_NEXT_RAY_FRAME,
    FAGEOU_STATE_NEXT_SHOT_FRAME,
    FAGEOU_STATE_POWER,
    FAGEOU_STATE_SOLVE_START_FRAME,
)
from genshin_sim.content.characters.snezhnaya.sandrone.fageou import SandroneFageouHook
from genshin_sim.content.state_container import StatePatchRequest
from genshin_sim.core.events import EmptyPayload, EventType, GameEvent
from genshin_sim.core.impacts import DamageImpactSpec

SLOT = 1
OWNER_REF = "character:slot_1"


class _FakeContext:
    """只提供 hook.state(owner_ref) 读路径的最小上下文。"""

    def __init__(self, values: dict[str, object]) -> None:
        self._values = values

    def state(self, owner_ref: str) -> dict[str, object]:
        assert owner_ref == OWNER_REF
        return self._values


def _hook() -> SandroneFageouHook:
    return SandroneFageouHook(
        owner_ref=OWNER_REF,
        slot=SLOT,
        damage_specs=cast(
            Mapping[str, DamageImpactSpec],
            {
                "character.sandrone.charged_attack.sweep": object(),
                "character.sandrone.charged_attack.overload": object(),
                "character.sandrone.charged_attack.ray": object(),
            },
        ),
    )


def _event(frame: int) -> GameEvent:
    return GameEvent(EventType.FRAME_STARTED, frame=frame, payload=EmptyPayload())


def _state(
    *,
    mode: str | None = None,
    power: float | None = None,
    solve_start: int | None = None,
    next_shot: int | None = None,
    next_ray: int | None = None,
    drain: bool | None = None,
) -> dict[str, object]:
    base: dict[str, object] = {
        FAGEOU_STATE_MODE: FAGEOU_MODE_IDLE,
        FAGEOU_STATE_POWER: 0.0,
        FAGEOU_STATE_SOLVE_START_FRAME: 0,
        FAGEOU_STATE_NEXT_SHOT_FRAME: 0,
        FAGEOU_STATE_NEXT_RAY_FRAME: 0,
        FAGEOU_STATE_DRAIN_ACTIVE: False,
    }
    if mode is not None:
        base[FAGEOU_STATE_MODE] = mode
    if power is not None:
        base[FAGEOU_STATE_POWER] = power
    if solve_start is not None:
        base[FAGEOU_STATE_SOLVE_START_FRAME] = solve_start
    if next_shot is not None:
        base[FAGEOU_STATE_NEXT_SHOT_FRAME] = next_shot
    if next_ray is not None:
        base[FAGEOU_STATE_NEXT_RAY_FRAME] = next_ray
    if drain is not None:
        base[FAGEOU_STATE_DRAIN_ACTIVE] = drain
    return base


def _run_frames(
    hook: SandroneFageouHook,
    state: dict[str, object],
    frames: int,
    *,
    start: int = 10_000,
) -> list[dict[str, object]]:
    """逐帧驱动 hook（按真实管线语义应用 state_patch），返回状态快照。"""

    context = _FakeContext(state)
    snapshots = []
    for offset in range(frames):
        result = hook.handle(_event(start + offset), context)
        for patch in result.state_patches:
            assert isinstance(patch, StatePatchRequest)
            state.update(patch.fields)
        snapshots.append(dict(state))
    return snapshots


def test_idle_state_decays_power_at_field_rate():
    hook = _hook()
    state = _state(power=100.0)
    snapshots = _run_frames(hook, state, frames=600)

    # 场上衰减 5.5/s：600 帧（10s）后约 45。
    assert snapshots[-1][FAGEOU_STATE_POWER] == pytest.approx(100.0 - 5.5 * 10.0)
    assert snapshots[-1][FAGEOU_STATE_MODE] == FAGEOU_MODE_IDLE


def test_overload_released_exits_to_idle_below_threshold():
    hook = _hook()
    state = _state(mode=FAGEOU_MODE_OVERLOAD, power=51.0, next_shot=0)
    snapshots = _run_frames(hook, state, frames=30)

    # 51 → <50 需要约 11 帧衰减；越过阈值后模式回待机并继续衰减。
    assert all(s[FAGEOU_STATE_MODE] == FAGEOU_MODE_OVERLOAD for s in snapshots[:10])
    assert snapshots[-1][FAGEOU_STATE_MODE] == FAGEOU_MODE_IDLE
    assert cast(float, snapshots[-1][FAGEOU_STATE_POWER]) < 50.0


def test_solve_power_caps_and_flips_to_overload():
    hook = _hook()
    state = _state(mode=FAGEOU_MODE_SOLVE, power=99.5, solve_start=0, next_shot=0, next_ray=0)
    snapshots = _run_frames(hook, state, frames=5)

    # 上升封顶即转过载：射击轨换 30F 节奏、射线轨清零。
    flipped = next(s for s in snapshots if s[FAGEOU_STATE_MODE] == FAGEOU_MODE_OVERLOAD)
    assert cast(float, flipped[FAGEOU_STATE_POWER]) == 100.0
    assert cast(int, flipped[FAGEOU_STATE_NEXT_SHOT_FRAME]) > 0
    assert cast(int, flipped[FAGEOU_STATE_NEXT_RAY_FRAME]) == 0


def test_drain_empties_power_and_clears_flag():
    hook = _hook()
    state = _state(mode=FAGEOU_MODE_IDLE, power=100.0, drain=True)
    snapshots = _run_frames(hook, state, frames=35)

    # ≈200/s 排空：约 30 帧清零，随后排空标志复位。
    drained = next(s for s in snapshots if s[FAGEOU_STATE_POWER] == 0.0)
    assert drained[FAGEOU_STATE_DRAIN_ACTIVE] is False
    assert snapshots[-1][FAGEOU_STATE_POWER] == 0.0


def test_non_frame_started_events_are_ignored():
    hook = _hook()
    state = _state(power=10.0)
    result = hook.handle(
        GameEvent(EventType.SIMULATION_STARTED, frame=5, payload=EmptyPayload()),
        _FakeContext(state),
    )

    assert result.impact_requests == ()
    assert result.state_patches == ()
    assert state[FAGEOU_STATE_POWER] == 10.0
