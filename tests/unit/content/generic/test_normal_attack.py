from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import pytest

from genshin_sim.content.generic.normal_attack import (
    ChainActionInterpreter,
    ChainInterpreterError,
    ChainSegmentSpec,
    ChainSpecValidationError,
    NormalAttackChainSpec,
    build_chain_actions,
    chain_state_schema,
)
from genshin_sim.content.state_container import StatePatchRequest
from genshin_sim.core.actions import (
    ActionInterpretationKind,
    ActionInterpretationTrigger,
    ActionOwnerRef,
    InputPhysicalState,
    InputSessionView,
)
from genshin_sim.core.contracts.intents import IntentKind
from genshin_sim.core.entity_states import CharacterRuntimeState, ContentStateMount
from genshin_sim.core.simulation.context import SimulationContext
from genshin_sim.core.simulation.intent_queue import IntentQueue
from genshin_sim.core.simulation.team import TeamRuntimeState


def _spec() -> NormalAttackChainSpec:
    return NormalAttackChainSpec(
        chain_key="character.test.normal_attack",
        segments=(
            ChainSegmentSpec(
                action_key="character.test.normal_attack.1",
                duration_frames=15,
                hit_frame=6,
                impact_key="character.test.normal_attack.1.hit",
                transitions={"normal_attack": 15},
            ),
            ChainSegmentSpec(
                action_key="character.test.normal_attack.2",
                duration_frames=20,
                hit_frame=8,
                impact_key="character.test.normal_attack.2.hit",
                transitions={"normal_attack": 20},
            ),
        ),
    )


def _session(
    *,
    trigger: ActionInterpretationTrigger = ActionInterpretationTrigger.RELEASE,
    frame: int = 10,
    release_frame: int = 10,
    key: str = "mouse.left",
) -> InputSessionView:
    return InputSessionView(
        session_id=1,
        key=key,
        trigger=trigger,
        press_frame=frame - 10,
        current_frame=frame,
        held_frames=10,
        physical_state=InputPhysicalState.RELEASED,
        owner=ActionOwnerRef.character(1),
        release_frame=release_frame if trigger is ActionInterpretationTrigger.RELEASE else None,
    )


def _runtime() -> tuple[SimulationContext, ContentStateMount, IntentQueue]:
    context = SimulationContext()
    schema = chain_state_schema("character:slot_1")
    mount = ContentStateMount(
        state_key=_spec().chain_key,
        schema=schema,
    )
    character = CharacterRuntimeState(
        slot=1,
        character_key="character:75",
        level=90,
        content_states={_spec().chain_key: mount},
    )
    team_state = TeamRuntimeState((character,))
    context.space_runtime = cast(Any, _FakeSpaceRuntime(team_state))
    queue = IntentQueue()
    context.register_system(queue)
    return context, mount, queue


@dataclass(frozen=True, slots=True)
class _FakeSpaceRuntime:
    team_state: TeamRuntimeState


def _settle_state_patches(
    queue: IntentQueue,
    mount: ContentStateMount,
) -> None:
    for intent in queue.drain_sorted():
        assert intent.kind is IntentKind.STATE_PATCH
        assert isinstance(intent.payload, StatePatchRequest)
        assert intent.payload.state_key == mount.state_key
        mount.apply_patch(intent.payload.fields)


def test_chain_segment_validates_impact_and_hit_frame_relationship():
    with pytest.raises(ChainSpecValidationError, match="hit_frame"):
        ChainSegmentSpec(
            action_key="a",
            duration_frames=10,
            impact_key="a.hit",
        )
    with pytest.raises(ChainSpecValidationError, match="小于 duration"):
        ChainSegmentSpec(
            action_key="a",
            duration_frames=10,
            hit_frame=10,
            impact_key="a.hit",
        )
    with pytest.raises(ChainSpecValidationError, match="impact_key"):
        ChainSegmentSpec(
            action_key="a",
            duration_frames=10,
            hit_frame=5,
        )


def test_chain_spec_rejects_duplicate_segment_keys():
    segment = ChainSegmentSpec(action_key="a", duration_frames=10)

    with pytest.raises(ChainSpecValidationError, match="不能重复"):
        NormalAttackChainSpec(
            chain_key="character.test.chain",
            segments=(segment, segment),
        )


def test_chain_state_schema_has_defaults():
    schema = chain_state_schema("character:slot_1")

    assert schema.defaults() == {
        "chain_last_action_key": "",
        "chain_last_start_frame": 0,
    }


def test_build_chain_actions_maps_segments_to_timed_actions():
    actions = build_chain_actions(_spec())

    assert [action.action_key for action in actions] == [
        "character.test.normal_attack.1",
        "character.test.normal_attack.2",
    ]
    first = actions[0]
    assert first.duration_frames == 15
    assert first.impact_keys == ("character.test.normal_attack.1.hit",)
    assert first.impact_frame_offsets == {"character.test.normal_attack.1.hit": 6}
    assert actions[1].impact_keys == ("character.test.normal_attack.2.hit",)


def test_interpreter_waits_on_press_and_hold():
    interpreter = ChainActionInterpreter(_spec())

    assert (
        interpreter.interpret(
            *_runtime()[:1], _session(trigger=ActionInterpretationTrigger.PRESS)
        ).kind
        is ActionInterpretationKind.WAIT
    )
    assert (
        interpreter.interpret(
            *_runtime()[:1], _session(trigger=ActionInterpretationTrigger.HOLD)
        ).kind
        is ActionInterpretationKind.WAIT
    )


def test_interpreter_starts_first_segment_and_queues_state_patch():
    interpreter = ChainActionInterpreter(_spec())
    context, mount, queue = _runtime()

    result = interpreter.interpret(context, _session())

    assert result.kind is ActionInterpretationKind.START_ACTION
    assert result.prepared_action is not None
    assert result.prepared_action.action_key == "character.test.normal_attack.1"
    assert queue.pending_count == 1
    intent = queue.drain_sorted()[0]
    assert intent.kind is IntentKind.STATE_PATCH
    assert intent.source_ref == "character.test.normal_attack"
    assert isinstance(intent.payload, StatePatchRequest)
    assert intent.payload.fields == {
        "chain_last_action_key": "character.test.normal_attack.1",
        "chain_last_start_frame": 10,
    }
    assert mount.values["chain_last_action_key"] == ""


def test_interpreter_rejects_early_transition():
    interpreter = ChainActionInterpreter(_spec())
    context, mount, queue = _runtime()
    interpreter.interpret(context, _session(frame=10, release_frame=10))
    _settle_state_patches(queue, mount)

    result = interpreter.interpret(context, _session(frame=20, release_frame=20))

    assert result.kind is ActionInterpretationKind.REJECT
    assert "最早可在第 25 帧" in (result.reason or "")


def test_interpreter_advances_after_transition_and_loops_at_end():
    interpreter = ChainActionInterpreter(_spec())
    context, mount, queue = _runtime()

    first = interpreter.interpret(context, _session(frame=10, release_frame=10))
    assert first.prepared_action is not None
    assert first.prepared_action.action_key == "character.test.normal_attack.1"
    _settle_state_patches(queue, mount)

    second = interpreter.interpret(context, _session(frame=25, release_frame=25))
    assert second.prepared_action is not None
    assert second.prepared_action.action_key == "character.test.normal_attack.2"
    _settle_state_patches(queue, mount)

    third = interpreter.interpret(context, _session(frame=45, release_frame=45))
    assert third.prepared_action is not None
    assert third.prepared_action.action_key == "character.test.normal_attack.1"


def test_interpreter_uses_segment_selector_override():
    def selector(last_key, segments):
        del last_key
        return segments[-1]

    interpreter = ChainActionInterpreter(
        _spec(),
        segment_selector=selector,
    )
    context, _mount, queue = _runtime()

    result = interpreter.interpret(context, _session())

    assert result.prepared_action is not None
    assert result.prepared_action.action_key == "character.test.normal_attack.2"
    assert queue.pending_count == 1


def test_interpreter_rejects_unknown_input_key():
    interpreter = ChainActionInterpreter(_spec())

    result = interpreter.interpret(
        _runtime()[0],
        _session(key="keyboard.e"),
    )

    assert result.kind is ActionInterpretationKind.REJECT
    assert "不支持输入" in (result.reason or "")


def test_interpreter_fails_deterministically_without_runtime_ports():
    interpreter = ChainActionInterpreter(_spec())
    context = SimulationContext()

    with pytest.raises(ChainInterpreterError, match="战场空间运行态"):
        interpreter.interpret(context, _session())

    context.space_runtime = cast(
        Any,
        _FakeSpaceRuntime(
            TeamRuntimeState(
                (CharacterRuntimeState(slot=1, character_key="character:75", level=90),)
            )
        ),
    )
    with pytest.raises(ChainInterpreterError, match="缺少内容状态段"):
        interpreter.interpret(context, _session())
