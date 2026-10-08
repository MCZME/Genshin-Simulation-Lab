"""输入缓冲 golden case：一段普攻期间连点，逐段衔接起手。

期望帧号来自仓库内已确认实测帧表 ``content/characters/snezhnaya/alyosha/data.py``
（V7.0 资料表）：一段普攻 N1 起手帧记 0 时，N1→N2 衔接 40、N2→N3 衔接 35、
N3→N4 衔接 72、N4→N1 衔接 60，故四段连打的起手帧相对偏移为
``N2@40 / N3@75 / N4@147 / N1@207``。本用例不引入任何新的外部资料。

用例用真实 ``AlyoshaActionInterpreter`` + 真实动作表驱动 ``ActionManager``，
只补齐解释器所需的最小运行态（连段状态挂载、意图队列结算、地面高度的战场空间），
不经资产库装配，因此不受本地资产库可用性影响。
"""

from __future__ import annotations

from typing import cast

from genshin_sim.content.characters.snezhnaya.alyosha.actions import (
    AlyoshaActionInterpreter,
    create_alyosha_actions,
)
from genshin_sim.content.characters.snezhnaya.alyosha.data import (
    ALYOSHA_CHARACTER_HANDLER_KEY,
    ALYOSHA_NORMAL_ATTACK_ACTION_KEYS,
)
from genshin_sim.content.generic.chain_state import chain_state_schema
from genshin_sim.content.state_container import StatePatchIntentHandler
from genshin_sim.core.actions import (
    ActionInterpreterRegistry,
    ActionManager,
    ActionRegistry,
    ActiveCharacterInterpreterSelector,
)
from genshin_sim.core.contracts.intents import IntentKind
from genshin_sim.core.entity_states import CharacterRuntimeState, ContentStateMount
from genshin_sim.core.events import (
    ActionStartedPayload,
    EventType,
    InputSessionDeferredPayload,
    InputSessionResolvedPayload,
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

_N1_START_FRAME = 2
_EXPECTED_START_FRAMES = [2, 42, 77, 149, 209]
_EXPECTED_ACTION_KEYS = [
    ALYOSHA_NORMAL_ATTACK_ACTION_KEYS[0],
    ALYOSHA_NORMAL_ATTACK_ACTION_KEYS[1],
    ALYOSHA_NORMAL_ATTACK_ACTION_KEYS[2],
    ALYOSHA_NORMAL_ATTACK_ACTION_KEYS[3],
    ALYOSHA_NORMAL_ATTACK_ACTION_KEYS[0],
]


def _click_frames() -> list[KeyInputFrame]:
    """5 次左键点按：第 1 次起手 N1，后 4 次在 N1 动画期间连点（各保持 1 帧）。"""

    frames: list[KeyInputFrame] = []
    press = 1
    for _ in range(5):
        frames.append(KeyInputFrame(press, (KeyEvent("mouse.left", KeyPhase.PRESS),)))
        frames.append(KeyInputFrame(press + 1, (KeyEvent("mouse.left", KeyPhase.RELEASE),)))
        press += 2
    return frames


def _resolved_record(payload: object) -> tuple[int, str, int | None]:
    """从终结事件载荷取出 (session_id, outcome, buffered_at_frame)。"""

    resolved = cast(InputSessionResolvedPayload, payload)
    return (resolved.session_id, resolved.outcome, resolved.buffered_at_frame)


def _build_runtime() -> tuple[ActionManager, SimulationContext, IntentSettlementRuntime]:
    mount = ContentStateMount(
        ALYOSHA_CHARACTER_HANDLER_KEY,
        chain_state_schema("character:slot_1"),
    )
    team_state = TeamRuntimeState(
        (
            CharacterRuntimeState(
                slot=1,
                character_key="character:alyosha",
                level=90,
                content_states={ALYOSHA_CHARACTER_HANDLER_KEY: mount},
            ),
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

    interpreter = AlyoshaActionInterpreter()
    registry = ActionInterpreterRegistry()
    registry.register("mouse.left", ActiveCharacterInterpreterSelector({1: interpreter}))
    manager = ActionManager(
        input_trace=InputTraceCompiler().compile(_click_frames()),
        interpreter_registry=registry,
        action_registry=ActionRegistry(create_alyosha_actions()),
    )
    return manager, context, settlement


def test_alyosha_consecutive_clicks_chain_through_buffered_inputs():
    manager, context, settlement = _build_runtime()
    started: list[tuple[int, str]] = []
    deferred: list[tuple[int, int]] = []
    resolved: list[tuple[int, str, int | None]] = []
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
    context.events.subscribe(
        EventType.INPUT_SESSION_RESOLVED,
        lambda event: resolved.append(_resolved_record(event.payload)),
    )

    stop_frame: int | None = None
    for frame in range(1, 1200):
        manager.update_frame(context, frame)
        settlement.settle_pending(context, frame, round=0)
        # 本用例不装配 ImpactRuntime，按它的分发语义消费到期影响点，
        # 使 is_idle() 的「无 pending 影响点」条件与真实仿真一致。
        for point in manager.due_impact_points(frame):
            manager.mark_impact_dispatched(point.impact_point_id)
        if manager.is_idle():
            stop_frame = frame
            break

    # 自然停止：动作链跑完且无待处理输入，不是被帧上限截断。
    assert stop_frame is not None
    assert stop_frame < 400

    assert [frame for frame, _key in started] == _EXPECTED_START_FRAMES
    assert [key for _frame, key in started] == _EXPECTED_ACTION_KEYS
    assert started[0][0] == _N1_START_FRAME

    # 连点的 4 个会话（session 2..5）全部经缓冲重评起手：缓冲进入帧即各自释放帧。
    assert deferred == [(4, 2), (6, 3), (8, 4), (10, 5)]
    assert resolved == [
        (1, "consumed", None),
        (2, "consumed", 4),
        (3, "consumed", 6),
        (4, "consumed", 8),
        (5, "consumed", 10),
    ]
