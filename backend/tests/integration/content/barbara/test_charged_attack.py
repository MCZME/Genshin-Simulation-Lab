"""芭芭拉左键点按/长按双语义（重击分界）的纵向集成。

重击不占独立按键：左键按住时长达到 ``BARBARA_HOLD_INPUT_MIN_FRAMES`` 按重击
解释，未达到按点按普攻解释；右键是冲刺位（按键输入契约），不映射重击。
"""

from __future__ import annotations

import pytest

from genshin_sim.content.characters.mondstadt.barbara.data import (
    BARBARA_CHARGED_ATTACK_ACTION_KEY,
    BARBARA_HOLD_INPUT_MIN_FRAMES,
    BARBARA_NORMAL_ATTACK_1_ACTION_KEY,
)
from genshin_sim.core.events import EventType


def _started_action_keys(assembled) -> list[str]:
    started: list[str] = []
    assembled.context.events.subscribe(
        EventType.ACTION_STARTED,
        lambda event: started.append(event.payload.action_key),
    )
    assembled.simulator.run()
    return started


def test_barbara_left_tap_starts_normal_attack(barbara_assembled):
    assembled = barbara_assembled(
        press_frame=1,
        release_frame=2,
        max_frames=20,
    )

    assert _started_action_keys(assembled) == [BARBARA_NORMAL_ATTACK_1_ACTION_KEY]


@pytest.mark.parametrize(
    ("held_frames", "expected_action_key"),
    (
        pytest.param(
            BARBARA_HOLD_INPUT_MIN_FRAMES - 1,
            BARBARA_NORMAL_ATTACK_1_ACTION_KEY,
            id="hold_below_boundary",
        ),
        pytest.param(
            BARBARA_HOLD_INPUT_MIN_FRAMES,
            BARBARA_CHARGED_ATTACK_ACTION_KEY,
            id="hold_at_boundary",
        ),
    ),
)
def test_barbara_left_hold_boundary_splits_normal_and_charged(
    barbara_assembled,
    held_frames: int,
    expected_action_key: str,
):
    assembled = barbara_assembled(
        press_frame=1,
        release_frame=1 + held_frames,
        max_frames=120,
    )

    assert _started_action_keys(assembled) == [expected_action_key]


def test_barbara_right_click_starts_no_action(barbara_assembled):
    # 右键是冲刺位（冲刺未接入），不再是重击输入位。
    assembled = barbara_assembled(
        input_key="mouse.right",
        max_frames=20,
    )

    assert _started_action_keys(assembled) == []
