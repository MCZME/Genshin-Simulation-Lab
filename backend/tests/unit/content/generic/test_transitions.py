"""通用衔接判定与四角色解释器 defer/reject 分流冒烟测试。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from genshin_sim.content.characters.mondstadt.barbara.actions import (
    BarbaraActionInterpreter,
)
from genshin_sim.content.characters.mondstadt.barbara.data import (
    BARBARA_ACTION_TABLE,
    BARBARA_CHARACTER_HANDLER_KEY,
    BARBARA_NORMAL_ATTACK_1_ACTION_KEY,
    INPUT_KIND_BY_KEY,
    NORMAL_ATTACK_INPUT,
)
from genshin_sim.content.characters.snezhnaya.alyosha.actions import (
    AlyoshaActionInterpreter,
)
from genshin_sim.content.characters.snezhnaya.alyosha.data import (
    ALYOSHA_ACTION_TABLE,
    ALYOSHA_CHARACTER_HANDLER_KEY,
    ALYOSHA_NORMAL_ATTACK_1_ACTION_KEY,
)
from genshin_sim.content.characters.snezhnaya.odette.actions import (
    OdetteActionInterpreter,
)
from genshin_sim.content.characters.snezhnaya.odette.data import (
    ODETTE_ACTION_TABLE,
    ODETTE_CHARACTER_HANDLER_KEY,
    ODETTE_NORMAL_ATTACK_1_ACTION_KEY,
)
from genshin_sim.content.characters.snezhnaya.sandrone.actions import (
    SandroneActionInterpreter,
)
from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    SANDRONE_ACTION_TABLE,
    SANDRONE_CHARACTER_HANDLER_KEY,
    SANDRONE_NORMAL_ATTACK_1_ACTION_KEY,
)
from genshin_sim.content.generic.chain_state import (
    CHAIN_STATE_LAST_ACTION_KEY,
    CHAIN_STATE_LAST_START_FRAME,
    chain_state_schema,
)
from genshin_sim.content.generic.timed_action import TimedActionSpec
from genshin_sim.content.generic.transitions import (
    TransitionVerdictKind,
    evaluate_transition,
)
from genshin_sim.core.actions import (
    ActionInterpretationContext,
    ActionInterpretationKind,
    ActionInterpretationTrigger,
    ActionOwnerRef,
    InputPhysicalState,
    InputSessionView,
)
from genshin_sim.core.entity_states import CharacterRuntimeState, ContentStateMount
from genshin_sim.core.simulation import IntentQueue, SimulationContext, TeamRuntimeState
from genshin_sim.core.space import Space, SpatialEntity, SpatialEntityKind, Vector3
from genshin_sim.core.space.runtime import SpaceRuntime

_TRANSITION_TABLE = {
    "previous": TimedActionSpec(
        action_key="previous",
        duration_frames=74,
        transitions={NORMAL_ATTACK_INPUT: 40},
    ),
    "no_transition": TimedActionSpec(
        action_key="no_transition",
        duration_frames=74,
        transitions={},
    ),
}


def test_evaluate_transition_returns_three_states():
    linkable = evaluate_transition(
        action_table=_TRANSITION_TABLE,
        display_name="测试",
        prev_action_key="",
        input_kind=NORMAL_ATTACK_INPUT,
        frame=1,
        prev_start_frame=0,
    )
    assert linkable.kind is TransitionVerdictKind.LINKABLE

    early = evaluate_transition(
        action_table=_TRANSITION_TABLE,
        display_name="测试",
        prev_action_key="previous",
        input_kind=NORMAL_ATTACK_INPUT,
        frame=10,
        prev_start_frame=0,
    )
    assert early.kind is TransitionVerdictKind.BEFORE_EARLIEST
    assert early.before_earliest
    assert early.earliest_frame == 40
    assert early.message == "测试动作 previous -> normal_attack 最早可在第 40 帧衔接"

    ready = evaluate_transition(
        action_table=_TRANSITION_TABLE,
        display_name="测试",
        prev_action_key="previous",
        input_kind=NORMAL_ATTACK_INPUT,
        frame=40,
        prev_start_frame=0,
    )
    assert ready.kind is TransitionVerdictKind.LINKABLE

    missing = evaluate_transition(
        action_table=_TRANSITION_TABLE,
        display_name="测试",
        prev_action_key="no_transition",
        input_kind=NORMAL_ATTACK_INPUT,
        frame=10,
        prev_start_frame=0,
    )
    assert missing.kind is TransitionVerdictKind.MISSING_DATA
    assert missing.missing_data
    assert missing.reject_message() == "测试动作缺少 no_transition -> normal_attack 的衔接数据"


def _interpreter_context(
    handler_key: str,
    *,
    last_action_key: str,
    last_start_frame: int,
) -> SimulationContext:
    """构造只含连段状态挂载与战场空间的最小上下文（无端口、无意图队列）。"""

    mount = ContentStateMount(
        handler_key,
        chain_state_schema("character:slot_1"),
        initial_values={
            CHAIN_STATE_LAST_ACTION_KEY: last_action_key,
            CHAIN_STATE_LAST_START_FRAME: last_start_frame,
        },
    )
    team_state = TeamRuntimeState(
        (
            CharacterRuntimeState(
                slot=1,
                character_key="character:test",
                level=90,
                content_states={handler_key: mount},
            ),
        ),
        active_slot=1,
    )
    context = SimulationContext()
    context.register_system(IntentQueue())
    context.space_runtime = SpaceRuntime(
        space=Space(
            [
                SpatialEntity(
                    "player:active",
                    SpatialEntityKind.ACTIVE_CHARACTER,
                    position=Vector3(),
                    active_slot=1,
                )
            ]
        ),
        team_state=team_state,
    )
    return context


def _session_view(*, current_frame: int) -> InputSessionView:
    return InputSessionView(
        session_id=1,
        key="mouse.left",
        trigger=ActionInterpretationTrigger.RELEASE,
        press_frame=1,
        current_frame=current_frame,
        held_frames=2,
        physical_state=InputPhysicalState.RELEASED,
        owner=ActionOwnerRef.character(1),
        release_frame=3,
    )


def _interpret(interpreter, context: SimulationContext, *, current_frame: int):
    return interpreter.interpret(
        ActionInterpretationContext(simulation=context),
        _session_view(current_frame=current_frame),
    )


@pytest.mark.parametrize(
    ("handler_key", "previous_action_key", "base_table", "interpreter_factory"),
    [
        (
            ALYOSHA_CHARACTER_HANDLER_KEY,
            ALYOSHA_NORMAL_ATTACK_1_ACTION_KEY,
            ALYOSHA_ACTION_TABLE,
            AlyoshaActionInterpreter,
        ),
        (
            BARBARA_CHARACTER_HANDLER_KEY,
            BARBARA_NORMAL_ATTACK_1_ACTION_KEY,
            BARBARA_ACTION_TABLE,
            BarbaraActionInterpreter,
        ),
        (
            ODETTE_CHARACTER_HANDLER_KEY,
            ODETTE_NORMAL_ATTACK_1_ACTION_KEY,
            ODETTE_ACTION_TABLE,
            OdetteActionInterpreter,
        ),
        (
            SANDRONE_CHARACTER_HANDLER_KEY,
            SANDRONE_NORMAL_ATTACK_1_ACTION_KEY,
            SANDRONE_ACTION_TABLE,
            SandroneActionInterpreter,
        ),
    ],
)
def test_interpreters_defer_before_earliest_and_reject_missing_data(
    handler_key: str,
    previous_action_key: str,
    base_table: dict[str, TimedActionSpec],
    interpreter_factory,
):
    assert INPUT_KIND_BY_KEY["mouse.left"] == NORMAL_ATTACK_INPUT

    # 以真实动作表为基础，只把一段普攻的衔接条目改为被测口径，保证后续连段
    # 动作仍在表内（否则 linkable 路径会因为查不到下一段而报错）。
    deferring = interpreter_factory(
        action_table={
            **base_table,
            previous_action_key: replace(
                base_table[previous_action_key],
                transitions={NORMAL_ATTACK_INPUT: 40},
            ),
        }
    )
    context = _interpreter_context(
        handler_key,
        last_action_key=previous_action_key,
        last_start_frame=0,
    )
    deferred = _interpret(deferring, context, current_frame=10)
    assert deferred.kind is ActionInterpretationKind.DEFER
    assert deferred.reason

    # 已到最早衔接帧：进入正常起手判定，不再 defer。
    linked = _interpret(deferring, context, current_frame=40)
    assert linked.kind is ActionInterpretationKind.START_ACTION

    rejecting = interpreter_factory(
        action_table={
            **base_table,
            previous_action_key: replace(base_table[previous_action_key], transitions={}),
        }
    )
    context = _interpreter_context(
        handler_key,
        last_action_key=previous_action_key,
        last_start_frame=0,
    )
    rejected = _interpret(rejecting, context, current_frame=10)
    assert rejected.kind is ActionInterpretationKind.REJECT
    assert rejected.reason and "衔接数据" in rejected.reason
