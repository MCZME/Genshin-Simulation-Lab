from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from genshin_sim.core.protocols import FrameUpdatable
from genshin_sim.core.space import Space, Vector3

if TYPE_CHECKING:
    from genshin_sim.core.simulation import SimulationContext


class ActionRejectReason(StrEnum):
    """动作请求被拒绝的最小原因集合。"""

    BUSY = "busy"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class TargetQuery:
    """动作请求附带的最小目标查询。"""

    origin: Vector3
    radius: float

    def __post_init__(self) -> None:
        if self.radius < 0:
            msg = "target query radius must be non-negative"
            raise ValueError(msg)

@dataclass(frozen=True, slots=True)
class ActionRequest:
    """一次由输入产生的动作请求。"""

    frame: int
    key: str
    active_slot: int
    duration_frames: int = 1
    target_query: TargetQuery | None = None


@dataclass(frozen=True, slots=True)
class ActionLock:
    """一个占用动作输入窗口的最小运行态。"""

    source: str
    start_frame: int
    end_frame: int
    active_slot: int

    def contains(self, frame: int) -> bool:
        return self.start_frame <= frame < self.end_frame


@dataclass(frozen=True, slots=True)
class ActionInstance:
    """已被接受并进入运行态的最小动作实例。"""

    instance_id: int
    key: str
    active_slot: int
    start_frame: int
    end_frame: int
    target_query: TargetQuery | None = None
    target_ids: tuple[str, ...] = ()

    def contains(self, frame: int) -> bool:
        return self.start_frame <= frame < self.end_frame


@dataclass(frozen=True, slots=True)
class ActionDecision:
    """动作请求的接受或拒绝结果。"""

    request: ActionRequest
    accepted: bool
    reject_reason: ActionRejectReason | None = None
    lock: ActionLock | None = None
    instance: ActionInstance | None = None

    @property
    def occupied_until_frame(self) -> int | None:
        if self.lock is None:
            return None
        return self.lock.end_frame


class ActionManager(FrameUpdatable):
    """最小动作管理器。

    当前只表达输入是否能被动作层接受，以及动作或后摇占用到哪一帧。
    """

    def __init__(self, supported_keys: Iterable[str] | None = None) -> None:
        self._supported_keys = None if supported_keys is None else frozenset(supported_keys)
        self._locks: list[ActionLock] = []
        self._instances: list[ActionInstance] = []
        self._decisions: list[ActionDecision] = []
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
            instance.end_frame <= self._current_frame for instance in self._instances
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
        active_slot: int,
    ) -> ActionLock:
        if duration_frames <= 0:
            msg = "duration_frames must be positive"
            raise ValueError(msg)

        lock = ActionLock(
            source=source,
            start_frame=frame,
            end_frame=frame + duration_frames,
            active_slot=active_slot,
        )
        self._locks.append(lock)
        return lock

    def request_action(
        self,
        context: SimulationContext,
        request: ActionRequest,
    ) -> ActionDecision:
        if request.duration_frames <= 0:
            msg = "duration_frames must be positive"
            raise ValueError(msg)

        if self._supported_keys is not None and request.key not in self._supported_keys:
            decision = ActionDecision(
                request=request,
                accepted=False,
                reject_reason=ActionRejectReason.UNSUPPORTED,
            )
            self._decisions.append(decision)
            return decision

        blocking_lock = self.current_lock(request.frame)
        if blocking_lock is not None:
            decision = ActionDecision(
                request=request,
                accepted=False,
                reject_reason=ActionRejectReason.BUSY,
                lock=blocking_lock,
            )
            self._decisions.append(decision)
            return decision

        lock = self.reserve(
            frame=request.frame,
            duration_frames=request.duration_frames,
            source=request.key,
            active_slot=request.active_slot,
        )
        instance = self._create_instance(context, request, lock)
        decision = ActionDecision(request=request, accepted=True, lock=lock, instance=instance)
        self._decisions.append(decision)
        return decision

    def _create_instance(
        self,
        context: SimulationContext,
        request: ActionRequest,
        lock: ActionLock,
    ) -> ActionInstance:
        instance = ActionInstance(
            instance_id=self._next_instance_id,
            key=request.key,
            active_slot=request.active_slot,
            start_frame=lock.start_frame,
            end_frame=lock.end_frame,
            target_query=request.target_query,
            target_ids=self._resolve_target_ids(context, request.target_query),
        )
        self._next_instance_id += 1
        self._instances.append(instance)
        return instance

    def _resolve_target_ids(
        self,
        context: SimulationContext,
        target_query: TargetQuery | None,
    ) -> tuple[str, ...]:
        if target_query is None:
            return ()
        if not isinstance(context.space, Space):
            return ()
        return tuple(
            target.target_id
            for target in context.space.targets_in_radius(target_query.origin, target_query.radius)
        )
