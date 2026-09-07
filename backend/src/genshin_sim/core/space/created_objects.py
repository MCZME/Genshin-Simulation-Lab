from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Protocol

from genshin_sim.core.entity_states.lifecycle import EntityLifecycle, EntityLifecycleState
from genshin_sim.core.protocols import FrameUpdatable
from genshin_sim.core.space.entities import SpatialEntity, SpatialEntityKind
from genshin_sim.core.space.geometry import Vector3

if TYPE_CHECKING:
    from genshin_sim.core.impacts.models import ImpactRequest
    from genshin_sim.core.simulation import SimulationContext


@dataclass(frozen=True, slots=True)
class CreatedObjectTickSpec:
    """创建物上的一个独立 tick 调度规格。"""

    behavior_key: str
    first_tick_frame_offset: int = 0
    interval_frames: int | None = None

    def __post_init__(self) -> None:
        _validate_non_empty_text(self.behavior_key, "创建物 tick 行为 key")
        if isinstance(self.first_tick_frame_offset, bool) or self.first_tick_frame_offset < 0:
            msg = "创建物 tick 首次偏移不能为负数"
            raise ValueError(msg)
        if self.interval_frames is not None and self.interval_frames <= 0:
            msg = "创建物 tick 间隔必须是正整数"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class CreatedObjectSpec:
    """内容创建场上对象的创建与刷新规格。"""

    object_key: str
    duration_frames: int
    position: Vector3 = field(default_factory=Vector3)
    facing: Vector3 = Vector3(0.0, 0.0, 1.0)
    owner_key: str | None = None
    source_key: str | None = None
    behavior_key: str | None = None
    entity_id: str | None = None
    tick_schedules: tuple[CreatedObjectTickSpec, ...] = ()
    tick_interval_frames: int | None = None
    first_tick_frame_offset: int | None = None
    follow_entity_id: str | None = None
    max_instances: int = 1
    refresh_existing: bool = True
    tags: tuple[str, ...] = field(default_factory=tuple)
    params: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_non_empty_text(self.object_key, "内容创建对象 key")
        if self.duration_frames <= 0:
            msg = "内容创建对象持续帧数必须是正整数"
            raise ValueError(msg)
        if self.owner_key is not None:
            _validate_non_empty_text(self.owner_key, "内容创建对象归属 key")
        if self.source_key is not None:
            _validate_non_empty_text(self.source_key, "内容创建对象来源 key")
        if self.behavior_key is not None:
            _validate_non_empty_text(self.behavior_key, "内容创建对象行为 key")
        if self.entity_id is not None:
            _validate_non_empty_text(self.entity_id, "内容创建对象实体 id")
        for schedule in self.tick_schedules:
            if not isinstance(schedule, CreatedObjectTickSpec):
                msg = "tick_schedules 成员必须是 CreatedObjectTickSpec"
                raise ValueError(msg)
        object.__setattr__(self, "tick_schedules", tuple(self.tick_schedules))
        if self.tick_interval_frames is not None and self.tick_interval_frames <= 0:
            msg = "内容创建对象 tick 间隔必须是正整数"
            raise ValueError(msg)
        if self.first_tick_frame_offset is not None and self.first_tick_frame_offset < 0:
            msg = "内容创建对象首次 tick 偏移不能为负数"
            raise ValueError(msg)
        if self.follow_entity_id is not None:
            _validate_non_empty_text(self.follow_entity_id, "内容创建对象跟随实体 id")
        if self.max_instances <= 0:
            msg = "内容创建对象数量上限必须是正整数"
            raise ValueError(msg)
        for tag in self.tags:
            _validate_non_empty_text(tag, "内容创建对象标签")
        object.__setattr__(self, "tags", tuple(self.tags))
        object.__setattr__(self, "params", dict(self.params))


@dataclass(frozen=True, slots=True)
class CreatedObjectExtensionRecord:
    """一次创建物持续时间延长的提交记录。"""

    frame: int
    object_key: str
    entity_id: str
    requested_frames: int
    applied_frames: int
    remaining_cap_frames: int | None = None

    def __post_init__(self) -> None:
        _validate_frame(self.frame)
        _validate_non_empty_text(self.object_key, "创建对象 key")
        _validate_non_empty_text(self.entity_id, "创建对象实体 id")
        _validate_positive_int(self.requested_frames, "请求延长帧数")
        _validate_non_negative_int(self.applied_frames, "实际延长帧数")
        if self.applied_frames > self.requested_frames:
            msg = "创建物实际延长帧数不能超过请求帧数"
            raise ValueError(msg)
        if self.remaining_cap_frames is not None:
            _validate_non_negative_int(self.remaining_cap_frames, "剩余上限帧数")


@dataclass(slots=True)
class CreatedObjectTickState:
    """创建物上一个 tick 调度的运行态。"""

    behavior_key: str
    next_tick_frame: int | None
    interval_frames: int | None = None


@dataclass(slots=True)
class CreatedObjectRuntimeState:
    """内容创建场上对象的运行态。"""

    entity: SpatialEntity
    object_key: str
    behavior_key: str | None = None
    next_tick_frame: int | None = None
    tick_interval_frames: int | None = None
    tick_schedules: tuple[CreatedObjectTickState, ...] = ()
    follow_entity_id: str | None = None
    extra_duration_frames: int = 0
    params: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.entity.kind is not SpatialEntityKind.CREATED_OBJECT:
            msg = "内容创建对象运行态必须组合 CREATED_OBJECT 空间实体"
            raise ValueError(msg)
        _validate_non_empty_text(self.object_key, "内容创建对象 key")
        if self.behavior_key is not None:
            _validate_non_empty_text(self.behavior_key, "内容创建对象行为 key")
        if (
            self.next_tick_frame is not None
            and self.next_tick_frame < self.entity.lifecycle.created_frame
        ):
            msg = "内容创建对象下一次 tick 帧不能早于创建帧"
            raise ValueError(msg)
        if self.tick_interval_frames is not None and self.tick_interval_frames <= 0:
            msg = "内容创建对象 tick 间隔必须是正整数"
            raise ValueError(msg)
        for schedule in self.tick_schedules:
            if not isinstance(schedule, CreatedObjectTickState):
                msg = "tick_schedules 成员必须是 CreatedObjectTickState"
                raise ValueError(msg)
        object.__setattr__(self, "tick_schedules", tuple(self.tick_schedules))
        if self.follow_entity_id is not None:
            _validate_non_empty_text(self.follow_entity_id, "内容创建对象跟随实体 id")
        _validate_non_negative_int(self.extra_duration_frames, "内容创建对象已延长帧数")
        self.params = dict(self.params)

    def is_active_at(self, frame: int) -> bool:
        return self.entity.is_active_at(frame)

    def expire(self) -> None:
        self.entity = replace(
            self.entity,
            lifecycle=self.entity.lifecycle.expired(),
        )
        self.next_tick_frame = None


class CreatedObjectBehavior(Protocol):
    """内容创建场上对象的 tick 行为协议。"""

    def create_tick_requests(
        self,
        state: CreatedObjectRuntimeState,
        frame: int,
    ) -> Sequence[ImpactRequest]:
        """为到期 tick 帧创建影响请求。"""
        ...


class CreatedObjectRuntime(FrameUpdatable):
    """内容创建场上对象的生命周期与 tick 运行时。"""

    def __init__(self, behaviors: Mapping[str, CreatedObjectBehavior] | None = None) -> None:
        self._behaviors: dict[str, CreatedObjectBehavior] = {}
        self._objects: list[CreatedObjectRuntimeState] = []
        self._pending_impact_requests: list[ImpactRequest] = []
        self._emitted_impact_requests: list[ImpactRequest] = []
        self._extension_records: list[CreatedObjectExtensionRecord] = []
        self._current_frame = 0
        self._next_entity_index = 1

        if behaviors is not None:
            for behavior_key, behavior in behaviors.items():
                self.register(behavior_key, behavior)

    @property
    def behavior_keys(self) -> tuple[str, ...]:
        return tuple(self._behaviors)

    @property
    def objects(self) -> tuple[CreatedObjectRuntimeState, ...]:
        return tuple(self._objects)

    @property
    def active_objects(self) -> tuple[CreatedObjectRuntimeState, ...]:
        return tuple(obj for obj in self._objects if obj.is_active_at(self._current_frame))

    @property
    def pending_impact_requests(self) -> tuple[ImpactRequest, ...]:
        return tuple(self._pending_impact_requests)

    @property
    def emitted_impact_requests(self) -> tuple[ImpactRequest, ...]:
        return tuple(self._emitted_impact_requests)

    @property
    def extension_records(self) -> tuple[CreatedObjectExtensionRecord, ...]:
        return tuple(self._extension_records)

    def register(self, behavior_key: str, behavior: CreatedObjectBehavior) -> None:
        _validate_non_empty_text(behavior_key, "内容创建对象行为 key")
        self._behaviors[behavior_key] = behavior

    def extend_duration(
        self,
        *,
        object_key: str,
        owner_key: str | None,
        frames: int,
        max_extra_frames: int | None = None,
        frame: int,
    ) -> CreatedObjectExtensionRecord | None:
        """延长活动创建物的持续时间，并按实例记录已使用延长预算。

        ``max_extra_frames`` 表示该创建物实例通过本入口累计可延长的上限；
        刷新（重放技能）会重置实例预算。没有活动匹配对象时返回 ``None``。
        """

        _validate_non_empty_text(object_key, "创建对象 key")
        if owner_key is not None:
            _validate_non_empty_text(owner_key, "创建对象归属 key")
        _validate_positive_int(frames, "请求延长帧数")
        if max_extra_frames is not None:
            _validate_positive_int(max_extra_frames, "延长上限帧数")
        _validate_frame(frame)
        obj = self._active_object_for(object_key, owner_key, frame)
        if obj is None:
            return None
        remaining = (
            None
            if max_extra_frames is None
            else max(max_extra_frames - obj.extra_duration_frames, 0)
        )
        applied = min(frames, remaining) if remaining is not None else frames
        remaining_after = None if remaining is None else remaining - applied
        record = CreatedObjectExtensionRecord(
            frame=frame,
            object_key=object_key,
            entity_id=obj.entity.entity_id,
            requested_frames=frames,
            applied_frames=applied,
            remaining_cap_frames=remaining_after,
        )
        self._extension_records.append(record)
        if applied <= 0:
            return record
        obj.extra_duration_frames += applied
        lifecycle = obj.entity.lifecycle
        obj.entity = replace(
            obj.entity,
            lifecycle=replace(
                lifecycle,
                expires_at_frame=(
                    None
                    if lifecycle.expires_at_frame is None
                    else lifecycle.expires_at_frame + applied
                ),
            ),
        )
        return record

    def create(self, spec: CreatedObjectSpec, frame: int) -> CreatedObjectRuntimeState:
        return self.create_or_refresh(spec, frame)

    def create_or_refresh(
        self,
        spec: CreatedObjectSpec,
        frame: int,
    ) -> CreatedObjectRuntimeState:
        _validate_frame(frame)
        self._current_frame = frame
        self._expire_due_objects(frame)

        active_objects = self._objects_for_spec(spec, frame)
        if active_objects and spec.refresh_existing:
            return self._refresh_object(active_objects[-1], spec, frame)
        if len(active_objects) >= spec.max_instances:
            return self._refresh_object(active_objects[0], spec, frame)
        return self._create_object(spec, frame)

    def drain_impact_requests(self) -> tuple[ImpactRequest, ...]:
        requests = tuple(self._pending_impact_requests)
        self._pending_impact_requests.clear()
        return requests

    def update_frame(self, context: SimulationContext, frame: int) -> None:
        _validate_frame(frame)
        self._current_frame = frame
        self._pending_impact_requests.clear()
        self._sync_followers(context)

        for obj in self._objects:
            if obj.entity.lifecycle.state is not EntityLifecycleState.ACTIVE:
                continue
            if _expire_if_due(obj, frame):
                continue
            self._tick_object(obj, frame)

    def is_idle(self) -> bool:
        return all(
            obj.entity.lifecycle.state is not EntityLifecycleState.ACTIVE for obj in self._objects
        )

    def _create_object(self, spec: CreatedObjectSpec, frame: int) -> CreatedObjectRuntimeState:
        entity_id = spec.entity_id or self._next_entity_id(spec.object_key)
        entity = SpatialEntity(
            entity_id=entity_id,
            kind=SpatialEntityKind.CREATED_OBJECT,
            position=spec.position,
            lifecycle=EntityLifecycle(
                created_frame=frame,
                expires_at_frame=frame + spec.duration_frames,
            ),
            facing=spec.facing,
            owner_key=spec.owner_key,
            source_key=spec.source_key,
            tags=spec.tags,
        )
        obj = CreatedObjectRuntimeState(
            entity=entity,
            object_key=spec.object_key,
            behavior_key=(None if spec.tick_schedules else (spec.behavior_key or spec.object_key)),
            next_tick_frame=None if spec.tick_schedules else _initial_tick_frame(spec, frame),
            tick_interval_frames=(None if spec.tick_schedules else spec.tick_interval_frames),
            tick_schedules=(
                tuple(
                    CreatedObjectTickState(
                        behavior_key=schedule.behavior_key,
                        next_tick_frame=frame + schedule.first_tick_frame_offset,
                        interval_frames=schedule.interval_frames,
                    )
                    for schedule in spec.tick_schedules
                )
                if spec.tick_schedules
                else ()
            ),
            follow_entity_id=spec.follow_entity_id,
            params=spec.params,
        )
        self._objects.append(obj)
        return obj

    def _refresh_object(
        self,
        obj: CreatedObjectRuntimeState,
        spec: CreatedObjectSpec,
        frame: int,
    ) -> CreatedObjectRuntimeState:
        obj.entity = replace(
            obj.entity,
            position=spec.position,
            lifecycle=EntityLifecycle(
                created_frame=obj.entity.lifecycle.created_frame,
                expires_at_frame=frame + spec.duration_frames,
            ),
            facing=spec.facing,
            owner_key=spec.owner_key,
            source_key=spec.source_key,
            tags=spec.tags,
        )
        obj.behavior_key = None if spec.tick_schedules else (spec.behavior_key or spec.object_key)
        obj.next_tick_frame = None if spec.tick_schedules else _initial_tick_frame(spec, frame)
        obj.tick_interval_frames = None if spec.tick_schedules else spec.tick_interval_frames
        obj.tick_schedules = (
            tuple(
                CreatedObjectTickState(
                    behavior_key=schedule.behavior_key,
                    next_tick_frame=frame + schedule.first_tick_frame_offset,
                    interval_frames=schedule.interval_frames,
                )
                for schedule in spec.tick_schedules
            )
            if spec.tick_schedules
            else ()
        )
        obj.follow_entity_id = spec.follow_entity_id
        obj.params = dict(spec.params)
        obj.extra_duration_frames = 0
        return obj

    def _tick_object(self, obj: CreatedObjectRuntimeState, frame: int) -> None:
        if obj.tick_schedules:
            for schedule in obj.tick_schedules:
                self._tick_schedule(obj, schedule, frame)
            return
        while obj.next_tick_frame is not None and obj.next_tick_frame <= frame:
            tick_frame = obj.next_tick_frame
            expires_at_frame = obj.entity.lifecycle.expires_at_frame
            if expires_at_frame is not None and tick_frame >= expires_at_frame:
                obj.next_tick_frame = None
                return

            behavior = self._behavior_for(obj.behavior_key or obj.object_key)
            requests = tuple(behavior.create_tick_requests(obj, tick_frame))
            self._pending_impact_requests.extend(requests)
            self._emitted_impact_requests.extend(requests)

            if obj.tick_interval_frames is None:
                obj.next_tick_frame = None
                return
            obj.next_tick_frame = tick_frame + obj.tick_interval_frames

    def _tick_schedule(
        self,
        obj: CreatedObjectRuntimeState,
        schedule: CreatedObjectTickState,
        frame: int,
    ) -> None:
        while schedule.next_tick_frame is not None and schedule.next_tick_frame <= frame:
            tick_frame = schedule.next_tick_frame
            expires_at_frame = obj.entity.lifecycle.expires_at_frame
            if expires_at_frame is not None and tick_frame >= expires_at_frame:
                schedule.next_tick_frame = None
                return

            behavior = self._behavior_for(schedule.behavior_key)
            requests = tuple(behavior.create_tick_requests(obj, tick_frame))
            self._pending_impact_requests.extend(requests)
            self._emitted_impact_requests.extend(requests)

            if schedule.interval_frames is None:
                schedule.next_tick_frame = None
                return
            schedule.next_tick_frame = tick_frame + schedule.interval_frames

    def _sync_followers(self, context: SimulationContext) -> None:
        """把声明了跟随实体的活动对象同步到目标实体位置。"""

        space_runtime = getattr(context, "space_runtime", None)
        if space_runtime is None:
            return
        for obj in self._objects:
            if obj.entity.lifecycle.state is not EntityLifecycleState.ACTIVE:
                continue
            if obj.follow_entity_id is None:
                continue
            follower = space_runtime.get_entity(obj.follow_entity_id)
            if follower is None:
                msg = f"内容创建对象跟随实体不存在：{obj.follow_entity_id}"
                raise ValueError(msg)
            if follower.position != obj.entity.position:
                obj.entity = replace(obj.entity, position=follower.position)

    def _behavior_for(self, behavior_key: str) -> CreatedObjectBehavior:
        behavior = self._behaviors.get(behavior_key)
        if behavior is None:
            msg = f"未注册内容创建对象行为：{behavior_key}"
            raise KeyError(msg)
        return behavior

    def _objects_for_spec(
        self,
        spec: CreatedObjectSpec,
        frame: int,
    ) -> tuple[CreatedObjectRuntimeState, ...]:
        return tuple(
            obj
            for obj in self._objects
            if obj.object_key == spec.object_key
            and obj.entity.owner_key == spec.owner_key
            and obj.is_active_at(frame)
        )

    def _active_object_for(
        self,
        object_key: str,
        owner_key: str | None,
        frame: int,
    ) -> CreatedObjectRuntimeState | None:
        for obj in self._objects:
            if obj.object_key != object_key:
                continue
            if owner_key is not None and obj.entity.owner_key != owner_key:
                continue
            if obj.is_active_at(frame):
                return obj
        return None

    def _expire_due_objects(self, frame: int) -> None:
        for obj in self._objects:
            _expire_if_due(obj, frame)

    def _next_entity_id(self, object_key: str) -> str:
        entity_id = f"created_object:{object_key}:{self._next_entity_index}"
        self._next_entity_index += 1
        return entity_id


def _initial_tick_frame(spec: CreatedObjectSpec, frame: int) -> int | None:
    if spec.first_tick_frame_offset is not None:
        return frame + spec.first_tick_frame_offset
    if spec.tick_interval_frames is not None:
        return frame + spec.tick_interval_frames
    return None


def _expire_if_due(obj: CreatedObjectRuntimeState, frame: int) -> bool:
    expires_at_frame = obj.entity.lifecycle.expires_at_frame
    if expires_at_frame is not None and frame >= expires_at_frame:
        obj.expire()
        return True
    return False


def _validate_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        msg = f"{field_name}必须是非空字符串"
        raise ValueError(msg)


def _validate_frame(frame: int) -> None:
    if frame < 0:
        msg = "帧号不能为负数"
        raise ValueError(msg)


def _validate_positive_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        msg = f"{field_name}必须是正整数"
        raise ValueError(msg)


def _validate_non_negative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        msg = f"{field_name}必须是非负整数"
        raise ValueError(msg)
