from __future__ import annotations

import pytest

from genshin_sim.core.simulation import (
    InputTraceCompiler,
    InputTraceError,
    KeyEvent,
    KeyInputFrame,
    KeyPhase,
)


def test_input_trace_compiler_pairs_sessions_and_preserves_boundary_order():
    trace = InputTraceCompiler().compile(
        [
            KeyInputFrame(
                1,
                (
                    KeyEvent("keyboard.2", KeyPhase.PRESS),
                    KeyEvent("keyboard.e", KeyPhase.PRESS),
                ),
            ),
            KeyInputFrame(
                4,
                (
                    KeyEvent("keyboard.e", KeyPhase.RELEASE),
                    KeyEvent("keyboard.2", KeyPhase.RELEASE),
                ),
            ),
        ]
    )

    session_summaries = [
        (session.session_id, session.key, session.held_frames) for session in trace.sessions
    ]
    assert session_summaries == [
        (1, "keyboard.2", 3),
        (2, "keyboard.e", 3),
    ]
    assert [(item.frame, item.order, item.session_id, item.phase) for item in trace.boundaries] == [
        (1, 0, 1, KeyPhase.PRESS),
        (1, 1, 2, KeyPhase.PRESS),
        (4, 0, 2, KeyPhase.RELEASE),
        (4, 1, 1, KeyPhase.RELEASE),
    ]
    assert [item.session_id for item in trace.boundaries_at(1)] == [1, 2]


@pytest.mark.parametrize(
    ("frames", "message"),
    [
        ([KeyInputFrame(0, ())], "输入帧号必须为正整数"),
        (
            [
                KeyInputFrame(1, (KeyEvent("keyboard.e", KeyPhase.PRESS),)),
                KeyInputFrame(1, (KeyEvent("keyboard.e", KeyPhase.RELEASE),)),
            ],
            "输入帧号必须严格递增",
        ),
        ([KeyInputFrame(1, ())], "第 1 帧必须至少包含一个输入事件"),
        (
            [KeyInputFrame(1, (KeyEvent("keyboard.w", KeyPhase.PRESS),))],
            "不支持的输入按键：keyboard.w",
        ),
        (
            [
                KeyInputFrame(
                    1,
                    (
                        KeyEvent("keyboard.e", KeyPhase.PRESS),
                        KeyEvent("keyboard.e", KeyPhase.RELEASE),
                    ),
                )
            ],
            "第 1 帧存在重复按键：keyboard.e",
        ),
        (
            [
                KeyInputFrame(1, (KeyEvent("keyboard.e", KeyPhase.PRESS),)),
                KeyInputFrame(2, (KeyEvent("keyboard.e", KeyPhase.PRESS),)),
            ],
            "按键已经处于按下状态：keyboard.e",
        ),
        (
            [KeyInputFrame(1, (KeyEvent("keyboard.e", KeyPhase.RELEASE),))],
            "按键在按下前被释放：keyboard.e",
        ),
        (
            [KeyInputFrame(1, (KeyEvent("keyboard.e", KeyPhase.PRESS),))],
            "输入轨迹结束时仍有按键未释放：keyboard.e",
        ),
    ],
)
def test_input_trace_compiler_validates_trace(
    frames: list[KeyInputFrame],
    message: str,
):
    with pytest.raises(InputTraceError, match=message):
        InputTraceCompiler().compile(frames)
