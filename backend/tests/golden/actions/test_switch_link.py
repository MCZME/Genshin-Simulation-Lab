"""切人衔接 golden case：切人不得早于当前动作声明的可切人帧。

期望帧号全部来自仓库内已确认的动作帧表 ``content/characters/mondstadt/sucrose/data.py``：
砂糖重击 ``duration_frames=69``、命中帧 ``54``，衔接表
``普攻 69 / 重击 66 / 元素战技 60 / 元素爆发 61 / 跳跃 53``。切人列尚未逐条声明，
按「最早衔接帧」派生为 ``53``——即重击起手后 ``53`` 帧内按切人键必须推迟，
到 ``起手帧 + 53`` 才起手。本用例不引入任何新的外部资料。

用例用真实 ``GenericCharacterActionInterpreter(SUCROSE_ACTION_SPEC)`` 与真实动作表驱动
``ActionManager``，只补齐解释器所需的最小运行态（连段状态挂载、意图队列结算、
地面高度的战场空间），不经资产库装配。
"""

from __future__ import annotations

from typing import cast

from genshin_sim.content.characters.mondstadt.sucrose.data import (
    SUCROSE_ACTION_SPEC,
    SUCROSE_CHARACTER_HANDLER_KEY,
    SUCROSE_CHARGED_ATTACK_ACTION_KEY,
)
from genshin_sim.content.generic.action_link import SlotActionLinkPort
from genshin_sim.content.generic.chain_state import chain_state_schema
from genshin_sim.content.generic.character_actions import (
    GenericCharacterActionInterpreter,
    compile_character_actions,
)
from genshin_sim.content.state_container import StatePatchIntentHandler
from genshin_sim.core.actions import (
    TEAM_SWITCH_ACTION_KEY,
    TEAM_SWITCH_INTERRUPT_KIND,
    ActionInterpreterRegistry,
    ActionLifecycle,
    ActionManager,
    ActionRegistry,
    ActiveCharacterInterpreterSelector,
    TeamActionInterpreter,
    TeamInterpreterSelector,
    TeamSwitchAction,
)
from genshin_sim.core.contracts.intents import IntentKind
from genshin_sim.core.entity_states import CharacterRuntimeState, ContentStateMount
from genshin_sim.core.events import (
    ActionStartedPayload,
    EventType,
    InputSessionDeferredPayload,
)
from genshin_sim.core.simulation import (
    InputTraceCompiler,
    IntentQueue,
    IntentSettlementRuntime,
    KeyEvent,
    KeyInputFrame,
    KeyPhase,
    SimulationContext,
    TeamRuntimeState,
)
from genshin_sim.core.space import Space, SpatialEntity, SpatialEntityKind, Vector3
from genshin_sim.core.space.runtime import SpaceRuntime

# 重击起手帧：左键按住 19 帧（>= 16 帧分界）后松开，故在松开帧起手。
_HELD_ATTACK_START_FRAME = 20
# 切人键按下帧：落在重击起手后的衔接窗口内（起手 + 53 = 73 才可切）。
_SWITCH_PRESS_FRAME = 40
# 派生的可切人帧 = 重击起手帧 + 衔接表最早帧 53。
_EXPECTED_SWITCH_FRAME = _HELD_ATTACK_START_FRAME + 53


def _input_frames() -> list[KeyInputFrame]:
    """左键长按出重击，重击期间按切人键。"""

    return [
        KeyInputFrame(1, (KeyEvent("mouse.left", KeyPhase.PRESS),)),
        KeyInputFrame(_HELD_ATTACK_START_FRAME, (KeyEvent("mouse.left", KeyPhase.RELEASE),)),
        KeyInputFrame(_SWITCH_PRESS_FRAME, (KeyEvent("keyboard.2", KeyPhase.PRESS),)),
        KeyInputFrame(_SWITCH_PRESS_FRAME + 1, (KeyEvent("keyboard.2", KeyPhase.RELEASE),)),
    ]


def _build_runtime() -> tuple[ActionManager, SimulationContext, IntentSettlementRuntime]:
    mount = ContentStateMount(
        SUCROSE_CHARACTER_HANDLER_KEY,
        chain_state_schema("character:slot_1"),
    )
    team_state = TeamRuntimeState(
        (
            CharacterRuntimeState(
                slot=1,
                character_key="character:sucrose",
                level=90,
                content_states={SUCROSE_CHARACTER_HANDLER_KEY: mount},
            ),
            CharacterRuntimeState(slot=2, character_key="character:teammate", level=90),
        ),
        active_slot=1,
    )
    context = SimulationContext()
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
    intent_queue = IntentQueue()
    context.register_system(intent_queue)
    settlement = IntentSettlementRuntime(intent_queue)
    settlement.register(IntentKind.STATE_PATCH, StatePatchIntentHandler(team_state))

    interpreters = {1: GenericCharacterActionInterpreter(SUCROSE_ACTION_SPEC)}
    registry = ActionInterpreterRegistry()
    registry.register(
        "keyboard.2",
        TeamInterpreterSelector(
            TeamActionInterpreter(action_link_port=SlotActionLinkPort(interpreters))
        ),
    )
    registry.register("mouse.left", ActiveCharacterInterpreterSelector(interpreters))
    manager = ActionManager(
        input_trace=InputTraceCompiler().compile(_input_frames()),
        interpreter_registry=registry,
        action_registry=ActionRegistry(
            (*compile_character_actions(SUCROSE_ACTION_SPEC), TeamSwitchAction())
        ),
    )
    return manager, context, settlement


def test_switch_waits_until_current_action_declares_it_switchable():
    manager, context, settlement = _build_runtime()
    started: list[tuple[int, str]] = []
    deferred: list[tuple[int, int]] = []
    context.events.subscribe(
        EventType.ACTION_STARTED,
        lambda event: started.append(
            (event.frame, cast(ActionStartedPayload, event.payload).action_key)
        ),
    )
    context.events.subscribe(
        EventType.INPUT_SESSION_DEFERRED,
        lambda event: deferred.append(
            (event.frame, cast(InputSessionDeferredPayload, event.payload).session_id)
        ),
    )

    for frame in range(1, _EXPECTED_SWITCH_FRAME + 1):
        manager.update_frame(context, frame)
        settlement.settle_pending(context, frame, round=0)
        if frame < _EXPECTED_SWITCH_FRAME:
            # 到帧之前切人必须仍在缓冲：没有切人实例、场上角色不变。
            assert TEAM_SWITCH_ACTION_KEY not in [key for _frame, key in started]
            assert context.space_runtime is not None
            assert context.space_runtime.team_state.active_slot == 1

    # 重击在长按松开帧起手；切人键在衔接窗口内的按下帧进入缓冲。
    assert started == [
        (_HELD_ATTACK_START_FRAME, SUCROSE_CHARGED_ATTACK_ACTION_KEY),
        (_EXPECTED_SWITCH_FRAME, TEAM_SWITCH_ACTION_KEY),
    ]
    assert deferred == [(_SWITCH_PRESS_FRAME, 2)]

    # 切人在可切人帧起手，并中断旧角色的重击实例。
    charged = next(
        instance
        for instance in manager.instances
        if instance.action_key == SUCROSE_CHARGED_ATTACK_ACTION_KEY
    )
    assert charged.lifecycle is ActionLifecycle.CANCELED
    assert charged.cancel_reason == TEAM_SWITCH_INTERRUPT_KIND
    assert [point.status for point in charged.impact_points] == ["canceled"]
    assert context.space_runtime is not None
    assert context.space_runtime.team_state.active_slot == 2
