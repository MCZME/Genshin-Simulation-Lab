"""奥黛塔动作链路纵向集成：存活判定、连段窗口与特殊战技窗口。

帧位语义：解释发生在松开帧；普攻 N1 在第 2 帧起手、动作时长 25 帧，
连段窗口到第 27 帧（含结束帧）；战技起手武装 360 帧特殊战技窗口。
本文件只锁定与帧位无关的行为接线，帧位数值来自动作表数据、不作断言
目标（测试规范 §3.3）。
"""

from __future__ import annotations

from genshin_sim.content.characters.snezhnaya.odette.data import (
    ODETTE_ELEMENTAL_SKILL_ACTION_KEY,
    ODETTE_JUMP_ACTION_KEY,
    ODETTE_NORMAL_ATTACK_1_ACTION_KEY,
    ODETTE_NORMAL_ATTACK_2_ACTION_KEY,
    ODETTE_SPECIAL_ELEMENTAL_SKILL_ACTION_KEY,
)
from genshin_sim.core.events import EventType
from tests.helpers import odette as odette_helpers

# N1 起手帧 = 首次左键松开帧（2），动作时长与连段窗口边界（含结束帧）。
_N1_START_FRAME = 2
_N1_DURATION = 25
_COMBO_WINDOW_END = _N1_START_FRAME + _N1_DURATION


def _started_action_keys(assembled) -> list[str]:
    started: list[str] = []
    assembled.context.events.subscribe(
        EventType.ACTION_STARTED,
        lambda event: started.append(event.payload.action_key),
    )
    assembled.simulator.run()
    return started


def test_skill_after_normal_attack_end_starts_skill(odette_assembled):
    """普攻结束后按 E：按「无前置动作」衔接起手战技（issue #34 场景）。"""

    assembled = odette_assembled(
        input_trace=[
            *odette_helpers.press_release(1, "mouse.left"),
            *odette_helpers.press_release(_COMBO_WINDOW_END + 5, "keyboard.e"),
        ],
        max_frames=60,
    )

    assert _started_action_keys(assembled) == [
        ODETTE_NORMAL_ATTACK_1_ACTION_KEY,
        ODETTE_ELEMENTAL_SKILL_ACTION_KEY,
    ]


def test_combo_advances_within_window_and_resets_after(odette_assembled):
    """连段窗口内按普攻推进下一段；窗口外回第一段（连段不无限存活）。"""

    within = odette_assembled(
        input_trace=[
            *odette_helpers.press_release(1, "mouse.left"),
            *odette_helpers.press_release(_COMBO_WINDOW_END - 1, "mouse.left"),
        ],
        max_frames=60,
    )
    assert _started_action_keys(within) == [
        ODETTE_NORMAL_ATTACK_1_ACTION_KEY,
        ODETTE_NORMAL_ATTACK_2_ACTION_KEY,
    ]

    after = odette_assembled(
        input_trace=[
            *odette_helpers.press_release(1, "mouse.left"),
            *odette_helpers.press_release(_COMBO_WINDOW_END, "mouse.left"),
        ],
        max_frames=60,
    )
    assert _started_action_keys(after) == [
        ODETTE_NORMAL_ATTACK_1_ACTION_KEY,
        ODETTE_NORMAL_ATTACK_1_ACTION_KEY,
    ]


def test_jump_then_normal_attack_after_jump_end(odette_assembled):
    """跳跃行衔接表为空；跳跃结束后普攻可起手（issue 影响表漏记的受害形态）。"""

    assembled = odette_assembled(
        input_trace=[
            *odette_helpers.press_release(1, "keyboard.space"),
            *odette_helpers.press_release(50, "mouse.left"),
        ],
        max_frames=90,
    )

    started = _started_action_keys(assembled)
    assert started[0] == ODETTE_JUMP_ACTION_KEY
    assert started[-1] == ODETTE_NORMAL_ATTACK_1_ACTION_KEY


def test_skill_within_special_window_casts_special_skill(odette_assembled):
    """窗口内的第二次 E 改走特殊战技：专属冷却门槛与动作键切换。"""

    assembled = odette_assembled(
        input_trace=[
            *odette_helpers.press_release(1, "keyboard.e"),
            *odette_helpers.press_release(60, "keyboard.e"),
        ],
        max_frames=160,
    )

    assert _started_action_keys(assembled) == [
        ODETTE_ELEMENTAL_SKILL_ACTION_KEY,
        ODETTE_SPECIAL_ELEMENTAL_SKILL_ACTION_KEY,
    ]
