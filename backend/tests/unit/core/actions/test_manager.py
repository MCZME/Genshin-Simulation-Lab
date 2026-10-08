from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, cast

import pytest

from genshin_sim.core.actions import (
    TEAM_SWITCH_ACTION_KEY,
    TEAM_SWITCH_TARGET_SLOT_PARAM,
    ActionAdmissionPolicy,
    ActionDecisionRejectReason,
    ActionInterpretationContext,
    ActionInterpretationResult,
    ActionInterpretationTrigger,
    ActionInterpreterRegistry,
    ActionInterruptPolicy,
    ActionManager,
    ActionOwnerRef,
    ActionRegistry,
    ActiveCharacterInterpreterSelector,
    InputControlState,
    InputSessionView,
    PreparedAction,
    SearchAreaSpec,
    TargetingSpec,
    TeamActionInterpreter,
    TeamInterpreterSelector,
    TeamSwitchAction,
    TimedImpactAction,
)
from genshin_sim.core.entity_states import CharacterRuntimeState
from genshin_sim.core.events import (
    EventType,
    InputSessionBoundaryPayload,
    InputSessionDeferredPayload,
    InputSessionResolvedPayload,
    TeamSwitchedPayload,
)
from genshin_sim.core.simulation import (
    InputTraceCompiler,
    KeyEvent,
    KeyInputFrame,
    KeyPhase,
    SimulationContext,
    TeamRuntimeState,
)
from genshin_sim.core.space import Space, SpatialEntity, SpatialEntityKind, Vector3
from genshin_sim.core.space.runtime import SpaceRuntime
from genshin_sim.core.systems.cooldown import (
    AbilityKind,
    CooldownDefinition,
    CooldownDurationMode,
    CooldownDurationOperation,
    CooldownDurationStage,
    CooldownDurationTerm,
    CooldownKey,
    CooldownRuntime,
    CooldownStore,
    CooldownSubjectRef,
)


@dataclass(slots=True)
class ReleaseStartInterpreter:
    action_by_key: dict[str, str]
    views: list[InputSessionView] = field(default_factory=list)
    contexts: list[object] = field(default_factory=list)

    @property
    def supported_action_keys(self) -> tuple[str, ...]:
        return tuple(self.action_by_key.values())

    def interpret(self, context, session: InputSessionView) -> ActionInterpretationResult:
        self.contexts.append(context)
        self.views.append(session)
        if session.trigger is not ActionInterpretationTrigger.RELEASE:
            return ActionInterpretationResult.wait()
        return ActionInterpretationResult.start(
            PreparedAction(
                action_key=self.action_by_key[session.key],
                owner=session.owner,
                requested_start_frame=session.current_frame,
                source_session_id=session.session_id,
            )
        )


def _context(*, team_size: int = 2, active_slot: int = 1) -> SimulationContext:
    context = SimulationContext()
    team_state = TeamRuntimeState(
        (
            CharacterRuntimeState(slot=slot, character_key=f"character:{slot}", level=90)
            for slot in range(1, team_size + 1)
        ),
        active_slot=active_slot,
    )
    context.space_runtime = SpaceRuntime(
        space=Space(
            [
                SpatialEntity(
                    "player:active",
                    SpatialEntityKind.ACTIVE_CHARACTER,
                    position=Vector3(),
                    active_slot=active_slot,
                )
            ]
        ),
        team_state=team_state,
    )
    return context


def _manager(
    frames: list[KeyInputFrame],
    interpreter: ReleaseStartInterpreter,
    actions: tuple[TimedImpactAction, ...],
    *,
    ability_condition_port=None,
    buff_reader=None,
) -> ActionManager:
    registry = ActionInterpreterRegistry()
    registry.register("keyboard.e", ActiveCharacterInterpreterSelector({1: interpreter}))
    registry.register("mouse.left", ActiveCharacterInterpreterSelector({1: interpreter}))
    return ActionManager(
        input_trace=InputTraceCompiler().compile(frames),
        interpreter_registry=registry,
        action_registry=ActionRegistry(actions),
        ability_condition_port=ability_condition_port,
        buff_reader=buff_reader,
    )


def _buffering_manager(
    frames: list[KeyInputFrame],
    interpreter,
    actions: tuple[TimedImpactAction, ...],
) -> ActionManager:
    """用同一解释器注册 keyboard.e 与 mouse.left 的管理器（缓冲用例共用）。"""

    registry = ActionInterpreterRegistry()
    registry.register("keyboard.e", ActiveCharacterInterpreterSelector({1: interpreter}))
    registry.register("mouse.left", ActiveCharacterInterpreterSelector({1: interpreter}))
    return ActionManager(
        input_trace=InputTraceCompiler().compile(frames),
        interpreter_registry=registry,
        action_registry=ActionRegistry(actions),
    )


def test_action_manager_starts_action_on_release_and_does_not_expose_future_release():
    interpreter = ReleaseStartInterpreter({"keyboard.e": "character.test.skill"})
    manager = _manager(
        [
            KeyInputFrame(1, (KeyEvent("keyboard.e", KeyPhase.PRESS),)),
            KeyInputFrame(3, (KeyEvent("keyboard.e", KeyPhase.RELEASE),)),
        ],
        interpreter,
        (
            TimedImpactAction(
                action_key="character.test.skill",
                duration_frames=2,
                impact_keys=("character.test.skill.hit",),
                impact_frame_offsets={"character.test.skill.hit": 1},
            ),
        ),
    )
    context = _context()

    manager.update_frame(context, 1)
    assert interpreter.views[-1].trigger is ActionInterpretationTrigger.PRESS
    assert interpreter.views[-1].release_frame is None
    assert manager.instances == ()

    manager.update_frame(context, 2)
    assert interpreter.views[-1].trigger is ActionInterpretationTrigger.HOLD
    assert interpreter.views[-1].release_frame is None

    manager.update_frame(context, 3)
    assert interpreter.views[-1].trigger is ActionInterpretationTrigger.RELEASE
    assert interpreter.views[-1].release_frame == 3
    assert manager.decisions[-1].accepted
    assert manager.instances[0].action_key == "character.test.skill"
    assert manager.instances[0].impact_points[0].scheduled_frame == 4


def test_action_manager_publishes_input_fact_and_boundary_events():
    interpreter = ReleaseStartInterpreter({"keyboard.e": "character.test.skill"})
    manager = _manager(
        [
            KeyInputFrame(1, (KeyEvent("keyboard.e", KeyPhase.PRESS),)),
            KeyInputFrame(3, (KeyEvent("keyboard.e", KeyPhase.RELEASE),)),
        ],
        interpreter,
        (TimedImpactAction(action_key="character.test.skill"),),
    )
    context = _context()

    manager.update_frame(context, 1)

    assert [event.event_type for event in context.events.frame_events] == [
        EventType.INPUT_KEY_RECEIVED,
        EventType.INPUT_SESSION_BOUNDARY_REACHED,
    ]
    assert context.events.frame_events[0].payload.to_dict() == {
        "key": "keyboard.e",
        "phase": "press",
        "order": 0,
        "session_id": 1,
    }
    assert context.events.frame_events[1].payload.to_dict() == {
        "session_id": 1,
        "key": "keyboard.e",
        "phase": "press",
        "order": 0,
        "press_frame": 1,
        "held_frames": 0,
        "physical_state": "held",
        "control_state": "listening",
        "owner_kind": "character",
        "owner_slot": 1,
        "interpreter_id": "character:1",
        "binding_scope": "active_character",
        "will_interpret": True,
        "skip_reason": None,
    }

    context.events.clear_frame_events()
    manager.update_frame(context, 2)
    context.events.clear_frame_events()
    manager.update_frame(context, 3)

    assert [event.event_type for event in context.events.frame_events] == [
        EventType.INPUT_KEY_RECEIVED,
        EventType.INPUT_SESSION_BOUNDARY_REACHED,
        EventType.ACTION_STARTED,
        EventType.INPUT_SESSION_RESOLVED,
    ]
    assert context.events.frame_events[1].payload.to_dict() == {
        "session_id": 1,
        "key": "keyboard.e",
        "phase": "release",
        "order": 0,
        "press_frame": 1,
        "held_frames": 2,
        "physical_state": "released",
        "control_state": "listening",
        "owner_kind": "character",
        "owner_slot": 1,
        "interpreter_id": "character:1",
        "binding_scope": "active_character",
        "will_interpret": True,
        "skip_reason": None,
    }
    assert context.events.frame_events[3].payload.to_dict() == {
        "session_id": 1,
        "key": "keyboard.e",
        "outcome": "consumed",
        "frame": 3,
        "buffered_at_frame": None,
        "reason": None,
        "instance_id": 1,
    }


def test_action_manager_rejects_unregistered_action():
    interpreter = ReleaseStartInterpreter({"keyboard.e": "missing.action"})
    manager = _manager(
        [
            KeyInputFrame(1, (KeyEvent("keyboard.e", KeyPhase.PRESS),)),
            KeyInputFrame(2, (KeyEvent("keyboard.e", KeyPhase.RELEASE),)),
        ],
        interpreter,
        (),
    )

    manager.update_frame(_context(), 1)
    manager.update_frame(_context(), 2)

    assert not manager.decisions[-1].accepted
    assert manager.decisions[-1].reject_reason is ActionDecisionRejectReason.UNSUPPORTED_ACTION


def test_action_manager_rejects_conflicting_named_lock():
    interpreter = ReleaseStartInterpreter(
        {
            "keyboard.e": "character.test.skill",
            "mouse.left": "character.test.attack",
        }
    )
    shared_lock = ActionAdmissionPolicy(required_locks=("character:1.control",))
    manager = _manager(
        [
            KeyInputFrame(1, (KeyEvent("keyboard.e", KeyPhase.PRESS),)),
            KeyInputFrame(2, (KeyEvent("keyboard.e", KeyPhase.RELEASE),)),
            KeyInputFrame(3, (KeyEvent("mouse.left", KeyPhase.PRESS),)),
            KeyInputFrame(4, (KeyEvent("mouse.left", KeyPhase.RELEASE),)),
        ],
        interpreter,
        (
            TimedImpactAction(
                action_key="character.test.skill",
                duration_frames=5,
                admission_policy=shared_lock,
            ),
            TimedImpactAction(
                action_key="character.test.attack",
                duration_frames=1,
                admission_policy=shared_lock,
            ),
        ),
    )
    context = _context()

    for frame in range(1, 5):
        manager.update_frame(context, frame)

    assert [decision.accepted for decision in manager.decisions] == [True, False]
    assert manager.decisions[-1].reject_reason is ActionDecisionRejectReason.LOCK_CONFLICT


def test_team_switch_is_regular_action_instance_and_updates_space_runtime():
    context = _context(team_size=2, active_slot=1)
    input_trace = InputTraceCompiler().compile(
        [
            KeyInputFrame(1, (KeyEvent("keyboard.2", KeyPhase.PRESS),)),
            KeyInputFrame(2, (KeyEvent("keyboard.2", KeyPhase.RELEASE),)),
        ]
    )
    registry = ActionInterpreterRegistry()
    registry.register("keyboard.2", TeamInterpreterSelector(TeamActionInterpreter()))
    manager = ActionManager(
        input_trace=input_trace,
        interpreter_registry=registry,
        action_registry=ActionRegistry((TeamSwitchAction(),)),
    )

    manager.update_frame(context, 1)

    assert manager.instances[0].action_key == TEAM_SWITCH_ACTION_KEY
    assert manager.instances[0].params == {TEAM_SWITCH_TARGET_SLOT_PARAM: 2}
    assert context.space_runtime is not None
    assert context.space_runtime.team_state.active_slot == 2
    player = context.space_runtime.get_entity("player:active")
    assert player is not None
    assert player.active_slot == 2
    assert manager.execution_records[0].payload["type"] == "team_switch"
    switched_events = [
        event
        for event in context.events.frame_events
        if event.event_type is EventType.TEAM_SWITCHED
    ]
    assert len(switched_events) == 1
    payload = switched_events[0].payload
    assert isinstance(payload, TeamSwitchedPayload)
    assert payload.requested_slot == 2
    assert payload.previous_slot == 1
    assert payload.active_slot == 2
    assert payload.accepted is True


def test_search_area_spec_rejects_negative_radius_or_height():
    with pytest.raises(ValueError, match="radius 必须为非负数"):
        SearchAreaSpec(shape="圆柱", radius=-1.0, height=10.0)
    with pytest.raises(ValueError, match="height 必须为非负数"):
        SearchAreaSpec(shape="圆柱", radius=15.0, height=-1.0)
    with pytest.raises(ValueError, match="shape 必须是非空字符串"):
        SearchAreaSpec(shape="", radius=15.0, height=10.0)


def test_targeting_spec_validates_search_area_and_selection_policy():
    spec = TargetingSpec(
        search_area=SearchAreaSpec(shape="圆柱", radius=15.0, height=10.0),
        selection_policy_key="分数",
    )

    assert spec.search_area is not None
    assert spec.search_area.radius == 15.0
    assert spec.search_area.height == 10.0
    assert spec.selection_policy_key == "分数"
    with pytest.raises(ValueError, match="search_area 必须是 SearchAreaSpec"):
        TargetingSpec(search_area=cast(Any, "圆柱"))
    with pytest.raises(ValueError, match="selection_policy_key"):
        TargetingSpec(selection_policy_key="")


class _RecordingAbilityConditionPort:
    def __init__(self) -> None:
        self.queries: list[object] = []

    def evaluate(self, query):
        self.queries.append(query)
        return type("Result", (), {"shared_conditions_satisfied": True})()


def test_action_manager_passes_ability_condition_port_to_interpreter():
    interpreter = ReleaseStartInterpreter({"keyboard.e": "character.test.skill"})
    port = _RecordingAbilityConditionPort()
    manager = _manager(
        [
            KeyInputFrame(1, (KeyEvent("keyboard.e", KeyPhase.PRESS),)),
            KeyInputFrame(3, (KeyEvent("keyboard.e", KeyPhase.RELEASE),)),
        ],
        interpreter,
        (TimedImpactAction(action_key="character.test.skill"),),
        ability_condition_port=port,
    )

    manager.update_frame(_context(), 1)

    assert interpreter.contexts
    interpretation_context = cast(
        ActionInterpretationContext,
        interpreter.contexts[0],
    )
    assert interpretation_context.ability_condition_port is port


class _RecordingBuffReader:
    """记录查询的最小 Buff 只读端口替身。"""

    def __init__(self) -> None:
        self.queries: list[tuple[int, object, str | None]] = []

    def active(
        self,
        frame: int,
        target_ref=None,
        definition_key: str | None = None,
        mechanic_key: str | None = None,
    ) -> tuple[object, ...]:
        self.queries.append((frame, target_ref, definition_key))
        return ()


def test_action_manager_passes_buff_reader_to_interpreter():
    """动作解释器拿到 Buff 只读端口：角色侧可自行查询并按结果决定行为参数。"""

    interpreter = ReleaseStartInterpreter({"keyboard.e": "character.test.skill"})
    reader = _RecordingBuffReader()
    manager = _manager(
        [
            KeyInputFrame(1, (KeyEvent("keyboard.e", KeyPhase.PRESS),)),
            KeyInputFrame(3, (KeyEvent("keyboard.e", KeyPhase.RELEASE),)),
        ],
        interpreter,
        (TimedImpactAction(action_key="character.test.skill"),),
        buff_reader=reader,
    )

    manager.update_frame(_context(), 1)

    assert interpreter.contexts
    interpretation_context = cast(
        ActionInterpretationContext,
        interpreter.contexts[0],
    )
    buff_reader = interpretation_context.buff_reader
    assert buff_reader is reader
    assert buff_reader is not None
    buff_reader.active(1, None, "buff.test.consumable")
    assert reader.queries == [(1, None, "buff.test.consumable")]


def test_timed_action_starts_cooldown_at_configured_frame():
    definition = CooldownDefinition(
        key=CooldownKey(
            CooldownSubjectRef.character("character:slot_1"),
            "elemental_skill",
        ),
        ability_kind=AbilityKind.ELEMENTAL_SKILL,
        base_duration_frames=100,
        max_charges=1,
        duration_mode=CooldownDurationMode.FIXED,
        source_ref="character.barbara.elemental_skill",
        tags=("elemental_skill",),
    )
    cooldown_runtime = CooldownRuntime(CooldownStore((definition,)))
    interpreter = ReleaseStartInterpreter({"keyboard.e": "character.test.skill"})
    manager = _manager(
        [
            KeyInputFrame(1, (KeyEvent("keyboard.e", KeyPhase.PRESS),)),
            KeyInputFrame(3, (KeyEvent("keyboard.e", KeyPhase.RELEASE),)),
        ],
        interpreter,
        (
            TimedImpactAction(
                action_key="character.test.skill",
                duration_frames=10,
                cooldown_start_frame=2,
                cooldown_ability_key="elemental_skill",
            ),
        ),
    )
    context = _context()
    context.register_system(cooldown_runtime)

    manager.update_frame(context, 1)
    manager.update_frame(context, 3)
    cooldown_runtime.normalize(4)
    manager.update_frame(context, 4)
    assert cooldown_runtime.store.get_record(definition.key).available_charges == 1

    cooldown_runtime.normalize(5)
    manager.update_frame(context, 5)

    record = cooldown_runtime.store.get_record(definition.key)
    assert record.available_charges == 0
    assert record.active_recovery is not None
    assert record.active_recovery.ready_frame == 105


def test_timed_action_passes_cooldown_duration_terms_to_start():
    definition = CooldownDefinition(
        key=CooldownKey(
            CooldownSubjectRef.character("character:slot_1"),
            "elemental_skill",
        ),
        ability_kind=AbilityKind.ELEMENTAL_SKILL,
        base_duration_frames=100,
        max_charges=1,
        duration_mode=CooldownDurationMode.FIXED,
        source_ref="character.barbara.elemental_skill",
        tags=("elemental_skill",),
    )
    cooldown_runtime = CooldownRuntime(CooldownStore((definition,)))
    interpreter = ReleaseStartInterpreter({"keyboard.e": "character.test.skill"})
    manager = _manager(
        [
            KeyInputFrame(1, (KeyEvent("keyboard.e", KeyPhase.PRESS),)),
            KeyInputFrame(3, (KeyEvent("keyboard.e", KeyPhase.RELEASE),)),
        ],
        interpreter,
        (
            TimedImpactAction(
                action_key="character.test.skill",
                duration_frames=10,
                cooldown_start_frame=2,
                cooldown_ability_key="elemental_skill",
                cooldown_duration_terms=(
                    CooldownDurationTerm(
                        term_key="test.cooldown_reduction",
                        source_ref="character.test",
                        stage=CooldownDurationStage.OWNER_ADJUSTMENT,
                        operation=CooldownDurationOperation.MULTIPLY_CURRENT,
                        value=Decimal("0.85"),
                    ),
                ),
            ),
        ),
    )
    context = _context()
    context.register_system(cooldown_runtime)

    manager.update_frame(context, 1)
    manager.update_frame(context, 3)
    cooldown_runtime.normalize(4)
    manager.update_frame(context, 4)
    cooldown_runtime.normalize(5)
    manager.update_frame(context, 5)

    record = cooldown_runtime.store.get_record(definition.key)
    assert record.available_charges == 0
    assert record.active_recovery is not None
    assert record.active_recovery.ready_frame == 90


def test_timed_action_merges_cooldown_duration_term_port():
    definition = CooldownDefinition(
        key=CooldownKey(
            CooldownSubjectRef.character("character:slot_1"),
            "elemental_skill",
        ),
        ability_kind=AbilityKind.ELEMENTAL_SKILL,
        base_duration_frames=100,
        max_charges=1,
        duration_mode=CooldownDurationMode.FIXED,
        source_ref="character.barbara.elemental_skill",
        tags=("elemental_skill",),
    )
    cooldown_runtime = CooldownRuntime(CooldownStore((definition,)))
    interpreter = ReleaseStartInterpreter({"keyboard.e": "character.test.skill"})
    manager = _manager(
        [
            KeyInputFrame(1, (KeyEvent("keyboard.e", KeyPhase.PRESS),)),
            KeyInputFrame(3, (KeyEvent("keyboard.e", KeyPhase.RELEASE),)),
        ],
        interpreter,
        (
            TimedImpactAction(
                action_key="character.test.skill",
                duration_frames=10,
                cooldown_start_frame=2,
                cooldown_ability_key="elemental_skill",
                cooldown_duration_term_port=_ResonanceCooldownPort(),
            ),
        ),
    )
    context = _context()
    context.register_system(cooldown_runtime)

    manager.update_frame(context, 1)
    manager.update_frame(context, 3)
    cooldown_runtime.normalize(4)
    manager.update_frame(context, 4)
    cooldown_runtime.normalize(5)
    manager.update_frame(context, 5)

    record = cooldown_runtime.store.get_record(definition.key)
    assert record.available_charges == 0
    assert record.active_recovery is not None
    assert record.active_recovery.ready_frame == 100


class _ResonanceCooldownPort:
    def terms_for(self, key):
        del key
        return (
            CooldownDurationTerm(
                term_key="resonance.cooldown",
                source_ref="resonance",
                stage=CooldownDurationStage.OWNER_ADJUSTMENT,
                operation=CooldownDurationOperation.MULTIPLY_CURRENT,
                value=Decimal("0.95"),
            ),
        )


# ---------------------------------------------------------------------------
# 输入缓冲（预输入）用例：defer 判定、缓冲重评、FIFO、锁挂起与可观测性。
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class BufferingInterpreter:
    """到最早帧前 ``defer``、之后 ``start`` 的合成解释器。"""

    action_by_key: dict[str, str]
    earliest_by_key: dict[str, int]
    views: list[InputSessionView] = field(default_factory=list)

    @property
    def supported_action_keys(self) -> tuple[str, ...]:
        return tuple(self.action_by_key.values())

    def interpret(self, context, session: InputSessionView) -> ActionInterpretationResult:
        del context
        self.views.append(session)
        if session.trigger is not ActionInterpretationTrigger.RELEASE:
            return ActionInterpretationResult.wait()
        earliest = self.earliest_by_key[session.key]
        if session.current_frame < earliest:
            return ActionInterpretationResult.defer(f"最早第 {earliest} 帧衔接")
        return ActionInterpretationResult.start(
            PreparedAction(
                action_key=self.action_by_key[session.key],
                owner=session.owner,
                requested_start_frame=session.current_frame,
                source_session_id=session.session_id,
            )
        )


@dataclass(slots=True)
class PressStartInterpreter:
    """PRESS 即起手的合成解释器（用于管理器锁挂起用例）。"""

    action_by_key: dict[str, str]

    @property
    def supported_action_keys(self) -> tuple[str, ...]:
        return tuple(self.action_by_key.values())

    def interpret(self, context, session: InputSessionView) -> ActionInterpretationResult:
        del context
        if session.trigger is not ActionInterpretationTrigger.PRESS:
            return ActionInterpretationResult.wait()
        return ActionInterpretationResult.start(
            PreparedAction(
                action_key=self.action_by_key[session.key],
                owner=session.owner,
                requested_start_frame=session.current_frame,
                source_session_id=session.session_id,
            )
        )


@dataclass(slots=True)
class RejectingInterpreter:
    """RELEASE 一律终局拒绝的合成解释器（冷却/缺少衔接数据等硬拒绝）。"""

    reason: str
    supported_action_keys: tuple[str, ...] = ()

    def interpret(self, context, session: InputSessionView) -> ActionInterpretationResult:
        del context
        if session.trigger is not ActionInterpretationTrigger.RELEASE:
            return ActionInterpretationResult.wait()
        return ActionInterpretationResult.reject(self.reason)


def test_deferred_session_starts_action_at_earliest_frame():
    interpreter = BufferingInterpreter(
        {"keyboard.e": "character.test.skill"},
        {"keyboard.e": 6},
    )
    manager = _buffering_manager(
        [
            KeyInputFrame(1, (KeyEvent("keyboard.e", KeyPhase.PRESS),)),
            KeyInputFrame(2, (KeyEvent("keyboard.e", KeyPhase.RELEASE),)),
        ],
        interpreter,
        (TimedImpactAction(action_key="character.test.skill", duration_frames=3),),
    )
    context = _context()
    started: list[int] = []
    deferred_events: list[tuple[int, str]] = []
    resolved_events: list[dict] = []
    context.events.subscribe(EventType.ACTION_STARTED, lambda event: started.append(event.frame))
    context.events.subscribe(
        EventType.INPUT_SESSION_DEFERRED,
        lambda event: deferred_events.append(
            (event.frame, cast(InputSessionDeferredPayload, event.payload).reason)
        ),
    )
    context.events.subscribe(
        EventType.INPUT_SESSION_RESOLVED,
        lambda event: resolved_events.append(
            cast(InputSessionResolvedPayload, event.payload).to_dict()
        ),
    )

    for frame in range(1, 6):
        manager.update_frame(context, frame)

    assert manager.deferred_session_ids == (1,)
    assert manager.sessions[0].control_state is InputControlState.LISTENING
    assert manager.instances == ()
    assert started == []
    assert deferred_events == [(2, "最早第 6 帧衔接")]
    assert resolved_events == []

    manager.update_frame(context, 6)

    assert manager.deferred_session_ids == ()
    assert started == [6]
    assert manager.instances[0].action_key == "character.test.skill"
    assert manager.instances[0].start_frame == 6
    assert resolved_events == [
        {
            "session_id": 1,
            "key": "keyboard.e",
            "outcome": "consumed",
            "frame": 6,
            "buffered_at_frame": 2,
            "reason": None,
            "instance_id": 1,
        }
    ]


def test_deferred_sessions_resolve_in_session_id_order():
    interpreter = BufferingInterpreter(
        {"keyboard.e": "character.test.skill", "mouse.left": "character.test.attack"},
        {"keyboard.e": 4, "mouse.left": 5},
    )
    manager = _buffering_manager(
        [
            KeyInputFrame(
                1,
                (
                    KeyEvent("keyboard.e", KeyPhase.PRESS),
                    KeyEvent("mouse.left", KeyPhase.PRESS),
                ),
            ),
            KeyInputFrame(
                2,
                (
                    KeyEvent("keyboard.e", KeyPhase.RELEASE),
                    KeyEvent("mouse.left", KeyPhase.RELEASE),
                ),
            ),
        ],
        interpreter,
        (
            TimedImpactAction(action_key="character.test.skill", duration_frames=2),
            TimedImpactAction(action_key="character.test.attack", duration_frames=2),
        ),
    )
    context = _context()
    started: list[int] = []
    context.events.subscribe(EventType.ACTION_STARTED, lambda event: started.append(event.frame))

    for frame in range(1, 6):
        manager.update_frame(context, frame)

    assert started == [4, 5]
    assert [instance.action_key for instance in manager.instances] == [
        "character.test.skill",
        "character.test.attack",
    ]
    assert manager.deferred_session_ids == ()


def test_deferred_review_freezes_held_frames_to_physical_release():
    interpreter = BufferingInterpreter(
        {"keyboard.e": "character.test.skill"},
        {"keyboard.e": 10},
    )
    manager = _buffering_manager(
        [
            KeyInputFrame(1, (KeyEvent("keyboard.e", KeyPhase.PRESS),)),
            KeyInputFrame(3, (KeyEvent("keyboard.e", KeyPhase.RELEASE),)),
        ],
        interpreter,
        (TimedImpactAction(action_key="character.test.skill", duration_frames=2),),
    )
    context = _context()

    for frame in range(1, 11):
        manager.update_frame(context, frame)

    review = interpreter.views[-1]
    assert review.trigger is ActionInterpretationTrigger.RELEASE
    assert review.current_frame == 10
    # held_frames 冻结为物理事实（3 - 1 = 2），不随重评帧膨胀。
    assert review.held_frames == 2
    assert review.release_frame == 3


@pytest.mark.parametrize(
    "reason",
    [
        "阿罗夏动作缺少 character.alyosha.normal_attack.1 -> jump 的衔接数据",
        "阿罗夏元素战技冷却未就绪",
    ],
)
def test_rejected_session_is_not_buffered_and_records_terminal_reason(reason: str):
    interpreter = RejectingInterpreter(reason)
    manager = _buffering_manager(
        [
            KeyInputFrame(1, (KeyEvent("keyboard.e", KeyPhase.PRESS),)),
            KeyInputFrame(2, (KeyEvent("keyboard.e", KeyPhase.RELEASE),)),
        ],
        interpreter,
        (TimedImpactAction(action_key="character.test.skill"),),
    )
    context = _context()
    resolved: list[dict] = []
    context.events.subscribe(
        EventType.INPUT_SESSION_RESOLVED,
        lambda event: resolved.append(event.payload.to_dict()),
    )

    manager.update_frame(context, 1)
    manager.update_frame(context, 2)

    assert manager.deferred_session_ids == ()
    session = manager.sessions[0]
    assert session.control_state is InputControlState.DETACHED
    assert session.terminal_reason == reason
    assert resolved == [
        {
            "session_id": 1,
            "key": "keyboard.e",
            "outcome": "rejected",
            "frame": 2,
            "buffered_at_frame": None,
            "reason": reason,
            "instance_id": None,
        }
    ]


def test_deferred_session_release_boundary_is_not_reinterpreted():
    lock_policy = ActionAdmissionPolicy(
        required_locks=("character:1.control",),
        interrupt_policy=ActionInterruptPolicy(cancel_policy="queue_new"),
    )
    interpreter = PressStartInterpreter(
        {"keyboard.e": "character.test.locked", "mouse.left": "character.test.locked"}
    )
    manager = _buffering_manager(
        [
            KeyInputFrame(
                1,
                (
                    KeyEvent("keyboard.e", KeyPhase.PRESS),
                    KeyEvent("mouse.left", KeyPhase.PRESS),
                ),
            ),
            KeyInputFrame(
                3,
                (
                    KeyEvent("keyboard.e", KeyPhase.RELEASE),
                    KeyEvent("mouse.left", KeyPhase.RELEASE),
                ),
            ),
        ],
        interpreter,
        (
            TimedImpactAction(
                action_key="character.test.locked",
                duration_frames=10,
                admission_policy=lock_policy,
            ),
        ),
    )
    context = _context()

    manager.update_frame(context, 1)
    assert manager.deferred_session_ids == (2,)

    context.events.clear_frame_events()
    manager.update_frame(context, 3)

    boundaries = [
        cast(InputSessionBoundaryPayload, event.payload)
        for event in context.events.frame_events
        if event.event_type is EventType.INPUT_SESSION_BOUNDARY_REACHED
        and cast(InputSessionBoundaryPayload, event.payload).session_id == 2
    ]
    assert len(boundaries) == 1
    assert boundaries[0].will_interpret is False
    assert boundaries[0].skip_reason == "deferred"
    assert manager.deferred_session_ids == (2,)


def test_canceling_owner_clears_deferred_session():
    interpreter = BufferingInterpreter(
        {"keyboard.e": "character.test.skill"},
        {"keyboard.e": 50},
    )
    manager = _buffering_manager(
        [
            KeyInputFrame(1, (KeyEvent("keyboard.e", KeyPhase.PRESS),)),
            KeyInputFrame(2, (KeyEvent("keyboard.e", KeyPhase.RELEASE),)),
        ],
        interpreter,
        (TimedImpactAction(action_key="character.test.skill"),),
    )
    context = _context()
    resolved: list[dict] = []
    context.events.subscribe(
        EventType.INPUT_SESSION_RESOLVED,
        lambda event: resolved.append(event.payload.to_dict()),
    )

    manager.update_frame(context, 1)
    manager.update_frame(context, 2)
    assert manager.deferred_session_ids == (1,)

    manager.cancel_sessions_for_owner(
        ActionOwnerRef.character(1),
        reason="character_switch",
        context=context,
        frame=3,
    )

    assert manager.deferred_session_ids == ()
    assert manager.sessions[0].control_state is InputControlState.CANCELED
    assert resolved == [
        {
            "session_id": 1,
            "key": "keyboard.e",
            "outcome": "canceled",
            "frame": 3,
            "buffered_at_frame": 2,
            "reason": "character_switch",
            "instance_id": None,
        }
    ]


def test_team_switch_second_press_queues_until_first_completes():
    context = _context(team_size=3, active_slot=1)
    input_trace = InputTraceCompiler().compile(
        [
            KeyInputFrame(
                1,
                (
                    KeyEvent("keyboard.2", KeyPhase.PRESS),
                    KeyEvent("keyboard.3", KeyPhase.PRESS),
                ),
            ),
            KeyInputFrame(
                3,
                (
                    KeyEvent("keyboard.2", KeyPhase.RELEASE),
                    KeyEvent("keyboard.3", KeyPhase.RELEASE),
                ),
            ),
        ]
    )
    registry = ActionInterpreterRegistry()
    registry.register("keyboard.2", TeamInterpreterSelector(TeamActionInterpreter()))
    registry.register("keyboard.3", TeamInterpreterSelector(TeamActionInterpreter()))
    manager = ActionManager(
        input_trace=input_trace,
        interpreter_registry=registry,
        action_registry=ActionRegistry((TeamSwitchAction(),)),
    )
    started: list[int] = []
    context.events.subscribe(EventType.ACTION_STARTED, lambda event: started.append(event.frame))

    for frame in range(1, 5):
        manager.update_frame(context, frame)

    assert started == [1, 3]
    assert [instance.params[TEAM_SWITCH_TARGET_SLOT_PARAM] for instance in manager.instances] == [
        2,
        3,
    ]
    assert manager.deferred_session_ids == ()


def test_manager_is_not_idle_while_session_deferred():
    interpreter = BufferingInterpreter(
        {"keyboard.e": "character.test.skill"},
        {"keyboard.e": 6},
    )
    manager = _buffering_manager(
        [
            KeyInputFrame(1, (KeyEvent("keyboard.e", KeyPhase.PRESS),)),
            KeyInputFrame(2, (KeyEvent("keyboard.e", KeyPhase.RELEASE),)),
        ],
        interpreter,
        (TimedImpactAction(action_key="character.test.skill", duration_frames=2),),
    )
    context = _context()

    for frame in range(1, 6):
        manager.update_frame(context, frame)
    assert manager.is_idle() is False

    for frame in range(6, 12):
        manager.update_frame(context, frame)
    assert manager.is_idle() is True


def test_buffering_is_reproducible_for_same_input():
    def run() -> tuple[list[int], list[str]]:
        interpreter = BufferingInterpreter(
            {"keyboard.e": "character.test.skill", "mouse.left": "character.test.attack"},
            {"keyboard.e": 4, "mouse.left": 5},
        )
        manager = _buffering_manager(
            [
                KeyInputFrame(
                    1,
                    (
                        KeyEvent("keyboard.e", KeyPhase.PRESS),
                        KeyEvent("mouse.left", KeyPhase.PRESS),
                    ),
                ),
                KeyInputFrame(
                    2,
                    (
                        KeyEvent("keyboard.e", KeyPhase.RELEASE),
                        KeyEvent("mouse.left", KeyPhase.RELEASE),
                    ),
                ),
            ],
            interpreter,
            (
                TimedImpactAction(action_key="character.test.skill", duration_frames=2),
                TimedImpactAction(action_key="character.test.attack", duration_frames=2),
            ),
        )
        context = _context()
        started: list[int] = []
        outcomes: list[str] = []
        context.events.subscribe(
            EventType.ACTION_STARTED, lambda event: started.append(event.frame)
        )
        context.events.subscribe(
            EventType.INPUT_SESSION_RESOLVED,
            lambda event: outcomes.append(cast(InputSessionResolvedPayload, event.payload).outcome),
        )
        for frame in range(1, 8):
            manager.update_frame(context, frame)
        return started, outcomes

    assert run() == run()
