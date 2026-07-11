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
    tick_interval_frames: int | None = None
    first_tick_frame_offset: int | None = None
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
        if self.tick_interval_frames is not None and self.tick_interval_frames <= 0:
            msg = "内容创建对象 tick 间隔必须是正整数"
            raise ValueError(msg)
        if self.first_tick_frame_offset is not None and self.first_tick_frame_offset < 0:
            msg = "内容创建对象首次 tick 偏移不能为负数"
            raise ValueError(msg)
        if self.max_instances <= 0:
            msg = "内容创建对象数量上限必须是正整数"
            raise ValueError(msg)
        for tag in self.tags:
            _validate_non_empty_text(tag, "内容创建对象标签")
        object.__setattr__(self, "tags", tuple(self.tags))
        object.__setattr__(self, "params", dict(self.params))


@dataclass(slots=True)
class CreatedObjectRuntimeState:
    """内容创建场上对象的运行态。"""

    entity: SpatialEntity
    object_key: str
    behavior_key: str | None = None
    next_tick_frame: int | None = None
    tick_interval_frames: int | None = None
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
        self.params = dict(self.params)

    def is_active_at(self, frame: int) -> bool:
        return self.entity.is_active_at(frame)

    def expire(self) -> None:
        self.entity.lifecycle.expire()
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

    def register(self, behavior_key: str, behavior: CreatedObjectBehavior) -> None:
        _validate_non_empty_text(behavior_key, "内容创建对象行为 key")
        self._behaviors[behavior_key] = behavior

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
        del context
        _validate_frame(frame)
        self._current_frame = frame
        self._pending_impact_requests.clear()

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
            behavior_key=spec.behavior_key or spec.object_key,
            next_tick_frame=_initial_tick_frame(spec, frame),
            tick_interval_frames=spec.tick_interval_frames,
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
        obj.behavior_key = spec.behavior_key or spec.object_key
        obj.next_tick_frame = _initial_tick_frame(spec, frame)
        obj.tick_interval_frames = spec.tick_interval_frames
        obj.params = dict(spec.params)
        return obj

    def _tick_object(self, obj: CreatedObjectRuntimeState, frame: int) -> None:
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
