from __future__ import annotations

from genshin_sim.content.characters.mondstadt.barbara import (
    BARBARA_CHARACTER_HANDLER_KEY,
    BARBARA_CHARGED_ATTACK_ACTION_KEY,
    BARBARA_CHARGED_ATTACK_IMPACT_KEY,
    BARBARA_ELEMENTAL_BURST_ACTION_KEY,
    BARBARA_ELEMENTAL_SKILL_ACTION_KEY,
    BARBARA_ELEMENTAL_SKILL_IMPACT_KEY,
    BARBARA_HIT_IMPACT_KEYS,
    BARBARA_JUMP_ACTION_KEY,
    BARBARA_JUMP_IMPACT_KEY,
    BARBARA_NORMAL_ATTACK_1_ACTION_KEY,
    BARBARA_NORMAL_ATTACK_1_IMPACT_KEY,
    BARBARA_NORMAL_ATTACK_2_ACTION_KEY,
    BARBARA_NORMAL_ATTACK_2_IMPACT_KEY,
    BarbaraActionInterpreter,
    BarbaraState,
    create_barbara_content,
)
from genshin_sim.content.registry import CharacterRuntimeRequest
from genshin_sim.core.actions import (
    ActionInterpretation,
    ActionInterpretationKind,
    ActionInterpretationTrigger,
    InputActionSession,
)
from genshin_sim.core.simulation import SimulationContext


def test_barbara_interpreter_schedules_first_normal_attack_with_hit_frame():
    interpreter = BarbaraActionInterpreter()

    interpretation = _release(interpreter, "mouse.left", frame=10)

    assert interpretation.kind is ActionInterpretationKind.SCHEDULE_TIMELINE
    assert interpretation.timeline is not None
    assert interpretation.timeline.action_key == BARBARA_NORMAL_ATTACK_1_ACTION_KEY
    assert interpretation.timeline.start_frame == 10
    assert interpretation.timeline.duration_frames == 15
    assert interpretation.timeline.impact_keys == (BARBARA_NORMAL_ATTACK_1_IMPACT_KEY,)
    assert interpretation.timeline.impact_frame_offsets == {
        BARBARA_NORMAL_ATTACK_1_IMPACT_KEY: 6
    }


def test_barbara_normal_attack_chain_uses_confirmed_transition_frames():
    interpreter = BarbaraActionInterpreter()

    _release(interpreter, "mouse.left", frame=0)
    too_early = _release(interpreter, "mouse.left", frame=14)
    chained = _release(interpreter, "mouse.left", frame=15)

    assert too_early.kind is ActionInterpretationKind.REJECT
    assert too_early.reason is not None
    assert "最早可在第 15 帧衔接" in too_early.reason
    assert chained.kind is ActionInterpretationKind.SCHEDULE_TIMELINE
    assert chained.timeline is not None
    assert chained.timeline.action_key == BARBARA_NORMAL_ATTACK_2_ACTION_KEY
    assert chained.timeline.impact_frame_offsets == {
        BARBARA_NORMAL_ATTACK_2_IMPACT_KEY: 11
    }


def test_barbara_missing_transition_data_rejects_input():
    interpreter = BarbaraActionInterpreter()

    _release(interpreter, "mouse.left", frame=0)
    interpretation = _release(interpreter, "keyboard.e", frame=99)

    assert interpretation.kind is ActionInterpretationKind.REJECT
    assert interpretation.reason is not None
    assert "缺少" in interpretation.reason
    assert "elemental_skill" in interpretation.reason


def test_barbara_charged_attack_can_link_to_burst_at_confirmed_frame():
    interpreter = BarbaraActionInterpreter()

    charged = _release(interpreter, "mouse.right", frame=0)
    too_early = _release(interpreter, "keyboard.q", frame=86)
    burst = _release(interpreter, "keyboard.q", frame=87)

    assert charged.kind is ActionInterpretationKind.SCHEDULE_TIMELINE
    assert charged.timeline is not None
    assert charged.timeline.action_key == BARBARA_CHARGED_ATTACK_ACTION_KEY
    assert charged.timeline.impact_frame_offsets == {BARBARA_CHARGED_ATTACK_IMPACT_KEY: 55}
    assert too_early.kind is ActionInterpretationKind.REJECT
    assert burst.kind is ActionInterpretationKind.SCHEDULE_TIMELINE
    assert burst.timeline is not None
    assert burst.timeline.action_key == BARBARA_ELEMENTAL_BURST_ACTION_KEY
    assert burst.timeline.impact_keys == ()


def test_barbara_elemental_skill_jump_transition_uses_early_cancel_frame():
    interpreter = BarbaraActionInterpreter()

    skill = _release(interpreter, "keyboard.e", frame=3)
    too_early = _release(interpreter, "keyboard.space", frame=7)
    jump = _release(interpreter, "keyboard.space", frame=8)

    assert skill.kind is ActionInterpretationKind.SCHEDULE_TIMELINE
    assert skill.timeline is not None
    assert skill.timeline.action_key == BARBARA_ELEMENTAL_SKILL_ACTION_KEY
    assert skill.timeline.duration_frames == 5
    assert skill.timeline.impact_frame_offsets == {BARBARA_ELEMENTAL_SKILL_IMPACT_KEY: 42}
    assert too_early.kind is ActionInterpretationKind.REJECT
    assert jump.kind is ActionInterpretationKind.SCHEDULE_TIMELINE
    assert jump.timeline is not None
    assert jump.timeline.action_key == BARBARA_JUMP_ACTION_KEY
    assert jump.timeline.impact_frame_offsets == {BARBARA_JUMP_IMPACT_KEY: 31}


def test_barbara_content_contribution_registers_action_state_machine():
    contribution = create_barbara_content(
        CharacterRuntimeRequest(
            handler_key=BARBARA_CHARACTER_HANDLER_KEY,
            character_key="character:10000014",
            slot=1,
            params={},
        )
    )

    assert contribution.handler_key == BARBARA_CHARACTER_HANDLER_KEY
    assert contribution.action_interpreter is not None
    assert contribution.state_extension == BarbaraState()
    assert tuple(contribution.impact_factories) == BARBARA_HIT_IMPACT_KEYS


def _release(
    interpreter: BarbaraActionInterpreter,
    key: str,
    *,
    frame: int,
) -> ActionInterpretation:
    session = InputActionSession(
        session_id=frame + 1,
        key=key,
        owner_slot_at_press=1,
        press_frame=frame,
        release_frame=frame,
    )
    return interpreter.interpret(
        SimulationContext(),
        session,
        ActionInterpretationTrigger.RELEASE,
    )
