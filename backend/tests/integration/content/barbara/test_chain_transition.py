"""芭芭拉动作链路纵向集成：存活判定与连段窗口（issue #34 回归矩阵）。

帧位语义：解释发生在松开帧；普攻 N1 在第 2 帧起手、动作时长 15 帧，
连段窗口到第 17 帧（含结束帧）。本文件只锁定与帧位无关的行为接线，
帧位数值来自动作表数据、不作断言目标（测试规范 §3.3）。
"""

from __future__ import annotations

from genshin_sim.content.characters.mondstadt.barbara.data import (
    BARBARA_ELEMENTAL_SKILL_ACTION_KEY,
    BARBARA_HOLD_INPUT_MIN_FRAMES,
    BARBARA_JUMP_ACTION_KEY,
    BARBARA_NORMAL_ATTACK_1_ACTION_KEY,
    BARBARA_NORMAL_ATTACK_2_ACTION_KEY,
)
from genshin_sim.core.events import EventType
from tests.helpers import barbara as barbara_helpers

# N1 起手帧 = 首次左键松开帧（2），动作时长与连段窗口边界（含结束帧）。
_N1_START_FRAME = 2
_N1_DURATION = 15
_COMBO_WINDOW_END = _N1_START_FRAME + _N1_DURATION


def _started_action_keys(assembled) -> list[str]:
    started: list[str] = []
    assembled.context.events.subscribe(
        EventType.ACTION_STARTED,
        lambda event: started.append(event.payload.action_key),
    )
    assembled.simulator.run()
    return started


def test_skill_after_normal_attack_end_starts_skill(barbara_assembled):
    """普攻结束后按 E：按「无前置动作」衔接起手战技（issue #34 主场景）。"""

    assembled = barbara_assembled(
        input_trace=[
            *barbara_helpers.press_release(1, "mouse.left"),
            *barbara_helpers.press_release(_COMBO_WINDOW_END + 5, "keyboard.e"),
        ],
        max_frames=60,
    )

    assert _started_action_keys(assembled) == [
        BARBARA_NORMAL_ATTACK_1_ACTION_KEY,
        BARBARA_ELEMENTAL_SKILL_ACTION_KEY,
    ]


def test_combo_advances_within_window_and_resets_after(barbara_assembled):
    """连段窗口内按普攻推进下一段；窗口外回第一段（连段不无限存活）。

    解释发生在松开帧：窗口边界用例的松开帧恰为 ``起手帧 + 时长``。
    """

    within = barbara_assembled(
        input_trace=[
            *barbara_helpers.press_release(1, "mouse.left"),
            *barbara_helpers.press_release(_COMBO_WINDOW_END - 1, "mouse.left"),
        ],
        max_frames=60,
    )
    assert _started_action_keys(within) == [
        BARBARA_NORMAL_ATTACK_1_ACTION_KEY,
        BARBARA_NORMAL_ATTACK_2_ACTION_KEY,
    ]

    after = barbara_assembled(
        input_trace=[
            *barbara_helpers.press_release(1, "mouse.left"),
            *barbara_helpers.press_release(_COMBO_WINDOW_END, "mouse.left"),
        ],
        max_frames=60,
    )
    assert _started_action_keys(after) == [
        BARBARA_NORMAL_ATTACK_1_ACTION_KEY,
        BARBARA_NORMAL_ATTACK_1_ACTION_KEY,
    ]


def test_left_hold_boundary_splits_normal_and_charged(barbara_assembled):
    """左键点按/长按双语义：按住达到分界按重击解释，未达到按普攻解释。"""

    below = barbara_assembled(
        input_trace=barbara_helpers.press_release(
            1, "mouse.left", hold=BARBARA_HOLD_INPUT_MIN_FRAMES - 1
        ),
        max_frames=120,
    )
    assert _started_action_keys(below) == [BARBARA_NORMAL_ATTACK_1_ACTION_KEY]

    at = barbara_assembled(
        input_trace=barbara_helpers.press_release(
            1, "mouse.left", hold=BARBARA_HOLD_INPUT_MIN_FRAMES
        ),
        max_frames=120,
    )
    started = _started_action_keys(at)
    assert started[0] == "character.barbara.charged_attack"


def test_jump_then_normal_attack_after_jump_end(barbara_assembled):
    """跳跃行衔接表为空；跳跃结束后普攻可起手（按无前置动作衔接）。"""

    assembled = barbara_assembled(
        input_trace=[
            *barbara_helpers.press_release(1, "keyboard.space"),
            *barbara_helpers.press_release(50, "mouse.left"),
        ],
        max_frames=90,
    )

    started = _started_action_keys(assembled)
    assert started[0] == BARBARA_JUMP_ACTION_KEY
    assert started[-1] == BARBARA_NORMAL_ATTACK_1_ACTION_KEY
