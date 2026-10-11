"""芭芭拉 / 奥黛塔左键点按/长按双语义（重击分界）解释器单测。

重击不占独立按键：左键按住时长达到分界常量按重击解释，未达到按点按普攻
解释；右键是冲刺位（按键输入契约），不映射重击。分界常量在无具体数据来源
时统一 30F（维护者口径，2026-10-11）。
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from genshin_sim.content.characters.mondstadt.barbara.actions import (
    BarbaraActionInterpreter,
)
from genshin_sim.content.characters.mondstadt.barbara.data import (
    BARBARA_CHARACTER_HANDLER_KEY,
    BARBARA_CHARGED_ATTACK_ACTION_KEY,
    BARBARA_HOLD_INPUT_MIN_FRAMES,
    BARBARA_NORMAL_ATTACK_1_ACTION_KEY,
)
from genshin_sim.content.characters.snezhnaya.odette.actions import (
    OdetteActionInterpreter,
)
from genshin_sim.content.characters.snezhnaya.odette.data import (
    ODETTE_CHARACTER_HANDLER_KEY,
    ODETTE_CHARGED_ATTACK_ACTION_KEY,
    ODETTE_HOLD_INPUT_MIN_FRAMES,
    ODETTE_NORMAL_ATTACK_1_ACTION_KEY,
)
from genshin_sim.content.generic.chain_state import (
    CHAIN_STATE_LAST_ACTION_KEY,
    CHAIN_STATE_LAST_START_FRAME,
    chain_state_schema,
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

_CASES = pytest.mark.parametrize(
    ("interpreter_factory", "handler_key", "hold_min_frames", "normal_key", "charged_key"),
    (
        pytest.param(
            BarbaraActionInterpreter,
            BARBARA_CHARACTER_HANDLER_KEY,
            BARBARA_HOLD_INPUT_MIN_FRAMES,
            BARBARA_NORMAL_ATTACK_1_ACTION_KEY,
            BARBARA_CHARGED_ATTACK_ACTION_KEY,
            id="barbara",
        ),
        pytest.param(
            OdetteActionInterpreter,
            ODETTE_CHARACTER_HANDLER_KEY,
            ODETTE_HOLD_INPUT_MIN_FRAMES,
            ODETTE_NORMAL_ATTACK_1_ACTION_KEY,
            ODETTE_CHARGED_ATTACK_ACTION_KEY,
            id="odette",
        ),
    ),
)


def _context(handler_key: str) -> SimulationContext:
    """构造只含连段状态挂载与战场空间的最小上下文（无端口、待机状态）。"""

    mount = ContentStateMount(
        handler_key,
        chain_state_schema("character:slot_1"),
        initial_values={CHAIN_STATE_LAST_ACTION_KEY: "", CHAIN_STATE_LAST_START_FRAME: 0},
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


def _release_session(*, key: str, held_frames: int) -> InputSessionView:
    return InputSessionView(
        session_id=1,
        key=key,
        trigger=ActionInterpretationTrigger.RELEASE,
        press_frame=1,
        current_frame=1 + held_frames,
        held_frames=held_frames,
        physical_state=InputPhysicalState.RELEASED,
        owner=ActionOwnerRef.character(1),
        release_frame=1 + held_frames,
    )


@_CASES
def test_right_click_is_not_a_charged_attack_input(
    interpreter_factory: Callable[[], BarbaraActionInterpreter | OdetteActionInterpreter],
    handler_key: str,
    hold_min_frames: int,
    normal_key: str,
    charged_key: str,
):
    result = interpreter_factory().interpret(
        ActionInterpretationContext(simulation=_context(handler_key)),
        _release_session(key="mouse.right", held_frames=hold_min_frames),
    )

    assert result.kind is ActionInterpretationKind.REJECT
    assert result.reason and "不支持输入" in result.reason


@_CASES
def test_left_hold_boundary_splits_normal_and_charged(
    interpreter_factory: Callable[[], BarbaraActionInterpreter | OdetteActionInterpreter],
    handler_key: str,
    hold_min_frames: int,
    normal_key: str,
    charged_key: str,
):
    below = interpreter_factory().interpret(
        ActionInterpretationContext(simulation=_context(handler_key)),
        _release_session(key="mouse.left", held_frames=hold_min_frames - 1),
    )
    at = interpreter_factory().interpret(
        ActionInterpretationContext(simulation=_context(handler_key)),
        _release_session(key="mouse.left", held_frames=hold_min_frames),
    )

    assert below.kind is ActionInterpretationKind.START_ACTION
    assert below.prepared_action is not None
    assert below.prepared_action.action_key == normal_key
    assert at.kind is ActionInterpretationKind.START_ACTION
    assert at.prepared_action is not None
    assert at.prepared_action.action_key == charged_key
