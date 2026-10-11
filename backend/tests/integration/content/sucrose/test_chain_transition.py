"""砂糖动作链路纵向集成：存活判定与连段窗口（issue #34 回归矩阵）。

帧位语义：解释发生在松开帧；普攻 N1 在第 2 帧起手、动作时长 21 帧，
连段窗口到第 24 帧（含结束帧）。本文件只锁定与帧位无关的行为接线，
帧位数值来自动作表数据、不作断言目标（测试规范 §3.3）。
"""

from __future__ import annotations

from genshin_sim.content.characters.mondstadt.sucrose.data import (
    SUCROSE_ELEMENTAL_SKILL_ACTION_KEY,
    SUCROSE_HOLD_INPUT_MIN_FRAMES,
    SUCROSE_JUMP_ACTION_KEY,
    SUCROSE_NORMAL_ATTACK_1_ACTION_KEY,
    SUCROSE_NORMAL_ATTACK_2_ACTION_KEY,
)
from genshin_sim.core.events import EventType
from tests.helpers import sucrose as sucrose_helpers

# N1 起手帧 = 首次左键松开帧（2），动作时长与连段窗口边界（含结束帧）。
_N1_START_FRAME = 2
_N1_DURATION = 21
_COMBO_WINDOW_END = _N1_START_FRAME + _N1_DURATION


def _started_action_keys(assembled) -> list[str]:
    started: list[str] = []
    assembled.context.events.subscribe(
        EventType.ACTION_STARTED,
        lambda event: started.append(event.payload.action_key),
    )
    assembled.simulator.run()
    return started


def test_skill_after_normal_attack_end_starts_skill(sucrose_assembled):
    """普攻结束后按 E：按「无前置动作」衔接起手战技（issue #34 主场景）。"""

    assembled = sucrose_assembled(
        input_trace=[
            *sucrose_helpers.press_release(1, "mouse.left"),
            *sucrose_helpers.press_release(_COMBO_WINDOW_END + 5, "keyboard.e"),
        ],
        max_frames=60,
    )

    assert _started_action_keys(assembled) == [
        SUCROSE_NORMAL_ATTACK_1_ACTION_KEY,
        SUCROSE_ELEMENTAL_SKILL_ACTION_KEY,
    ]


def test_combo_advances_within_window_and_resets_after(sucrose_assembled):
    """连段窗口内按普攻推进下一段；窗口外回第一段（连段不无限存活）。

    解释发生在松开帧：窗口边界用例的松开帧恰为 ``起手帧 + 时长``。
    """

    within = sucrose_assembled(
        input_trace=[
            *sucrose_helpers.press_release(1, "mouse.left"),
            *sucrose_helpers.press_release(_COMBO_WINDOW_END - 1, "mouse.left"),
        ],
        max_frames=60,
    )
    assert _started_action_keys(within) == [
        SUCROSE_NORMAL_ATTACK_1_ACTION_KEY,
        SUCROSE_NORMAL_ATTACK_2_ACTION_KEY,
    ]

    after = sucrose_assembled(
        input_trace=[
            *sucrose_helpers.press_release(1, "mouse.left"),
            *sucrose_helpers.press_release(_COMBO_WINDOW_END, "mouse.left"),
        ],
        max_frames=60,
    )
    assert _started_action_keys(after) == [
        SUCROSE_NORMAL_ATTACK_1_ACTION_KEY,
        SUCROSE_NORMAL_ATTACK_1_ACTION_KEY,
    ]


def test_left_tap_below_hold_boundary_starts_normal_attack(sucrose_assembled):
    """点按（按住时长未达长按分界）按普攻解释，连段从第一段起手。"""

    assembled = sucrose_assembled(
        input_trace=sucrose_helpers.press_release(1, "mouse.left"),
        max_frames=40,
    )

    assert _started_action_keys(assembled) == [SUCROSE_NORMAL_ATTACK_1_ACTION_KEY]


def test_left_hold_at_boundary_starts_charged_attack(sucrose_assembled):
    """按住达到长按分界按重击解释。"""

    assembled = sucrose_assembled(
        input_trace=[
            {"frame": 1, "events": [{"key": "mouse.left", "phase": "press"}]},
            {
                "frame": 1 + SUCROSE_HOLD_INPUT_MIN_FRAMES,
                "events": [{"key": "mouse.left", "phase": "release"}],
            },
        ],
        max_frames=120,
    )

    started = _started_action_keys(assembled)
    assert started[0] == "character.sucrose.wind_spirit_creation.charged"


def test_jump_then_normal_attack_after_jump_end(sucrose_assembled):
    """跳跃行衔接表为空；跳跃结束后普攻可起手（按无前置动作衔接）。"""

    assembled = sucrose_assembled(
        input_trace=[
            *sucrose_helpers.press_release(1, "keyboard.space"),
            *sucrose_helpers.press_release(70, "mouse.left"),
        ],
        max_frames=100,
    )

    started = _started_action_keys(assembled)
    assert started[0] == SUCROSE_JUMP_ACTION_KEY
    assert started[-1] == SUCROSE_NORMAL_ATTACK_1_ACTION_KEY


def test_determinism_same_trace_same_actions(sucrose_assembled):
    """同配置同输入轨迹得到相同动作序列（确定性约定）。"""

    trace = [
        *sucrose_helpers.press_release(1, "mouse.left"),
        *sucrose_helpers.press_release(_COMBO_WINDOW_END - 1, "mouse.left"),
        *sucrose_helpers.press_release(_COMBO_WINDOW_END + 30, "keyboard.e"),
    ]

    first = _started_action_keys(sucrose_assembled(input_trace=trace, max_frames=80))
    second = _started_action_keys(sucrose_assembled(input_trace=trace, max_frames=80))

    assert first == second
    assert first == [
        SUCROSE_NORMAL_ATTACK_1_ACTION_KEY,
        SUCROSE_NORMAL_ATTACK_2_ACTION_KEY,
        SUCROSE_ELEMENTAL_SKILL_ACTION_KEY,
    ]
