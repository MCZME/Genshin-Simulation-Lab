"""动作领域数据模型与规格。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from genshin_sim.core.actions.enums import (
    ActionDecisionRejectReason,
    ActionInterpretationKind,
    ActionInterpretationTrigger,
    ActionLifecycle,
    ActionLifecycleDirective,
    ActionOwnerKind,
    InputControlState,
    InputPhysicalState,
    InputSessionPolicy,
    SnapshotPolicy,
)
from genshin_sim.core.space.geometry import Vector3

if TYPE_CHECKING:
    from genshin_sim.core.actions.interpreters import ActionInterpreter
    from genshin_sim.core.actions.protocols import Action
    from genshin_sim.core.simulation import SimulationContext


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


@dataclass(frozen=True, slots=True)
class SearchAreaSpec:
    """动作索敌搜索区域规格。

    ``shape`` 与 ``radius``/``height`` 保留资料原始形状和范围（如圆柱
    `15,10`）；当前空间模型只使用 X/Z 平面，圆柱投影为同半径圆，高度暂不参与
    查询。``radius`` 由运行时作为 X/Z 查询半径使用。
    """

    shape: str
    radius: float
    height: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.shape, str) or not self.shape.strip():
            raise ValueError("SearchAreaSpec.shape 必须是非空字符串")
        if (
            isinstance(self.radius, bool)
            or not isinstance(self.radius, int | float)
            or self.radius < 0
        ):
            raise ValueError("SearchAreaSpec.radius 必须为非负数")
        if self.height is not None and (
            isinstance(self.height, bool)
            or not isinstance(self.height, int | float)
            or self.height < 0
        ):
            raise ValueError("SearchAreaSpec.height 必须为非负数")


@dataclass(frozen=True, slots=True)
class TargetingSpec:
    """动作影响点的目标解析规格。"""

    origin: Vector3 = field(default_factory=Vector3)
    radius: float = 0.0
    search_area: SearchAreaSpec | None = None
    selection_policy_key: str | None = None
    kinds: tuple[str, ...] = ("target",)
    exclude_entity_ids: tuple[str, ...] = ()
    snapshot_policy: SnapshotPolicy = SnapshotPolicy.RESOLVE_ON_IMPACT
    snapshot_entity_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.radius < 0:
            msg = "目标查询半径必须为非负数"
            raise ValueError(msg)
        if self.search_area is not None and not isinstance(self.search_area, SearchAreaSpec):
            raise ValueError("search_area 必须是 SearchAreaSpec 或 None")
        if self.selection_policy_key is not None and (
            not isinstance(self.selection_policy_key, str)
            or not self.selection_policy_key.strip()
        ):
            raise ValueError("selection_policy_key 提供时必须是非空字符串")
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
