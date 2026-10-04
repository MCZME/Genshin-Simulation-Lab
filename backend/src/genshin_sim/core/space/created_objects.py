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
    """内容创建场上实体的创建与刷新规格。

    机械字段（时长、位置、归属、标签等）由运行时基座消费；``config`` 是
    类型化配置的原始载体，由目标类型在 ``build_state`` 中解析校验。
    """

    type_key: str
    duration_frames: int
    position: Vector3 = field(default_factory=Vector3)
    facing: Vector3 = Vector3(0.0, 0.0, 1.0)
    owner_key: str | None = None
    source_key: str | None = None
    entity_id: str | None = None
    follow_entity_id: str | None = None
    max_instances: int = 1
    refresh_existing: bool = True
    tags: tuple[str, ...] = field(default_factory=tuple)
    config: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_non_empty_text(self.type_key, "内容创建实体类型 key")
        if self.duration_frames <= 0:
            msg = "内容创建实体持续帧数必须是正整数"
            raise ValueError(msg)
        if self.owner_key is not None:
            _validate_non_empty_text(self.owner_key, "内容创建实体归属 key")
        if self.source_key is not None:
            _validate_non_empty_text(self.source_key, "内容创建实体来源 key")
        if self.entity_id is not None:
            _validate_non_empty_text(self.entity_id, "内容创建实体 id")
        if self.follow_entity_id is not None:
            _validate_non_empty_text(self.follow_entity_id, "内容创建实体跟随实体 id")
        if self.max_instances <= 0:
            msg = "内容创建实体数量上限必须是正整数"
            raise ValueError(msg)
        for tag in self.tags:
            _validate_non_empty_text(tag, "内容创建实体标签")
        object.__setattr__(self, "tags", tuple(self.tags))
        object.__setattr__(self, "config", dict(self.config))


@dataclass(frozen=True, slots=True)
class CreatedObjectExtensionRecord:
    """一次创建物持续时间延长的提交记录。"""

    frame: int
    type_key: str
    entity_id: str
    requested_frames: int
    applied_frames: int
    remaining_cap_frames: int | None = None

    def __post_init__(self) -> None:
        _validate_frame(self.frame)
        _validate_non_empty_text(self.type_key, "创建实体类型 key")
        _validate_non_empty_text(self.entity_id, "创建实体实体 id")
        _validate_positive_int(self.requested_frames, "请求延长帧数")
        _validate_non_negative_int(self.applied_frames, "实际延长帧数")
        if self.applied_frames > self.requested_frames:
            msg = "创建物实际延长帧数不能超过请求帧数"
            raise ValueError(msg)
        if self.remaining_cap_frames is not None:
            _validate_non_negative_int(self.remaining_cap_frames, "剩余上限帧数")


@dataclass(frozen=True, slots=True)
class CreatedObjectTickAlignRecord:
    """一次创建物 tick 调度重锚的提交记录。

    重锚把全部 tick 调度按同一偏移平移（相位保持），使最早一拍落在目标帧；
    ``delta_frames`` 为正表示推迟、为负表示提前、为 0 表示本已对齐。
    """

    frame: int
    type_key: str
    entity_id: str
    earliest_tick_frame_before: int
    target_tick_frame: int
    delta_frames: int

    def __post_init__(self) -> None:
        _validate_frame(self.frame)
        _validate_non_empty_text(self.type_key, "创建实体类型 key")
        _validate_non_empty_text(self.entity_id, "创建实体实体 id")
        _validate_non_negative_int(self.earliest_tick_frame_before, "重锚前最早 tick 帧")
        _validate_non_negative_int(self.target_tick_frame, "重锚目标帧")
        if isinstance(self.delta_frames, bool) or not isinstance(self.delta_frames, int):
            msg = "重锚平移帧数必须是整数"
            raise ValueError(msg)


@dataclass(slots=True)
class CreatedObjectTickState:
    """创建物上一条 tick 调度的运行态。

    类型在 ``build_state`` 直接构建（``next_tick_frame`` 为绝对帧）并在
    ``on_tick`` 中自行推进下一拍（置 ``None`` 表示停机）；运行时基座负责
    到期驱动、过期门控与停摆守卫，节奏变更入口为创建/刷新与重锚。
    """

    schedule_key: str
    next_tick_frame: int | None

    def __post_init__(self) -> None:
        _validate_non_empty_text(self.schedule_key, "创建物 tick 调度 key")


class CreatedObjectRuntimeState:
    """内容创建场上实体的运行态基座。

    实体投影、调度存储、延长预算由运行时基座持有；类型子类（或直接使用
    基座）补充类型化实例配置。类型在 ``build_state`` 直接构建
    ``CreatedObjectTickState``（绝对帧）声明初始调度，在 ``on_tick`` 中自行
    推进下一拍（基于原定 tick 帧，置 ``None`` 停机）；重锚/延长与过期停机
    仍由运行时基座承载。
    """

    def __init__(
        self,
        *,
        entity: SpatialEntity,
        type_key: str,
        schedules: Sequence[CreatedObjectTickState] = (),
        follow_entity_id: str | None = None,
    ) -> None:
        if entity.kind is not SpatialEntityKind.CREATED_OBJECT:
            msg = "内容创建实体运行态必须组合 CREATED_OBJECT 空间实体"
            raise ValueError(msg)
        _validate_non_empty_text(type_key, "内容创建实体类型 key")
        if follow_entity_id is not None:
            _validate_non_empty_text(follow_entity_id, "内容创建实体跟随实体 id")
        schedules = tuple(schedules)
        for schedule in schedules:
            if not isinstance(schedule, CreatedObjectTickState):
                msg = "schedules 成员必须是 CreatedObjectTickState"
                raise ValueError(msg)
            if (
                schedule.next_tick_frame is not None
                and schedule.next_tick_frame < entity.lifecycle.created_frame
            ):
                msg = "创建物下一次 tick 帧不能早于创建帧"
                raise ValueError(msg)
        self.entity = entity
        self.type_key = type_key
        self.schedules: list[CreatedObjectTickState] = list(schedules)
        self.follow_entity_id = follow_entity_id
        self.extra_duration_frames = 0

    def is_active_at(self, frame: int) -> bool:
        return self.entity.is_active_at(frame)

    def expire(self) -> None:
        self.entity = replace(
            self.entity,
            lifecycle=self.entity.lifecycle.expired(),
        )
        for schedule in self.schedules:
            schedule.next_tick_frame = None


class CreatedEntityType(Protocol):
    """内容创建实体类型：类型化配置校验、运行态构建与 tick 产出的载体。

    类型在内容侧定义并注册（``type_key`` 全局唯一），创建请求只携带
    ``type_key`` 与类型化 ``config``；类型负责把 config 解析为运行态（含
    初始 tick 调度声明），并在到期帧按调度键产出影响请求。编译期依赖
    （倍率契约、槽位等）由类型实例在内容编译期持有。
    """

    type_key: str

    def build_state(
        self,
        config: Mapping[str, object],
        entity: SpatialEntity,
        frame: int,
        previous: CreatedObjectRuntimeState | None,
    ) -> CreatedObjectRuntimeState:
        """由类型化配置构建运行态（含初始调度声明）。

        ``previous`` 是刷新路径上被替换的同类型旧运行态（新建为 ``None``），
        类型据此实现"保留既有节奏"等继承语义。
        """
        ...

    def on_tick(
        self,
        state: CreatedObjectRuntimeState,
        schedule: CreatedObjectTickState,
        frame: int,
        context: SimulationContext,
    ) -> Sequence[ImpactRequest]:
        """为到期的调度产出影响请求，并自行推进该调度的下一拍。

        ``frame`` 为原定 tick 帧；推进应基于它计算（如固定周期为
        ``schedule.next_tick_frame = frame + 周期``），以保持追赶补发时按
        原定节奏落帧。置 ``schedule.next_tick_frame = None`` 表示停机；未
        前进到更晚帧由运行时确定性报错。
        """
        ...


class CreatedObjectRuntime(FrameUpdatable):
    """内容创建场上实体的生命周期、调度与类型注册运行时。

    职责切分：基座拥有"何时调用"——生命周期、调度存储与到期驱动、过期
    门控、追赶循环、延长与重锚；类型拥有"是什么与怎么再来"——配置解析、
    初始调度声明、请求产出与下一拍推进（``CreatedEntityType``）。
    """

    def __init__(self, types: Mapping[str, CreatedEntityType] | None = None) -> None:
        self._types: dict[str, CreatedEntityType] = {}
        self._objects: list[CreatedObjectRuntimeState] = []
        self._pending_impact_requests: list[ImpactRequest] = []
        self._emitted_impact_requests: list[ImpactRequest] = []
        self._extension_records: list[CreatedObjectExtensionRecord] = []
        self._tick_align_records: list[CreatedObjectTickAlignRecord] = []
        self._current_frame = 0
        self._next_entity_index = 1

        if types is not None:
            for type_key, type_impl in types.items():
                self.register(type_key, type_impl)

    @property
    def type_keys(self) -> tuple[str, ...]:
        return tuple(self._types)

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

    @property
    def tick_align_records(self) -> tuple[CreatedObjectTickAlignRecord, ...]:
        return tuple(self._tick_align_records)

    def register(self, type_key: str, type_impl: CreatedEntityType) -> None:
        _validate_non_empty_text(type_key, "内容创建实体类型 key")
        self._types[type_key] = type_impl

    def extend_duration(
        self,
        *,
        type_key: str,
        owner_key: str | None,
        frames: int,
        max_extra_frames: int | None = None,
        frame: int,
    ) -> CreatedObjectExtensionRecord | None:
        """延长活动创建实体的持续时间，并按实例记录已使用延长预算。

        ``max_extra_frames`` 表示该创建实体实例通过本入口累计可延长的上限；
        刷新（重放技能）会重置实例预算。没有活动匹配对象时返回 ``None``。
        """

        _validate_non_empty_text(type_key, "创建实体类型 key")
        if owner_key is not None:
            _validate_non_empty_text(owner_key, "创建实体归属 key")
        _validate_positive_int(frames, "请求延长帧数")
        if max_extra_frames is not None:
            _validate_positive_int(max_extra_frames, "延长上限帧数")
        _validate_frame(frame)
        obj = self._active_object_for(type_key, owner_key, frame)
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
            type_key=type_key,
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

    def align_tick_schedules(
        self,
        *,
        type_key: str,
        owner_key: str | None,
        target_frame: int,
        frame: int,
    ) -> CreatedObjectTickAlignRecord | None:
        """把活动创建实体的全部 tick 调度按同一偏移平移，使最早一拍落在目标帧。

        相位保持：各调度间的相对间隔不变，只整体提前或推迟（用于召唤物暂停
        后恢复攻击等场景，不重置持续时间、不重建对象）。没有活动匹配对象、
        或全部调度都没有下一 tick 帧时返回 ``None``；目标帧早于当前帧时拒绝。
        """

        _validate_non_empty_text(type_key, "创建实体类型 key")
        if owner_key is not None:
            _validate_non_empty_text(owner_key, "创建实体归属 key")
        _validate_frame(frame)
        _validate_frame(target_frame)
        if target_frame < frame:
            msg = "创建物 tick 重锚目标帧不能早于当前帧"
            raise ValueError(msg)
        obj = self._active_object_for(type_key, owner_key, frame)
        if obj is None:
            return None
        due_frames = [
            schedule.next_tick_frame
            for schedule in obj.schedules
            if schedule.next_tick_frame is not None
        ]
        if not due_frames:
            return None
        earliest = min(due_frames)
        delta = target_frame - earliest
        for schedule in obj.schedules:
            if schedule.next_tick_frame is not None:
                schedule.next_tick_frame += delta
        record = CreatedObjectTickAlignRecord(
            frame=frame,
            type_key=type_key,
            entity_id=obj.entity.entity_id,
            earliest_tick_frame_before=earliest,
            target_tick_frame=target_frame,
            delta_frames=delta,
        )
        self._tick_align_records.append(record)
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
            self._tick_object(obj, frame, context)

    def is_idle(self) -> bool:
        return all(
            obj.entity.lifecycle.state is not EntityLifecycleState.ACTIVE for obj in self._objects
        )

    def _create_object(self, spec: CreatedObjectSpec, frame: int) -> CreatedObjectRuntimeState:
        entity_id = spec.entity_id or self._next_entity_id(spec.type_key)
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
        state = self._type_for(spec.type_key).build_state(
            config=spec.config,
            entity=entity,
            frame=frame,
            previous=None,
        )
        if state.type_key != spec.type_key:
            msg = f"创建实体类型 {spec.type_key} 的 build_state 返回了 {state.type_key} 运行态"
            raise ValueError(msg)
        state.follow_entity_id = spec.follow_entity_id
        self._objects.append(state)
        return state

    def _refresh_object(
        self,
        obj: CreatedObjectRuntimeState,
        spec: CreatedObjectSpec,
        frame: int,
    ) -> CreatedObjectRuntimeState:
        entity = replace(
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
        state = self._type_for(spec.type_key).build_state(
            config=spec.config,
            entity=entity,
            frame=frame,
            previous=obj,
        )
        if state.type_key != spec.type_key:
            msg = f"创建实体类型 {spec.type_key} 的 build_state 返回了 {state.type_key} 运行态"
            raise ValueError(msg)
        state.follow_entity_id = spec.follow_entity_id
        state.extra_duration_frames = 0
        self._objects[self._objects.index(obj)] = state
        return state

    def _tick_object(
        self,
        obj: CreatedObjectRuntimeState,
        frame: int,
        context: SimulationContext,
    ) -> None:
        for schedule in tuple(obj.schedules):
            self._tick_schedule(obj, schedule, frame, context)

    def _tick_schedule(
        self,
        obj: CreatedObjectRuntimeState,
        schedule: CreatedObjectTickState,
        frame: int,
        context: SimulationContext,
    ) -> None:
        while schedule.next_tick_frame is not None and schedule.next_tick_frame <= frame:
            tick_frame = schedule.next_tick_frame
            expires_at_frame = obj.entity.lifecycle.expires_at_frame
            if expires_at_frame is not None and tick_frame >= expires_at_frame:
                schedule.next_tick_frame = None
                return

            type_impl = self._type_for(obj.type_key)
            requests = tuple(type_impl.on_tick(obj, schedule, tick_frame, context))
            self._pending_impact_requests.extend(requests)
            self._emitted_impact_requests.extend(requests)

            # 推进由类型决定：必须前进到更晚帧（含追赶中的原定帧），置 None
            # 停机；原地不动意味着节奏逻辑缺陷，确定性报错而非静默停摆。
            if schedule.next_tick_frame is not None and schedule.next_tick_frame <= tick_frame:
                msg = (
                    f"创建实体 {obj.type_key} 调度 {schedule.schedule_key} "
                    f"在 tick {tick_frame} 后未推进到更晚帧"
                )
                raise ValueError(msg)

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
                msg = f"内容创建实体跟随实体不存在：{obj.follow_entity_id}"
                raise ValueError(msg)
            if follower.position != obj.entity.position:
                obj.entity = replace(obj.entity, position=follower.position)

    def _type_for(self, type_key: str) -> CreatedEntityType:
        type_impl = self._types.get(type_key)
        if type_impl is None:
            msg = f"未注册内容创建实体类型：{type_key}"
            raise KeyError(msg)
        return type_impl

    def _objects_for_spec(
        self,
        spec: CreatedObjectSpec,
        frame: int,
    ) -> tuple[CreatedObjectRuntimeState, ...]:
        return tuple(
            obj
            for obj in self._objects
            if obj.type_key == spec.type_key
            and obj.entity.owner_key == spec.owner_key
            and obj.is_active_at(frame)
        )

    def _active_object_for(
        self,
        type_key: str,
        owner_key: str | None,
        frame: int,
    ) -> CreatedObjectRuntimeState | None:
        for obj in self._objects:
            if obj.type_key != type_key:
                continue
            if owner_key is not None and obj.entity.owner_key != owner_key:
                continue
            if obj.is_active_at(frame):
                return obj
        return None

    def _expire_due_objects(self, frame: int) -> None:
        for obj in self._objects:
            _expire_if_due(obj, frame)

    def _next_entity_id(self, type_key: str) -> str:
        entity_id = f"created_object:{type_key}:{self._next_entity_index}"
        self._next_entity_index += 1
        return entity_id


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
