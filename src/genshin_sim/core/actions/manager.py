from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from genshin_sim.core.events import (
    EventType,
    GameEvent,
    InputKeyReceivedPayload,
    InputSessionBoundaryPayload,
)
from genshin_sim.core.protocols import FrameUpdatable
from genshin_sim.core.simulation.input import InputSessionBoundary, InputSessionTrace, KeyPhase
from genshin_sim.core.space.geometry import Vector3

if TYPE_CHECKING:
    from genshin_sim.core.simulation import SimulationContext


TEAM_SWITCH_ACTION_KEY = "team.switch"
TEAM_SWITCH_TARGET_SLOT_PARAM = "target_slot"


class ActionOwnerKind(StrEnum):
    TEAM = "team"
    CHARACTER = "character"


@dataclass(frozen=True, slots=True)
class ActionOwnerRef:
    """动作或输入解释器的运行时归属。"""

    kind: ActionOwnerKind
    slot: int | None = None

    @classmethod
    def team(cls) -> ActionOwnerRef:
        return cls(ActionOwnerKind.TEAM)

    @classmethod
    def character(cls, slot: int) -> ActionOwnerRef:
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            msg = "角色动作 owner.slot 必须是正整数"
            raise ValueError(msg)
        return cls(ActionOwnerKind.CHARACTER, slot=slot)

    @property
    def lock_prefix(self) -> str:
        if self.kind is ActionOwnerKind.TEAM:
            return "team"
        return f"character:{self.slot}"


class InputPhysicalState(StrEnum):
    HELD = "held"
    RELEASED = "released"


class InputControlState(StrEnum):
    LISTENING = "listening"
    DETACHED = "detached"
    CANCELED = "canceled"


class ActionInterpretationTrigger(StrEnum):
    PRESS = "press"
    HOLD = "hold"
    RELEASE = "release"
    CANCEL = "cancel"


class ActionInterpretationKind(StrEnum):
    WAIT = "wait"
    REJECT = "reject"
    START_ACTION = "start_action"
    CONTROL_ACTION = "control_action"


class InputSessionPolicy(StrEnum):
    KEEP_LISTENING = "keep_listening"
    DETACH = "detach"
    CANCEL = "cancel"


class ActionLifecycle(StrEnum):
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELED = "canceled"


class ActionLifecycleDirective(StrEnum):
    CONTINUE = "continue"
    FINISH = "finish"
    CANCEL = "cancel"


class ActionDecisionRejectReason(StrEnum):
    INVALID_START_FRAME = "invalid_start_frame"
    INVALID_OWNER = "invalid_owner"
    SESSION_NOT_ACTIVE = "session_not_active"
    SESSION_ALREADY_BOUND = "session_already_bound"
    LOCK_CONFLICT = "lock_conflict"
    INTERRUPT_NOT_ALLOWED = "interrupt_not_allowed"
    INSTANCE_NOT_FOUND = "instance_not_found"
    INVALID_COMMAND = "invalid_command"
    UNSUPPORTED_ACTION = "unsupported_action"


class SnapshotPolicy(StrEnum):
    RESOLVE_ON_IMPACT = "resolve_on_impact"
    SNAPSHOT_ON_EMIT = "snapshot_on_emit"


@dataclass(frozen=True, slots=True)
class TargetingSpec:
    """动作影响点的目标解析规格。"""

    origin: Vector3 = field(default_factory=Vector3)
    radius: float = 0.0
    kinds: tuple[str, ...] = ("target",)
    exclude_entity_ids: tuple[str, ...] = ()
    snapshot_policy: SnapshotPolicy = SnapshotPolicy.RESOLVE_ON_IMPACT
    snapshot_entity_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.radius < 0:
            msg = "目标查询半径必须为非负数"
            raise ValueError(msg)
        object.__setattr__(self, "kinds", tuple(self.kinds))
        object.__setattr__(self, "exclude_entity_ids", tuple(self.exclude_entity_ids))
        object.__setattr__(self, "snapshot_entity_ids", tuple(self.snapshot_entity_ids))


@dataclass(frozen=True, slots=True)
class CandidateTargetRef:
    """影响点到期时从空间实体解析出的候选目标引用。"""

    spatial_entity_id: str
    target_id: str


@dataclass(frozen=True, slots=True)
class ActionImpactPoint:
    """动作运行过程中产生的机制影响点。"""

    impact_point_id: str
    source_instance_id: int
    owner: ActionOwnerRef
    action_key: str
    impact_key: str
    scheduled_frame: int
    targeting: TargetingSpec | None = None
    params: Mapping[str, object] = field(default_factory=dict)
    cancel_with_action: bool = True
    status: str = "pending"

    def __post_init__(self) -> None:
        if self.source_instance_id <= 0:
            msg = "source_instance_id 必须是正整数"
            raise ValueError(msg)
        if not self.impact_point_id.strip():
            msg = "impact_point_id 必须是非空字符串"
            raise ValueError(msg)
        if not self.action_key.strip():
            msg = "action_key 必须是非空字符串"
            raise ValueError(msg)
        if not self.impact_key.strip():
            msg = "impact_key 必须是非空字符串"
            raise ValueError(msg)
        if self.scheduled_frame < 0:
            msg = "scheduled_frame 不能为负数"
            raise ValueError(msg)
        object.__setattr__(self, "params", dict(self.params))


@dataclass(frozen=True, slots=True)
class PreparedAction:
    """解释器提交给 ActionManager 的动作启动请求。"""

    action_key: str
    owner: ActionOwnerRef
    requested_start_frame: int
    params: Mapping[str, object] = field(default_factory=dict)
    source_session_id: int | None = None
    bind_session_on_accept: bool = False
    continue_on_reject: bool = False
    interrupt_kind: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.action_key.strip():
            msg = "prepared action_key 必须是非空字符串"
            raise ValueError(msg)
        if self.requested_start_frame < 0:
            msg = "requested_start_frame 不能为负数"
            raise ValueError(msg)
        object.__setattr__(self, "params", dict(self.params))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True, slots=True)
class ControlActionRequest:
    """解释器发给既有动作实例的语义化控制命令。"""

    target_instance_id: int
    command: str
    params: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.target_instance_id <= 0:
            msg = "target_instance_id 必须是正整数"
            raise ValueError(msg)
        if not self.command.strip():
            msg = "控制命令必须是非空字符串"
            raise ValueError(msg)
        object.__setattr__(self, "params", dict(self.params))


@dataclass(frozen=True, slots=True)
class ActionInterpretationResult:
    """动作解释器返回给 ActionManager 的结构化结果。"""

    kind: ActionInterpretationKind
    prepared_action: PreparedAction | None = None
    control_request: ControlActionRequest | None = None
    session_policy: InputSessionPolicy = InputSessionPolicy.KEEP_LISTENING
    reason: str | None = None

    @classmethod
    def wait(cls) -> ActionInterpretationResult:
        return cls(ActionInterpretationKind.WAIT)

    @classmethod
    def reject(
        cls,
        reason: str,
        *,
        session_policy: InputSessionPolicy = InputSessionPolicy.DETACH,
    ) -> ActionInterpretationResult:
        return cls(
            ActionInterpretationKind.REJECT,
            session_policy=session_policy,
            reason=reason,
        )

    @classmethod
    def start(
        cls,
        prepared_action: PreparedAction,
        *,
        session_policy: InputSessionPolicy = InputSessionPolicy.DETACH,
    ) -> ActionInterpretationResult:
        return cls(
            ActionInterpretationKind.START_ACTION,
            prepared_action=prepared_action,
            session_policy=session_policy,
        )

    @classmethod
    def control(
        cls,
        control_request: ControlActionRequest,
        *,
        session_policy: InputSessionPolicy = InputSessionPolicy.KEEP_LISTENING,
    ) -> ActionInterpretationResult:
        return cls(
            ActionInterpretationKind.CONTROL_ACTION,
            control_request=control_request,
            session_policy=session_policy,
        )


@dataclass(frozen=True, slots=True)
class InterpreterBinding:
    """某个输入会话固定绑定的解释器。"""

    interpreter_id: str
    interpreter: ActionInterpreter
    owner: ActionOwnerRef
    scope: str


@dataclass(frozen=True, slots=True)
class InputSessionView:
    """解释器可见的当前帧输入会话视图。"""

    session_id: int
    key: str
    trigger: ActionInterpretationTrigger
    press_frame: int
    current_frame: int
    held_frames: int
    physical_state: InputPhysicalState
    owner: ActionOwnerRef
    bound_instance: ActionInstance | None = None
    release_frame: int | None = None


@dataclass(slots=True)
class RuntimeInputSession:
    """ActionManager 内部持有的输入会话运行态。"""

    session_id: int
    key: str
    press_frame: int
    physical_state: InputPhysicalState
    control_state: InputControlState
    interpreter_binding: InterpreterBinding
    owner: ActionOwnerRef
    bound_instance_id: int | None = None
    cancel_reason: str | None = None
    released_frame: int | None = None


@runtime_checkable
class ActionInterpreter(Protocol):
    @property
    def supported_action_keys(self) -> Sequence[str]:
        """该解释器可能请求的动作 key。"""
        ...

    def interpret(
        self,
        context: SimulationContext,
        session: InputSessionView,
    ) -> ActionInterpretationResult:
        """解释当前输入会话视图。"""
        ...


class InterpreterSelector(Protocol):
    def resolve(self, context: SimulationContext, key: str) -> InterpreterBinding:
        """为按键输入解析解释器绑定。"""
        ...


class TeamInterpreterSelector:
    """固定返回队伍级解释器。"""

    def __init__(self, interpreter: ActionInterpreter) -> None:
        self.interpreter = interpreter

    def resolve(self, context: SimulationContext, key: str) -> InterpreterBinding:
        del context, key
        return InterpreterBinding(
            interpreter_id="team",
            interpreter=self.interpreter,
            owner=ActionOwnerRef.team(),
            scope="team",
        )


class ActiveCharacterInterpreterSelector:
    """根据 PRESS 时的当前场上槽位绑定角色解释器。"""

    def __init__(self, interpreters: Mapping[int, ActionInterpreter]) -> None:
        self._interpreters = dict(interpreters)

    def resolve(self, context: SimulationContext, key: str) -> InterpreterBinding:
        del key
        if context.space_runtime is None:
            msg = "缺少 SpaceRuntime，无法解析当前场上角色解释器"
            raise LookupError(msg)
        slot = context.space_runtime.team_state.active_slot
        try:
            interpreter = self._interpreters[slot]
        except KeyError as exc:
            msg = f"队伍槽位 {slot} 缺少角色动作解释器"
            raise LookupError(msg) from exc
        return InterpreterBinding(
            interpreter_id=f"character:{slot}",
            interpreter=interpreter,
            owner=ActionOwnerRef.character(slot),
            scope="active_character",
        )


class ActionInterpreterRegistry:
    """按输入键解析队伍级或角色级解释器。"""

    def __init__(self) -> None:
        self._selectors: dict[str, InterpreterSelector] = {}

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(self._selectors)

    def register(self, key: str, selector: InterpreterSelector) -> None:
        _validate_non_empty_text(key, "输入键")
        if key in self._selectors:
            msg = f"输入键重复注册解释器：{key}"
            raise ValueError(msg)
        self._selectors[key] = selector

    def resolve(self, key: str, context: SimulationContext) -> InterpreterBinding:
        try:
            selector = self._selectors[key]
        except KeyError as exc:
            msg = f"输入键缺少解释器 selector：{key}"
            raise LookupError(msg) from exc
        return selector.resolve(context, key)


@dataclass(frozen=True, slots=True)
class ActionInterruptPolicy:
    allowed_interrupt_kinds: tuple[str, ...] = ()
    active_from_frame: int = 0
    active_until_frame: int | None = None
    cancel_policy: str = "reject_new"

    def allows(self, interrupt_kind: str | None, elapsed_frames: int) -> bool:
        if interrupt_kind is None or interrupt_kind not in self.allowed_interrupt_kinds:
            return False
        if elapsed_frames < self.active_from_frame:
            return False
        return self.active_until_frame is None or elapsed_frames <= self.active_until_frame


@dataclass(frozen=True, slots=True)
class ActionAdmissionPolicy:
    action_tags: tuple[str, ...] = ()
    required_locks: tuple[str, ...] = ()
    interrupt_policy: ActionInterruptPolicy = field(default_factory=ActionInterruptPolicy)
    concurrency_policy: str = "exclusive"

    def __post_init__(self) -> None:
        object.__setattr__(self, "action_tags", tuple(self.action_tags))
        object.__setattr__(self, "required_locks", tuple(self.required_locks))


@dataclass(frozen=True, slots=True)
class ActionExecutionContext:
    frame: int
    instance_id: int
    owner: ActionOwnerRef
    source_session_id: int | None
    start_frame: int
    elapsed_frames: int
    action_state: Mapping[str, object]
    simulation_context: SimulationContext
    params: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ActionExecutionResult:
    next_state: Mapping[str, object] | None = None
    emitted_impacts: tuple[ActionImpactPoint, ...] = ()
    lifecycle_directive: ActionLifecycleDirective = ActionLifecycleDirective.CONTINUE
    records: tuple[Mapping[str, object], ...] = ()
    cancel_reason: str | None = None

    def __post_init__(self) -> None:
        if self.next_state is not None:
            object.__setattr__(self, "next_state", dict(self.next_state))
        object.__setattr__(self, "emitted_impacts", tuple(self.emitted_impacts))
        object.__setattr__(self, "records", tuple(dict(record) for record in self.records))


@runtime_checkable
class Action(Protocol):
    @property
    def action_key(self) -> str:
        """动作实现身份。"""
        ...

    @property
    def admission_policy(self) -> ActionAdmissionPolicy:
        """动作准入策略。"""
        ...

    def create_initial_state(self, params: Mapping[str, object]) -> Mapping[str, object]:
        """为一次动作实例创建初始可变状态。"""
        ...

    def on_start(self, context: ActionExecutionContext) -> ActionExecutionResult:
        """动作开始。"""
        ...

    def on_update(self, context: ActionExecutionContext) -> ActionExecutionResult:
        """逐帧推进动作。"""
        ...

    def on_command(
        self,
        context: ActionExecutionContext,
        command: ControlActionRequest,
    ) -> ActionExecutionResult:
        """处理语义化控制命令。"""
        ...

    def on_cancel(self, context: ActionExecutionContext, reason: str) -> ActionExecutionResult:
        """动作被取消。"""
        ...

    def on_finish(self, context: ActionExecutionContext) -> ActionExecutionResult:
        """动作完成。"""
        ...


class ActionRegistry:
    """组装阶段注册的不可变 Action 定义。"""

    def __init__(self, actions: Iterable[Action] = ()) -> None:
        self._actions: dict[str, Action] = {}
        for action in actions:
            self.register(action)

    @property
    def action_keys(self) -> tuple[str, ...]:
        return tuple(self._actions)

    def register(self, action: Action) -> None:
        _validate_non_empty_text(action.action_key, "action_key")
        if action.action_key in self._actions:
            msg = f"重复 action_key：{action.action_key}"
            raise ValueError(msg)
        self._actions[action.action_key] = action

    def get(self, action_key: str) -> Action:
        try:
            return self._actions[action_key]
        except KeyError as exc:
            msg = f"未注册 action：{action_key}"
            raise KeyError(msg) from exc

    def contains(self, action_key: str) -> bool:
        return action_key in self._actions


@dataclass(slots=True)
class ActionInstance:
    """已接受动作的一次运行身份。"""

    instance_id: int
    action: Action
    action_key: str
    owner: ActionOwnerRef
    source_session_id: int | None
    created_frame: int
    start_frame: int
    lifecycle: ActionLifecycle
    action_state: Mapping[str, object]
    params: Mapping[str, object]
    pending_commands: list[ControlActionRequest] = field(default_factory=list)
    impact_points: list[ActionImpactPoint] = field(default_factory=list)
    completed_frame: int | None = None
    cancel_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ActionDecision:
    request_id: int
    source_session_id: int | None
    accepted: bool
    frame: int
    action_key: str
    reject_reason: ActionDecisionRejectReason | None = None
    created_instance_id: int | None = None
    interrupted_instance_ids: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class ActionExecutionRecord:
    frame: int
    instance_id: int
    action_key: str
    payload: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", dict(self.payload))


@dataclass(frozen=True, slots=True)
class TimedImpactAction:
    """用于测试内容和已确认帧表的通用定时动作。"""

    action_key: str
    duration_frames: int = 1
    impact_keys: tuple[str, ...] = ()
    impact_frame_offsets: Mapping[str, int] = field(default_factory=dict)
    create_default_impact_point: bool = False
    targeting: TargetingSpec | None = None
    admission_policy: ActionAdmissionPolicy = field(default_factory=ActionAdmissionPolicy)

    def __post_init__(self) -> None:
        _validate_non_empty_text(self.action_key, "action_key")
        if self.duration_frames <= 0:
            msg = "duration_frames 必须是正整数"
            raise ValueError(msg)
        object.__setattr__(self, "impact_keys", tuple(self.impact_keys))
        object.__setattr__(self, "impact_frame_offsets", dict(self.impact_frame_offsets))

    def create_initial_state(self, params: Mapping[str, object]) -> Mapping[str, object]:
        return {"params": dict(params)}

    def on_start(self, context: ActionExecutionContext) -> ActionExecutionResult:
        impact_keys = self.impact_keys
        if not impact_keys and self.create_default_impact_point:
            impact_keys = (self.action_key,)
        impacts = tuple(
            ActionImpactPoint(
                impact_point_id=f"action:{context.instance_id}:{impact_key}",
                source_instance_id=context.instance_id,
                owner=context.owner,
                action_key=self.action_key,
                impact_key=impact_key,
                scheduled_frame=context.start_frame + self.impact_frame_offsets.get(impact_key, 0),
                targeting=self.targeting,
                params=context.params,
            )
            for impact_key in impact_keys
        )
        return ActionExecutionResult(emitted_impacts=impacts)

    def on_update(self, context: ActionExecutionContext) -> ActionExecutionResult:
        if context.elapsed_frames >= self.duration_frames:
            return ActionExecutionResult(lifecycle_directive=ActionLifecycleDirective.FINISH)
        return ActionExecutionResult()

    def on_command(
        self,
        context: ActionExecutionContext,
        command: ControlActionRequest,
    ) -> ActionExecutionResult:
        del context
        if command.command == "finish":
            return ActionExecutionResult(lifecycle_directive=ActionLifecycleDirective.FINISH)
        if command.command == "cancel":
            return ActionExecutionResult(
                lifecycle_directive=ActionLifecycleDirective.CANCEL,
                cancel_reason="command_cancel",
            )
        return ActionExecutionResult()

    def on_cancel(self, context: ActionExecutionContext, reason: str) -> ActionExecutionResult:
        del context
        return ActionExecutionResult(records=({"type": "action_canceled", "reason": reason},))

    def on_finish(self, context: ActionExecutionContext) -> ActionExecutionResult:
        del context
        return ActionExecutionResult()


@dataclass(frozen=True, slots=True)
class TeamSwitchAction:
    """队伍切人动作实现。"""

    action_key: str = TEAM_SWITCH_ACTION_KEY
    duration_frames: int = 1
    admission_policy: ActionAdmissionPolicy = field(
        default_factory=lambda: ActionAdmissionPolicy(required_locks=("team.control",))
    )

    def create_initial_state(self, params: Mapping[str, object]) -> Mapping[str, object]:
        target_slot = params.get(TEAM_SWITCH_TARGET_SLOT_PARAM)
        if isinstance(target_slot, bool) or not isinstance(target_slot, int):
            msg = f"{TEAM_SWITCH_ACTION_KEY}.params.{TEAM_SWITCH_TARGET_SLOT_PARAM} 必须是整数"
            raise ValueError(msg)
        return {TEAM_SWITCH_TARGET_SLOT_PARAM: target_slot}

    def on_start(self, context: ActionExecutionContext) -> ActionExecutionResult:
        if context.simulation_context.space_runtime is None:
            return ActionExecutionResult(
                lifecycle_directive=ActionLifecycleDirective.CANCEL,
                cancel_reason="missing_space_runtime",
            )
        space_runtime = context.simulation_context.space_runtime
        target_slot = context.action_state[TEAM_SWITCH_TARGET_SLOT_PARAM]
        if not isinstance(target_slot, int):
            msg = f"{TEAM_SWITCH_ACTION_KEY}.state.{TEAM_SWITCH_TARGET_SLOT_PARAM} 必须是整数"
            raise ValueError(msg)
        result = space_runtime.team_state.switch_to(target_slot, context.frame)
        if result.accepted and space_runtime.get_entity("player:active") is not None:
            space_runtime.update_active_character_slot(result.active_slot)
        return ActionExecutionResult(
            records=(
                {
                    "type": "team_switch",
                    "status": result.status.value,
                    "accepted": result.accepted,
                    "requested_slot": result.requested_slot,
                    "previous_slot": result.previous_slot,
                    "active_slot": result.active_slot,
                },
            )
        )

    def on_update(self, context: ActionExecutionContext) -> ActionExecutionResult:
        if context.elapsed_frames >= self.duration_frames:
            return ActionExecutionResult(lifecycle_directive=ActionLifecycleDirective.FINISH)
        return ActionExecutionResult()

    def on_command(
        self,
        context: ActionExecutionContext,
        command: ControlActionRequest,
    ) -> ActionExecutionResult:
        del context, command
        return ActionExecutionResult()

    def on_cancel(self, context: ActionExecutionContext, reason: str) -> ActionExecutionResult:
        del context
        return ActionExecutionResult(records=({"type": "team_switch_canceled", "reason": reason},))

    def on_finish(self, context: ActionExecutionContext) -> ActionExecutionResult:
        del context
        return ActionExecutionResult()


class TeamActionInterpreter:
    """队伍级数字键解释器。"""

    supported_action_keys = (TEAM_SWITCH_ACTION_KEY,)

    def interpret(
        self,
        context: SimulationContext,
        session: InputSessionView,
    ) -> ActionInterpretationResult:
        del context
        if session.trigger is not ActionInterpretationTrigger.PRESS:
            return ActionInterpretationResult.wait()
        target_slot = _switch_slot_from_key(session.key)
        if target_slot is None:
            return ActionInterpretationResult.reject(f"队伍解释器不支持输入：{session.key}")
        return ActionInterpretationResult.start(
            PreparedAction(
                action_key=TEAM_SWITCH_ACTION_KEY,
                owner=ActionOwnerRef.team(),
                requested_start_frame=session.current_frame,
                params={TEAM_SWITCH_TARGET_SLOT_PARAM: target_slot},
                source_session_id=session.session_id,
            )
        )


class ActionManager(FrameUpdatable):
    """输入会话解释、动作准入、动作实例和影响点的统一运行时入口。"""

    def __init__(
        self,
        *,
        input_trace: InputSessionTrace,
        interpreter_registry: ActionInterpreterRegistry,
        action_registry: ActionRegistry,
    ) -> None:
        self.input_trace = input_trace
        self.interpreter_registry = interpreter_registry
        self.action_registry = action_registry
        self._sessions: dict[int, RuntimeInputSession] = {}
        self._instances: list[ActionInstance] = []
        self._decisions: list[ActionDecision] = []
        self._execution_records: list[ActionExecutionRecord] = []
        self._current_frame = 0
        self._next_instance_id = 1
        self._next_request_id = 1
        self._started_this_frame: set[int] = set()

    @property
    def sessions(self) -> tuple[RuntimeInputSession, ...]:
        return tuple(sorted(self._sessions.values(), key=lambda item: item.session_id))

    @property
    def instances(self) -> tuple[ActionInstance, ...]:
        return tuple(self._instances)

    @property
    def decisions(self) -> tuple[ActionDecision, ...]:
        return tuple(self._decisions)

    @property
    def execution_records(self) -> tuple[ActionExecutionRecord, ...]:
        return tuple(self._execution_records)

    @property
    def active_instances(self) -> tuple[ActionInstance, ...]:
        return tuple(
            instance
            for instance in self._instances
            if instance.lifecycle in {ActionLifecycle.SCHEDULED, ActionLifecycle.RUNNING}
        )

    def update_frame(self, context: SimulationContext, frame: int) -> None:
        if frame < 0:
            msg = "帧号不能为负数"
            raise ValueError(msg)
        self._current_frame = frame
        self._started_this_frame = set()
        self._start_due_instances(context, frame)
        released_sessions: set[int] = set()
        pressed_sessions: set[int] = set()
        for boundary in self.input_trace.boundaries_at(frame):
            self._publish_input_key_received(context, boundary)
            if boundary.phase is KeyPhase.PRESS:
                pressed_sessions.add(boundary.session_id)
                self._handle_press(context, boundary, frame)
                continue
            released_sessions.add(boundary.session_id)
            self._handle_release(context, boundary, frame)
        self._handle_holds(context, frame, pressed_sessions | released_sessions)
        self._update_running_instances(context, frame)

    def is_idle(self) -> bool:
        if self.input_trace.has_pending_after(self._current_frame):
            return False
        if any(
            session.physical_state is InputPhysicalState.HELD
            or session.control_state is InputControlState.LISTENING
            for session in self._sessions.values()
        ):
            return False
        if any(
            instance.lifecycle in {ActionLifecycle.SCHEDULED, ActionLifecycle.RUNNING}
            for instance in self._instances
        ):
            return False
        return not any(point.status == "pending" for point in self.iter_impact_points())

    def iter_impact_points(self) -> tuple[ActionImpactPoint, ...]:
        return tuple(point for instance in self._instances for point in instance.impact_points)

    def due_impact_points(self, frame: int) -> tuple[ActionImpactPoint, ...]:
        return tuple(
            point
            for point in self.iter_impact_points()
            if point.status == "pending" and point.scheduled_frame <= frame
        )

    def mark_impact_dispatched(self, impact_point_id: str) -> None:
        for instance in self._instances:
            for index, point in enumerate(instance.impact_points):
                if point.impact_point_id != impact_point_id:
                    continue
                instance.impact_points[index] = replace(point, status="dispatched")
                return
        msg = f"未知影响点：{impact_point_id}"
        raise KeyError(msg)

    def _handle_press(
        self,
        context: SimulationContext,
        boundary: InputSessionBoundary,
        frame: int,
    ) -> None:
        plan = self.input_trace.get_session(boundary.session_id)
        binding = self.interpreter_registry.resolve(plan.key, context)
        session = RuntimeInputSession(
            session_id=plan.session_id,
            key=plan.key,
            press_frame=plan.press_frame,
            physical_state=InputPhysicalState.HELD,
            control_state=InputControlState.LISTENING,
            interpreter_binding=binding,
            owner=binding.owner,
        )
        self._sessions[boundary.session_id] = session
        self._publish_input_session_boundary(
            context,
            session,
            boundary,
            will_interpret=True,
            skip_reason=None,
        )
        self._interpret(context, session, ActionInterpretationTrigger.PRESS, frame)

    def _handle_release(
        self,
        context: SimulationContext,
        boundary: InputSessionBoundary,
        frame: int,
    ) -> None:
        session = self._sessions[boundary.session_id]
        session.physical_state = InputPhysicalState.RELEASED
        session.released_frame = frame
        will_interpret = session.control_state is InputControlState.LISTENING
        self._publish_input_session_boundary(
            context,
            session,
            boundary,
            will_interpret=will_interpret,
            skip_reason=None if will_interpret else session.control_state.value,
        )
        if will_interpret:
            self._interpret(context, session, ActionInterpretationTrigger.RELEASE, frame)
        if session.control_state is InputControlState.LISTENING:
            session.control_state = InputControlState.DETACHED

    def _publish_input_key_received(
        self,
        context: SimulationContext,
        boundary: InputSessionBoundary,
    ) -> None:
        plan = self.input_trace.get_session(boundary.session_id)
        context.events.publish(
            GameEvent(
                EventType.INPUT_KEY_RECEIVED,
                frame=boundary.frame,
                source=self,
                payload=InputKeyReceivedPayload(
                    key=plan.key,
                    phase=boundary.phase.value,
                    order=boundary.order,
                    session_id=boundary.session_id,
                ),
            )
        )

    def _publish_input_session_boundary(
        self,
        context: SimulationContext,
        session: RuntimeInputSession,
        boundary: InputSessionBoundary,
        *,
        will_interpret: bool,
        skip_reason: str | None,
    ) -> None:
        context.events.publish(
            GameEvent(
                EventType.INPUT_SESSION_BOUNDARY_REACHED,
                frame=boundary.frame,
                source=self,
                payload=InputSessionBoundaryPayload(
                    session_id=session.session_id,
                    key=session.key,
                    phase=boundary.phase.value,
                    order=boundary.order,
                    press_frame=session.press_frame,
                    held_frames=boundary.frame - session.press_frame,
                    physical_state=session.physical_state.value,
                    control_state=session.control_state.value,
                    owner_kind=session.owner.kind.value,
                    owner_slot=session.owner.slot,
                    interpreter_id=session.interpreter_binding.interpreter_id,
                    binding_scope=session.interpreter_binding.scope,
                    will_interpret=will_interpret,
                    skip_reason=skip_reason,
                ),
            )
        )

    def _handle_holds(
        self,
        context: SimulationContext,
        frame: int,
        skipped_session_ids: set[int],
    ) -> None:
        for session in self.sessions:
            if session.session_id in skipped_session_ids:
                continue
            if session.physical_state is not InputPhysicalState.HELD:
                continue
            if session.control_state is not InputControlState.LISTENING:
                continue
            self._interpret(context, session, ActionInterpretationTrigger.HOLD, frame)

    def _interpret(
        self,
        context: SimulationContext,
        session: RuntimeInputSession,
        trigger: ActionInterpretationTrigger,
        frame: int,
    ) -> None:
        view = self._session_view(session, trigger, frame)
        result = session.interpreter_binding.interpreter.interpret(context, view)
        self._apply_interpretation(context, session, result, frame)

    def _session_view(
        self,
        session: RuntimeInputSession,
        trigger: ActionInterpretationTrigger,
        frame: int,
    ) -> InputSessionView:
        return InputSessionView(
            session_id=session.session_id,
            key=session.key,
            trigger=trigger,
            press_frame=session.press_frame,
            current_frame=frame,
            held_frames=frame - session.press_frame,
            physical_state=session.physical_state,
            owner=session.owner,
            bound_instance=self._instance_by_id(session.bound_instance_id)
            if session.bound_instance_id is not None
            else None,
            release_frame=session.released_frame
            if trigger is ActionInterpretationTrigger.RELEASE
            else None,
        )

    def _apply_interpretation(
        self,
        context: SimulationContext,
        session: RuntimeInputSession,
        result: ActionInterpretationResult,
        frame: int,
    ) -> None:
        if result.kind is ActionInterpretationKind.WAIT:
            return
        if result.kind is ActionInterpretationKind.REJECT:
            self._apply_session_policy(session, result.session_policy, result.reason)
            return
        if result.kind is ActionInterpretationKind.START_ACTION:
            if result.prepared_action is None:
                self._apply_session_policy(session, InputSessionPolicy.DETACH, "missing_action")
                return
            decision = self._start_prepared_action(context, result.prepared_action, frame)
            if decision.accepted and result.prepared_action.bind_session_on_accept:
                session.bound_instance_id = decision.created_instance_id
            if decision.accepted or not result.prepared_action.continue_on_reject:
                self._apply_session_policy(session, result.session_policy, result.reason)
            return
        if result.control_request is None:
            self._apply_session_policy(session, InputSessionPolicy.DETACH, "missing_control")
            return
        self._control_action(context, result.control_request, frame)
        self._apply_session_policy(session, result.session_policy, result.reason)

    def _start_prepared_action(
        self,
        context: SimulationContext,
        prepared: PreparedAction,
        frame: int,
    ) -> ActionDecision:
        request_id = self._next_request_id
        self._next_request_id += 1
        if prepared.requested_start_frame < frame:
            return self._record_decision(
                ActionDecision(
                    request_id=request_id,
                    source_session_id=prepared.source_session_id,
                    accepted=False,
                    frame=frame,
                    action_key=prepared.action_key,
                    reject_reason=ActionDecisionRejectReason.INVALID_START_FRAME,
                )
            )
        if not self.action_registry.contains(prepared.action_key):
            return self._record_decision(
                ActionDecision(
                    request_id=request_id,
                    source_session_id=prepared.source_session_id,
                    accepted=False,
                    frame=frame,
                    action_key=prepared.action_key,
                    reject_reason=ActionDecisionRejectReason.UNSUPPORTED_ACTION,
                )
            )
        action = self.action_registry.get(prepared.action_key)
        conflicts = self._conflicting_instances(action.admission_policy)
        interrupted: list[int] = []
        if conflicts:
            if not all(
                self._can_interrupt(instance, prepared.interrupt_kind, frame)
                for instance in conflicts
            ):
                return self._record_decision(
                    ActionDecision(
                        request_id=request_id,
                        source_session_id=prepared.source_session_id,
                        accepted=False,
                        frame=frame,
                        action_key=prepared.action_key,
                        reject_reason=ActionDecisionRejectReason.LOCK_CONFLICT,
                    )
                )
            for instance in conflicts:
                self._cancel_instance(context, instance, frame, "interrupted")
                interrupted.append(instance.instance_id)

        instance = ActionInstance(
            instance_id=self._next_instance_id,
            action=action,
            action_key=action.action_key,
            owner=prepared.owner,
            source_session_id=prepared.source_session_id,
            created_frame=frame,
            start_frame=prepared.requested_start_frame,
            lifecycle=ActionLifecycle.SCHEDULED,
            action_state=action.create_initial_state(prepared.params),
            params=prepared.params,
        )
        self._next_instance_id += 1
        self._instances.append(instance)
        if prepared.requested_start_frame <= frame:
            self._start_instance(context, instance, frame)
        return self._record_decision(
            ActionDecision(
                request_id=request_id,
                source_session_id=prepared.source_session_id,
                accepted=True,
                frame=frame,
                action_key=prepared.action_key,
                created_instance_id=instance.instance_id,
                interrupted_instance_ids=tuple(interrupted),
            )
        )

    def _control_action(
        self,
        context: SimulationContext,
        request: ControlActionRequest,
        frame: int,
    ) -> ActionDecision:
        request_id = self._next_request_id
        self._next_request_id += 1
        instance = self._instance_by_id(request.target_instance_id)
        if instance is None:
            return self._record_decision(
                ActionDecision(
                    request_id=request_id,
                    source_session_id=None,
                    accepted=False,
                    frame=frame,
                    action_key="control",
                    reject_reason=ActionDecisionRejectReason.INSTANCE_NOT_FOUND,
                )
            )
        result = instance.action.on_command(
            self._execution_context(context, instance, frame),
            request,
        )
        self._apply_execution_result(context, instance, result, frame)
        return self._record_decision(
            ActionDecision(
                request_id=request_id,
                source_session_id=instance.source_session_id,
                accepted=True,
                frame=frame,
                action_key=instance.action_key,
                created_instance_id=instance.instance_id,
            )
        )

    def _start_due_instances(self, context: SimulationContext, frame: int) -> None:
        for instance in self._instances:
            if instance.lifecycle is ActionLifecycle.SCHEDULED and instance.start_frame <= frame:
                self._start_instance(context, instance, frame)

    def _start_instance(
        self,
        context: SimulationContext,
        instance: ActionInstance,
        frame: int,
    ) -> None:
        instance.lifecycle = ActionLifecycle.RUNNING
        self._started_this_frame.add(instance.instance_id)
        result = instance.action.on_start(self._execution_context(context, instance, frame))
        self._apply_execution_result(context, instance, result, frame)

    def _update_running_instances(self, context: SimulationContext, frame: int) -> None:
        for instance in tuple(self._instances):
            if instance.lifecycle is not ActionLifecycle.RUNNING:
                continue
            if instance.instance_id in self._started_this_frame:
                continue
            result = instance.action.on_update(self._execution_context(context, instance, frame))
            self._apply_execution_result(context, instance, result, frame)

    def _apply_execution_result(
        self,
        context: SimulationContext,
        instance: ActionInstance,
        result: ActionExecutionResult,
        frame: int,
    ) -> None:
        if result.next_state is not None:
            instance.action_state = result.next_state
        instance.impact_points.extend(result.emitted_impacts)
        for record in result.records:
            self._execution_records.append(
                ActionExecutionRecord(
                    frame=frame,
                    instance_id=instance.instance_id,
                    action_key=instance.action_key,
                    payload=record,
                )
            )
            if record.get("type") == "team_switch" and record.get("accepted") is True:
                previous_slot = record.get("previous_slot")
                if isinstance(previous_slot, int):
                    self.cancel_sessions_for_owner(
                        ActionOwnerRef.character(previous_slot),
                        reason="character_switch",
                    )
        if result.lifecycle_directive is ActionLifecycleDirective.FINISH:
            finish_result = instance.action.on_finish(
                self._execution_context(context, instance, frame)
            )
            instance.lifecycle = ActionLifecycle.COMPLETED
            instance.completed_frame = frame
            for record in finish_result.records:
                self._execution_records.append(
                    ActionExecutionRecord(
                        frame=frame,
                        instance_id=instance.instance_id,
                        action_key=instance.action_key,
                        payload=record,
                    )
                )
            return
        if result.lifecycle_directive is ActionLifecycleDirective.CANCEL:
            self._cancel_instance(context, instance, frame, result.cancel_reason or "canceled")

    def _cancel_instance(
        self,
        context: SimulationContext,
        instance: ActionInstance,
        frame: int,
        reason: str,
    ) -> None:
        if instance.lifecycle in {ActionLifecycle.COMPLETED, ActionLifecycle.CANCELED}:
            return
        result = instance.action.on_cancel(
            self._execution_context(context, instance, frame),
            reason,
        )
        instance.lifecycle = ActionLifecycle.CANCELED
        instance.cancel_reason = reason
        instance.completed_frame = frame
        for index, point in enumerate(instance.impact_points):
            if point.status == "pending" and point.cancel_with_action:
                instance.impact_points[index] = replace(point, status="canceled")
        for record in result.records:
            self._execution_records.append(
                ActionExecutionRecord(
                    frame=frame,
                    instance_id=instance.instance_id,
                    action_key=instance.action_key,
                    payload=record,
                )
            )

    def cancel_sessions_for_owner(self, owner: ActionOwnerRef, *, reason: str) -> None:
        for session in self._sessions.values():
            if session.owner != owner:
                continue
            if session.control_state is not InputControlState.LISTENING:
                continue
            session.control_state = InputControlState.CANCELED
            session.cancel_reason = reason

    def _apply_session_policy(
        self,
        session: RuntimeInputSession,
        policy: InputSessionPolicy,
        reason: str | None,
    ) -> None:
        if policy is InputSessionPolicy.KEEP_LISTENING:
            return
        if policy is InputSessionPolicy.DETACH:
            session.control_state = InputControlState.DETACHED
            return
        session.control_state = InputControlState.CANCELED
        session.cancel_reason = reason

    def _conflicting_instances(
        self,
        policy: ActionAdmissionPolicy,
    ) -> tuple[ActionInstance, ...]:
        if policy.concurrency_policy == "allow_parallel" or not policy.required_locks:
            return ()
        requested = set(policy.required_locks)
        return tuple(
            instance
            for instance in self._instances
            if instance.lifecycle in {ActionLifecycle.SCHEDULED, ActionLifecycle.RUNNING}
            and requested.intersection(instance.action.admission_policy.required_locks)
        )

    def _can_interrupt(
        self,
        instance: ActionInstance,
        interrupt_kind: str | None,
        frame: int,
    ) -> bool:
        elapsed = max(0, frame - instance.start_frame)
        return instance.action.admission_policy.interrupt_policy.allows(
            interrupt_kind,
            elapsed,
        )

    def _execution_context(
        self,
        context: SimulationContext,
        instance: ActionInstance,
        frame: int,
    ) -> ActionExecutionContext:
        return ActionExecutionContext(
            frame=frame,
            instance_id=instance.instance_id,
            owner=instance.owner,
            source_session_id=instance.source_session_id,
            start_frame=instance.start_frame,
            elapsed_frames=frame - instance.start_frame,
            action_state=instance.action_state,
            simulation_context=context,
            params=instance.params,
        )

    def _record_decision(self, decision: ActionDecision) -> ActionDecision:
        self._decisions.append(decision)
        return decision

    def _instance_by_id(self, instance_id: int | None) -> ActionInstance | None:
        if instance_id is None:
            return None
        for instance in self._instances:
            if instance.instance_id == instance_id:
                return instance
        return None


def _switch_slot_from_key(key: str) -> int | None:
    if key not in {"keyboard.1", "keyboard.2", "keyboard.3", "keyboard.4"}:
        return None
    return int(key.removeprefix("keyboard."))


def _validate_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        msg = f"{field_name} 必须是非空字符串"
        raise ValueError(msg)
