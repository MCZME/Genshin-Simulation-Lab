"""芭芭拉动作解释器代表行为：起手、连段衔接与取消。"""

from __future__ import annotations

from typing import cast

from genshin_sim.content.characters.mondstadt.barbara.actions import (
    BarbaraActionInterpreter,
)
from genshin_sim.content.characters.mondstadt.barbara.data import (
    BARBARA_CHARGED_ATTACK_ACTION_KEY,
    BARBARA_NORMAL_ATTACK_1_ACTION_KEY,
    BARBARA_NORMAL_ATTACK_2_ACTION_KEY,
    BARBARA_NORMAL_ATTACK_2_IMPACT_KEY,
)
from genshin_sim.content.generic.chain_state import (
    CHAIN_STATE_LAST_ACTION_KEY,
    CHAIN_STATE_LAST_START_FRAME,
)
from genshin_sim.core.actions import ActionInterpretationKind, TimedImpactAction


def test_barbara_interpreter_starts_first_normal_attack(
    barbara_release,
    barbara_runtime,
):
    interpreter = BarbaraActionInterpreter()
    runtime = barbara_runtime()

    interpretation = barbara_release(interpreter, "mouse.left", frame=10, runtime=runtime)

    assert interpretation.kind is ActionInterpretationKind.START_ACTION
    assert interpretation.prepared_action is not None
    assert interpretation.prepared_action.action_key == BARBARA_NORMAL_ATTACK_1_ACTION_KEY
    assert interpretation.prepared_action.requested_start_frame == 10
    assert interpretation.prepared_action.params["barbara_action_kind"] == "normal_attack"
    assert interpretation.prepared_action.params["barbara_hit_frame"] == 6


def test_barbara_normal_attack_chain_uses_confirmed_transition_frames(
    barbara_release,
    barbara_runtime,
    barbara_actions,
):
    interpreter = BarbaraActionInterpreter()
    runtime = barbara_runtime()

    barbara_release(interpreter, "mouse.left", frame=0, runtime=runtime)
    too_early = barbara_release(interpreter, "mouse.left", frame=14, runtime=runtime)
    chained = barbara_release(interpreter, "mouse.left", frame=15, runtime=runtime)

    assert too_early.kind is ActionInterpretationKind.REJECT
    assert too_early.reason is not None
    assert "最早可在第 15 帧衔接" in too_early.reason
    assert chained.kind is ActionInterpretationKind.START_ACTION
    assert chained.prepared_action is not None
    assert chained.prepared_action.action_key == BARBARA_NORMAL_ATTACK_2_ACTION_KEY
    assert runtime[1].values[CHAIN_STATE_LAST_ACTION_KEY] == (BARBARA_NORMAL_ATTACK_2_ACTION_KEY)
    assert runtime[1].values[CHAIN_STATE_LAST_START_FRAME] == 15
    assert cast(
        TimedImpactAction, barbara_actions[BARBARA_NORMAL_ATTACK_2_ACTION_KEY]
    ).impact_frame_offsets == {BARBARA_NORMAL_ATTACK_2_IMPACT_KEY: 11}


def test_barbara_normal_attack_can_cancel_into_charged_attack(
    barbara_release,
    barbara_runtime,
):
    interpreter = BarbaraActionInterpreter()
    runtime = barbara_runtime()

    barbara_release(interpreter, "mouse.left", frame=0, runtime=runtime)
    too_early = barbara_release(interpreter, "mouse.right", frame=17, runtime=runtime)
    charged = barbara_release(interpreter, "mouse.right", frame=18, runtime=runtime)

    assert too_early.kind is ActionInterpretationKind.REJECT
    assert "最早可在第 18 帧衔接" in (too_early.reason or "")
    assert charged.kind is ActionInterpretationKind.START_ACTION
    assert charged.prepared_action is not None
    assert charged.prepared_action.action_key == BARBARA_CHARGED_ATTACK_ACTION_KEY
