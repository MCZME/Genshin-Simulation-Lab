from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from genshin_sim.core.protocols import FrameUpdatable
from genshin_sim.core.space import SpatialEntityKind, Vector3

if TYPE_CHECKING:
    from genshin_sim.core.simulation import SimulationContext


class ActionRejectReason(StrEnum):
    """动作时间轴被拒绝的最小原因集合。"""

    BUSY = "busy"
    UNSUPPORTED = "unsupported"


TEAM_SWITCH_ACTION_KEY = "team.switch"
TEAM_SWITCH_TARGET_SLOT_PARAM = "target_slot"


@dataclass(frozen=True, slots=True)
class SpatialQuery:
    """动作时间轴附带的最小空间查询。"""

    origin: Vector3
    radius: float

    def __post_init__(self) -> None:
        if self.radius < 0:
            msg = "空间查询半径必须为非负数"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class ActionTimelineSpec:
    """角色解释器提交给动作管理器的通用动作时间轴。"""

    action_key: str
    owner_slot: int
    start_frame: int
    duration_frames: int = 1
    source_key: str | None = None
    actor_entity_id: str | None = None
    spatial_query: SpatialQuery | None = None
    impact_keys: tuple[str, ...] = ()
    impact_frame_offsets: Mapping[str, int] = field(default_factory=dict)
    create_default_impact_point: bool = True
    params: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.duration_frames <= 0:
            msg = "duration_frames 必须是正整数"
            raise ValueError(msg)
        if self.actor_entity_id is not None and not self.actor_entity_id.strip():
            msg = "actor_entity_id 必须是非空字符串"
            raise ValueError(msg)
        offsets: dict[str, int] = {}
        for impact_key, offset in self.impact_frame_offsets.items():
            if not isinstance(impact_key, str) or not impact_key.strip():
                msg = "impact_frame_offsets 的 key 必须是非空字符串"
                raise ValueError(msg)
            if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
                msg = "impact_frame_offsets 的 value 必须是非负整数"
                raise ValueError(msg)
            offsets[impact_key] = offset
        object.__setattr__(self, "impact_frame_offsets", offsets)
        object.__setattr__(self, "params", dict(self.params))


@dataclass(frozen=True, slots=True)
class ActionLock:
    """一个占用动作输入窗口的最小运行态。"""

    source: str
    start_frame: int
    end_frame: int
    owner_slot: int

    def contains(self, frame: int) -> bool:
        return self.start_frame <= frame < self.end_frame


@dataclass(frozen=True, slots=True)
class CandidateTargetRef:
    """动作空间查询解析出的候选目标引用。"""

    spatial_entity_id: str
    target_id: str


@dataclass(frozen=True, slots=True)
class ActionImpactPoint:
    """动作实例内的最小影响点。

    它只描述动作时间轴上的候选影响点，不表示最终命中、伤害或反应。
    """

    frame: int
    impact_key: str
    candidate_entity_ids: tuple[str, ...] = ()
    candidate_targets: tuple[CandidateTargetRef, ...] = ()


@dataclass(frozen=True, slots=True)
class ActionInstance:
    """已被接受并进入运行态的最小动作实例。"""

    instance_id: int
    action_key: str
    source_key: str
    owner_slot: int
    start_frame: int
    end_frame: int
    actor_entity_id: str | None = None
    spatial_query: SpatialQuery | None = None
    candidate_entity_ids: tuple[str, ...] = ()
    candidate_targets: tuple[CandidateTargetRef, ...] = ()
    impact_points: tuple[ActionImpactPoint, ...] = ()
    params: Mapping[str, object] = field(default_factory=dict)

    def contains(self, frame: int) -> bool:
        return self.start_frame <= frame < self.end_frame


@dataclass(frozen=True, slots=True)
class ActionDecision:
    """动作时间轴的接受或拒绝结果。"""

    timeline: ActionTimelineSpec
    accepted: bool
    reject_reason: ActionRejectReason | None = None
    lock: ActionLock | None = None
    instance: ActionInstance | None = None

    @property
    def occupied_until_frame(self) -> int | None:
        if self.lock is None:
            return None
        return self.lock.end_frame


@dataclass(frozen=True, slots=True)
class ActionConsumptionRecord:
    """运行时消费动作实例后的通用记录。"""

    frame: int
    instance_id: int
    action_key: str
    actor_entity_id: str | None
    consumer_key: str
    status: str
    payload: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.frame < 0:
            msg = "消费记录帧号不能为负数"
            raise ValueError(msg)
        if self.instance_id <= 0:
            msg = "消费记录 instance_id 必须是正整数"
            raise ValueError(msg)
        if not self.action_key.strip():
            msg = "消费记录 action_key 必须是非空字符串"
            raise ValueError(msg)
        if self.actor_entity_id is not None and not self.actor_entity_id.strip():
            msg = "消费记录 actor_entity_id 必须是非空字符串"
            raise ValueError(msg)
        if not self.consumer_key.strip():
            msg = "消费记录 consumer_key 必须是非空字符串"
            raise ValueError(msg)
        if not self.status.strip():
            msg = "消费记录 status 必须是非空字符串"
            raise ValueError(msg)
        object.__setattr__(self, "payload", dict(self.payload))


class ActionManager(FrameUpdatable):
    """通用动作调度器。

    它只接收已经解释完成的动作时间轴，管理 busy lock、动作实例和影响点。
    """

    def __init__(
        self,
        *,
        supported_action_keys: Iterable[str] | None = None,
    ) -> None:
        self._supported_action_keys = (
            None if supported_action_keys is None else frozenset(supported_action_keys)
        )
        self._locks: list[ActionLock] = []
        self._instances: list[ActionInstance] = []
        self._decisions: list[ActionDecision] = []
        self._consumption_records: list[ActionConsumptionRecord] = []
        self._current_frame = 0
        self._next_instance_id = 1

    @property
    def locks(self) -> tuple[ActionLock, ...]:
        return tuple(self._locks)

    @property
    def decisions(self) -> tuple[ActionDecision, ...]:
        return tuple(self._decisions)

    @property
    def instances(self) -> tuple[ActionInstance, ...]:
        return tuple(self._instances)

    @property
    def consumption_records(self) -> tuple[ActionConsumptionRecord, ...]:
        return tuple(self._consumption_records)

    @property
    def active_instances(self) -> tuple[ActionInstance, ...]:
        return tuple(
            instance for instance in self._instances if instance.contains(self._current_frame)
        )

    def is_busy(self, frame: int) -> bool:
        return self.current_lock(frame) is not None

    def update_frame(self, context: SimulationContext, frame: int) -> None:
        del context
        self._current_frame = frame

    def is_idle(self) -> bool:
        locks_idle = all(lock.end_frame <= self._current_frame for lock in self._locks)
        instances_idle = all(
            instance.end_frame <= self._current_frame
            and all(point.frame <= self._current_frame for point in instance.impact_points)
            for instance in self._instances
        )
        return locks_idle and instances_idle

    def current_lock(self, frame: int) -> ActionLock | None:
        for lock in reversed(self._locks):
            if lock.contains(frame):
                return lock
        return None

    def reserve(
        self,
        *,
        frame: int,
        duration_frames: int,
        source: str,
        owner_slot: int,
    ) -> ActionLock:
        if duration_frames <= 0:
            msg = "duration_frames 必须是正整数"
            raise ValueError(msg)

        lock = ActionLock(
            source=source,
            start_frame=frame,
            end_frame=frame + duration_frames,
            owner_slot=owner_slot,
        )
        self._locks.append(lock)
        return lock

    def record_consumption(
        self,
        *,
        frame: int,
        instance_id: int,
        consumer_key: str,
        status: str,
        payload: Mapping[str, object] | None = None,
    ) -> ActionConsumptionRecord:
        instance = self._instance_by_id(instance_id)
        record = ActionConsumptionRecord(
            frame=frame,
            instance_id=instance.instance_id,
            action_key=instance.action_key,
            actor_entity_id=instance.actor_entity_id,
            consumer_key=consumer_key,
            status=status,
            payload={} if payload is None else payload,
        )
        self._consumption_records.append(record)
        return record

    def schedule_timeline(
        self,
        context: SimulationContext,
        timeline: ActionTimelineSpec,
    ) -> ActionDecision:
        if self._supported_action_keys is not None and timeline.action_key not in (
            self._supported_action_keys
        ):
            decision = ActionDecision(
                timeline=timeline,
                accepted=False,
                reject_reason=ActionRejectReason.UNSUPPORTED,
            )
            self._decisions.append(decision)
            return decision

        blocking_lock = self.current_lock(timeline.start_frame)
        if blocking_lock is not None:
            decision = ActionDecision(
                timeline=timeline,
                accepted=False,
                reject_reason=ActionRejectReason.BUSY,
                lock=blocking_lock,
            )
            self._decisions.append(decision)
            return decision

        lock = self.reserve(
            frame=timeline.start_frame,
            duration_frames=timeline.duration_frames,
            source=timeline.source_key or timeline.action_key,
            owner_slot=timeline.owner_slot,
        )
        instance = self._create_instance(context, timeline, lock)
        decision = ActionDecision(timeline=timeline, accepted=True, lock=lock, instance=instance)
        self._decisions.append(decision)
        return decision

    def _create_instance(
        self,
        context: SimulationContext,
        timeline: ActionTimelineSpec,
        lock: ActionLock,
    ) -> ActionInstance:
        candidate_entity_ids = self._resolve_candidate_entity_ids(
            context,
            timeline.spatial_query,
        )
        candidate_targets = (
            ()
            if context.space_runtime is None
            else context.space_runtime.resolve_candidate_targets(candidate_entity_ids)
        )
        if timeline.impact_keys:
            impact_keys = timeline.impact_keys
        elif timeline.create_default_impact_point:
            impact_keys = (timeline.action_key,)
        else:
            impact_keys = ()
        instance = ActionInstance(
            instance_id=self._next_instance_id,
            action_key=timeline.action_key,
            source_key=timeline.source_key or timeline.action_key,
            owner_slot=timeline.owner_slot,
            start_frame=lock.start_frame,
            end_frame=lock.end_frame,
            actor_entity_id=timeline.actor_entity_id,
            spatial_query=timeline.spatial_query,
            candidate_entity_ids=candidate_entity_ids,
            candidate_targets=candidate_targets,
            impact_points=tuple(
                ActionImpactPoint(
                    frame=lock.start_frame + timeline.impact_frame_offsets.get(impact_key, 0),
                    impact_key=impact_key,
                    candidate_entity_ids=candidate_entity_ids,
                    candidate_targets=candidate_targets,
                )
                for impact_key in impact_keys
            ),
            params=timeline.params,
        )
        self._next_instance_id += 1
        self._instances.append(instance)
        return instance

    def _instance_by_id(self, instance_id: int) -> ActionInstance:
        for instance in self._instances:
            if instance.instance_id == instance_id:
                return instance
        msg = f"未知动作实例 id：{instance_id}"
        raise KeyError(msg)

    def _resolve_candidate_entity_ids(
        self,
        context: SimulationContext,
        spatial_query: SpatialQuery | None,
    ) -> tuple[str, ...]:
        if spatial_query is None:
            return ()
        if context.space_runtime is None:
            return ()
        return tuple(
            entity.entity_id
            for entity in context.space_runtime.entities_in_radius(
                spatial_query.origin,
                spatial_query.radius,
                kinds={SpatialEntityKind.TARGET},
            )
        )
