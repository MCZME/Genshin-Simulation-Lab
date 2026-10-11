"""generic 通用角色动作解释器单测：存活判定、连段窗口、门槛与覆写点默认行为。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import pytest

from genshin_sim.content.generic.chain_state import (
    CHAIN_STATE_LAST_ACTION_KEY,
    CHAIN_STATE_LAST_START_FRAME,
    chain_state_schema,
)
from genshin_sim.content.generic.character_actions import (
    CHARGED_ATTACK_INPUT,
    ELEMENTAL_BURST_INPUT,
    ELEMENTAL_SKILL_INPUT,
    JUMP_INPUT,
    NORMAL_ATTACK_INPUT,
    GenericAbilityGate,
    GenericCharacterActionError,
    GenericCharacterActionInterpreter,
    GenericCharacterActionSpec,
)
from genshin_sim.content.generic.timed_action import TimedActionSpec
from genshin_sim.content.state_container import StatePatchRequest
from genshin_sim.core.actions import (
    ActionInterpretationContext,
    ActionInterpretationKind,
    ActionInterpretationTrigger,
    ActionOwnerRef,
    InputPhysicalState,
    InputSessionView,
)
from genshin_sim.core.coordination.character_ability_condition.models import (
    CharacterAbilityConditionQuery,
)
from genshin_sim.core.coordination.character_ability_condition.protocols import (
    CharacterAbilityConditionPort,
)
from genshin_sim.core.entity_states import CharacterRuntimeState, ContentStateMount
from genshin_sim.core.simulation import IntentQueue, SimulationContext, TeamRuntimeState
from genshin_sim.core.space import Space, SpatialEntity, SpatialEntityKind, Vector3
from genshin_sim.core.space.runtime import SpaceRuntime

_NA_1_KEY = "test.na.1"
_NA_2_KEY = "test.na.2"
_CHARGED_KEY = "test.charged"
_SKILL_KEY = "test.skill"
_BURST_KEY = "test.burst"
_JUMP_KEY = "test.jump"
_PLUNGE_KEY = "test.plunge"

_NA_1_DURATION = 20

_ACTION_TABLE: dict[str, TimedActionSpec] = {
    _NA_1_KEY: TimedActionSpec(
        action_key=_NA_1_KEY,
        duration_frames=_NA_1_DURATION,
        hit_frame=6,
        impact_key=f"{_NA_1_KEY}.hit",
        transitions={NORMAL_ATTACK_INPUT: _NA_1_DURATION, CHARGED_ATTACK_INPUT: 18},
    ),
    _NA_2_KEY: TimedActionSpec(
        action_key=_NA_2_KEY,
        duration_frames=24,
        hit_frame=8,
        impact_key=f"{_NA_2_KEY}.hit",
        transitions={NORMAL_ATTACK_INPUT: 24, CHARGED_ATTACK_INPUT: 22},
    ),
    _CHARGED_KEY: TimedActionSpec(
        action_key=_CHARGED_KEY,
        duration_frames=60,
        hit_frame=30,
        impact_key=f"{_CHARGED_KEY}.hit",
        transitions={NORMAL_ATTACK_INPUT: 60},
    ),
    _SKILL_KEY: TimedActionSpec(
        action_key=_SKILL_KEY,
        duration_frames=40,
        hit_frame=12,
        impact_key=f"{_SKILL_KEY}.hit",
        transitions={NORMAL_ATTACK_INPUT: 40, JUMP_INPUT: 10},
    ),
    _BURST_KEY: TimedActionSpec(
        action_key=_BURST_KEY,
        duration_frames=50,
        transitions={NORMAL_ATTACK_INPUT: 50},
    ),
    _JUMP_KEY: TimedActionSpec(
        action_key=_JUMP_KEY,
        duration_frames=30,
        transitions={},
    ),
    _PLUNGE_KEY: TimedActionSpec(
        action_key=_PLUNGE_KEY,
        duration_frames=1,
        transitions={},
    ),
}

_SPEC = GenericCharacterActionSpec(
    display_name="测试角色",
    character_handler_key="character.test_action",
    input_kind_by_session_key={
        "mouse.left": NORMAL_ATTACK_INPUT,
        "keyboard.e": ELEMENTAL_SKILL_INPUT,
        "keyboard.q": ELEMENTAL_BURST_INPUT,
        "keyboard.space": JUMP_INPUT,
    },
    action_table=_ACTION_TABLE,
    normal_attack_action_keys=(_NA_1_KEY, _NA_2_KEY),
    plunge_action_key=_PLUNGE_KEY,
    plunge_collision_impact_key=f"{_PLUNGE_KEY}.collision",
    plunge_landing_impact_key=f"{_PLUNGE_KEY}.landing",
    elemental_skill_action_key=_SKILL_KEY,
    elemental_burst_action_key=_BURST_KEY,
    jump_action_key=_JUMP_KEY,
    charged_attack_action_key=_CHARGED_KEY,
    hold_input_min_frames=16,
    ability_gates=(
        GenericAbilityGate(
            input_kind=ELEMENTAL_SKILL_INPUT,
            ability_key="elemental_skill",
            blocked_message="测试角色元素战技冷却未就绪",
        ),
    ),
    action_kind_param_name="test_action_kind",
    hit_frame_param_name="test_hit_frame",
)


def _interpreter() -> GenericCharacterActionInterpreter:
    return GenericCharacterActionInterpreter(_SPEC)


def _context(
    *,
    last_action_key: str = "",
    last_start_frame: int = 0,
    height: float = 0.0,
) -> SimulationContext:
    mount = ContentStateMount(
        _SPEC.character_handler_key,
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
                content_states={_SPEC.character_handler_key: mount},
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
                    position=Vector3(0.0, height, 0.0),
                    active_slot=1,
                )
            ]
        ),
        team_state=team_state,
    )
    return context


def _session(
    *,
    key: str = "keyboard.e",
    current_frame: int,
    held_frames: int = 2,
) -> InputSessionView:
    return InputSessionView(
        session_id=1,
        key=key,
        trigger=ActionInterpretationTrigger.RELEASE,
        press_frame=max(current_frame - held_frames, 0),
        current_frame=current_frame,
        held_frames=held_frames,
        physical_state=InputPhysicalState.RELEASED,
        owner=ActionOwnerRef.character(1),
        release_frame=current_frame,
    )


def _interpret(
    context: SimulationContext,
    *,
    key: str = "keyboard.e",
    current_frame: int,
    held_frames: int = 2,
):
    return _interpreter().interpret(
        ActionInterpretationContext(simulation=context),
        _session(key=key, current_frame=current_frame, held_frames=held_frames),
    )


# --- R1 存活判定（issue #34） -------------------------------------------------


def test_skill_after_normal_attack_end_starts_skill():
    """普攻结束后再按 E：按「无前置动作」衔接，不再终局拒绝（issue #34）。"""

    result = _interpret(
        _context(last_action_key=_NA_1_KEY, last_start_frame=2),
        current_frame=2 + _NA_1_DURATION + 5,
    )
    assert result.kind is ActionInterpretationKind.START_ACTION
    assert result.prepared_action is not None
    assert result.prepared_action.action_key == _SKILL_KEY


def test_undeclared_input_during_live_action_still_rejected():
    """动作存活期内该行未声明的输入仍终局拒绝（契约不变）。"""

    result = _interpret(
        _context(last_action_key=_NA_1_KEY, last_start_frame=2),
        current_frame=10,
    )
    assert result.kind is ActionInterpretationKind.REJECT
    assert result.reason and "衔接数据" in result.reason


def test_input_after_jump_end_starts_action():
    """跳跃行整张衔接表为空，动作结束后任意输入可起手。"""

    result = _interpret(
        _context(last_action_key=_JUMP_KEY, last_start_frame=2),
        key="mouse.left",
        current_frame=100,
    )
    assert result.kind is ActionInterpretationKind.START_ACTION
    assert result.prepared_action is not None
    assert result.prepared_action.action_key == _NA_1_KEY


def test_normal_attack_before_earliest_defers():
    """存活期内早于最早衔接帧交管理器缓冲（时间结构条件）。"""

    result = _interpret(
        _context(last_action_key=_SKILL_KEY, last_start_frame=2),
        key="mouse.left",
        current_frame=10,
    )
    assert result.kind is ActionInterpretationKind.DEFER
    assert result.reason


# --- R1 下落豁免 ---------------------------------------------------------------


def test_plunge_landing_resets_chain_state():
    """下落落地（高度归零）后链状态重置，按无前置动作衔接。"""

    result = _interpret(
        _context(last_action_key=_PLUNGE_KEY, last_start_frame=2),
        key="mouse.left",
        current_frame=100,
    )
    assert result.kind is ActionInterpretationKind.START_ACTION
    assert result.prepared_action is not None
    assert result.prepared_action.action_key == _NA_1_KEY


def test_airborne_plunge_survives_beyond_placeholder_duration():
    """空中下落不受占位 duration_frames 判据影响：行内未声明输入仍终局拒绝。"""

    result = _interpret(
        _context(last_action_key=_PLUNGE_KEY, last_start_frame=2, height=5.0),
        current_frame=100,
    )
    assert result.kind is ActionInterpretationKind.REJECT
    assert result.reason and "衔接数据" in result.reason


# --- R2 连段窗口 ---------------------------------------------------------------


def test_combo_advances_at_window_boundary_frame():
    """连段窗口含结束帧：恰在 ``起手帧 + duration`` 按普攻推进下一段。"""

    result = _interpret(
        _context(last_action_key=_NA_1_KEY, last_start_frame=2),
        key="mouse.left",
        current_frame=2 + _NA_1_DURATION,
        held_frames=1,
    )
    assert result.kind is ActionInterpretationKind.START_ACTION
    assert result.prepared_action is not None
    assert result.prepared_action.action_key == _NA_2_KEY


def test_combo_resets_after_window_expiry():
    """连段窗口外按普攻回第一段，连段不无限存活。"""

    result = _interpret(
        _context(last_action_key=_NA_1_KEY, last_start_frame=2),
        key="mouse.left",
        current_frame=2 + _NA_1_DURATION + 1,
        held_frames=1,
    )
    assert result.kind is ActionInterpretationKind.START_ACTION
    assert result.prepared_action is not None
    assert result.prepared_action.action_key == _NA_1_KEY


def test_combo_resets_after_non_normal_attack_action():
    """重击/战技/爆发/跳跃之后按普攻回第一段。"""

    result = _interpret(
        _context(last_action_key=_SKILL_KEY, last_start_frame=2),
        key="mouse.left",
        current_frame=100,
    )
    assert result.kind is ActionInterpretationKind.START_ACTION
    assert result.prepared_action is not None
    assert result.prepared_action.action_key == _NA_1_KEY


# --- 左键双语义 -----------------------------------------------------------------


def test_hold_release_upgrades_to_charged():
    long_held = _interpret(
        _context(),
        key="mouse.left",
        current_frame=40,
        held_frames=17,
    )
    assert long_held.kind is ActionInterpretationKind.START_ACTION
    assert long_held.prepared_action is not None
    assert long_held.prepared_action.action_key == _CHARGED_KEY

    short_tap = _interpret(
        _context(),
        key="mouse.left",
        current_frame=40,
        held_frames=15,
    )
    assert short_tap.kind is ActionInterpretationKind.START_ACTION
    assert short_tap.prepared_action is not None
    assert short_tap.prepared_action.action_key == _NA_1_KEY


# --- 能力门槛 -------------------------------------------------------------------


@dataclass(frozen=True)
class _StubConditionResult:
    shared_conditions_satisfied: bool


class _StubConditionPort:
    def __init__(self, *, satisfied: bool) -> None:
        self._satisfied = satisfied

    def evaluate(self, query: CharacterAbilityConditionQuery) -> _StubConditionResult:
        return _StubConditionResult(shared_conditions_satisfied=self._satisfied)


def test_ability_gate_blocks_when_port_reports_unsatisfied():
    context = _context()
    result = _interpreter().interpret(
        ActionInterpretationContext(
            simulation=context,
            ability_condition_port=cast(
                CharacterAbilityConditionPort, _StubConditionPort(satisfied=False)
            ),
        ),
        _session(current_frame=100),
    )
    assert result.kind is ActionInterpretationKind.REJECT
    assert result.reason == "测试角色元素战技冷却未就绪"


def test_ability_gate_passes_when_port_reports_satisfied():
    context = _context()
    result = _interpreter().interpret(
        ActionInterpretationContext(
            simulation=context,
            ability_condition_port=cast(
                CharacterAbilityConditionPort, _StubConditionPort(satisfied=True)
            ),
        ),
        _session(current_frame=100),
    )
    assert result.kind is ActionInterpretationKind.START_ACTION


def test_gateless_input_kinds_are_not_blocked():
    """数据面未声明门槛的输入（普攻/爆发/跳跃）不被能力门槛阻断。"""

    result = _interpret(_context(), key="keyboard.q", current_frame=100)
    assert result.kind is ActionInterpretationKind.START_ACTION
    assert result.prepared_action is not None
    assert result.prepared_action.action_key == _BURST_KEY


# --- 起手状态补丁 ---------------------------------------------------------------


def test_start_patches_chain_state_with_selected_action():
    context = _context(last_action_key=_NA_1_KEY, last_start_frame=2)
    result = _interpret(
        context,
        key="mouse.left",
        current_frame=2 + _NA_1_DURATION,
        held_frames=1,
    )
    assert result.kind is ActionInterpretationKind.START_ACTION
    queue = cast(IntentQueue | None, context.get_system(IntentQueue))
    assert queue is not None
    intents = queue.drain_sorted()
    assert len(intents) == 1
    patch = cast(StatePatchRequest, intents[0].payload)
    assert patch.fields == {
        CHAIN_STATE_LAST_ACTION_KEY: _NA_2_KEY,
        CHAIN_STATE_LAST_START_FRAME: 2 + _NA_1_DURATION,
    }


# --- 状态损坏与配置校验 -----------------------------------------------------------


def test_unknown_chain_state_raises_deterministically():
    with pytest.raises(GenericCharacterActionError, match="未知测试角色动作状态"):
        _interpret(_context(last_action_key="test.ghost"), current_frame=100)


def test_unsupported_session_key_rejects():
    result = _interpret(_context(), key="keyboard.x", current_frame=100)
    assert result.kind is ActionInterpretationKind.REJECT
    assert result.reason and "不支持输入" in result.reason


def test_spec_rejects_charged_without_hold_threshold():
    with pytest.raises(ValueError, match="同时提供或同时缺省"):
        GenericCharacterActionSpec(
            display_name="测试角色",
            character_handler_key="character.test_action",
            input_kind_by_session_key={"mouse.left": NORMAL_ATTACK_INPUT},
            action_table=_ACTION_TABLE,
            normal_attack_action_keys=(_NA_1_KEY, _NA_2_KEY),
            plunge_action_key=_PLUNGE_KEY,
            plunge_collision_impact_key=f"{_PLUNGE_KEY}.collision",
            plunge_landing_impact_key=f"{_PLUNGE_KEY}.landing",
            elemental_skill_action_key=_SKILL_KEY,
            elemental_burst_action_key=_BURST_KEY,
            jump_action_key=_JUMP_KEY,
            charged_attack_action_key=_CHARGED_KEY,
        )


def test_spec_rejects_action_keys_missing_from_table():
    with pytest.raises(ValueError, match="动作表中不存在的动作键"):
        GenericCharacterActionSpec(
            display_name="测试角色",
            character_handler_key="character.test_action",
            input_kind_by_session_key={"mouse.left": NORMAL_ATTACK_INPUT},
            action_table=_ACTION_TABLE,
            normal_attack_action_keys=("test.missing",),
            plunge_action_key=_PLUNGE_KEY,
            plunge_collision_impact_key=f"{_PLUNGE_KEY}.collision",
            plunge_landing_impact_key=f"{_PLUNGE_KEY}.landing",
            elemental_skill_action_key=_SKILL_KEY,
            elemental_burst_action_key=_BURST_KEY,
            jump_action_key=_JUMP_KEY,
        )
