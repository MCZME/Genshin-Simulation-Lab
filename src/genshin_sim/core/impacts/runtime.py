from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from genshin_sim.core.actions.manager import ActionImpactPoint, ActionManager
from genshin_sim.core.impacts.dispatcher import ImpactDispatcher
from genshin_sim.core.impacts.models import ImpactKind, ImpactRequest
from genshin_sim.core.protocols import FrameUpdatable
from genshin_sim.core.space import CreatedObjectSpec, Vector3

if TYPE_CHECKING:
    from genshin_sim.core.simulation import SimulationContext


@dataclass(frozen=True, slots=True)
class ImpactDispatchRecord:
    """动作影响点展开出的机制请求记录。"""

    frame: int
    action_key: str
    impact_key: str
    requests: tuple[ImpactRequest, ...]


@dataclass(frozen=True, slots=True)
class CreatedObjectRecord:
    """由 create_entity 请求创建或刷新的内容对象记录。"""

    frame: int
    request: ImpactRequest
    object_key: str
    entity_id: str


@dataclass(frozen=True, slots=True)
class IgnoredImpactRecord:
    """暂未接入机制处理的影响请求记录。"""

    frame: int
    request: ImpactRequest
    reason: str


class ImpactRuntime(FrameUpdatable):
    """把动作影响点展开为机制请求，并处理创建空间实体的最小运行时。"""

    def __init__(
        self,
        action_manager: ActionManager,
        dispatcher: ImpactDispatcher,
    ) -> None:
        self.action_manager = action_manager
        self.dispatcher = dispatcher
        self._current_frame = 0
        self._processed_impact_points: set[tuple[int, int, str]] = set()
        self._dispatch_records: list[ImpactDispatchRecord] = []
        self._created_object_records: list[CreatedObjectRecord] = []
        self._ignored_requests: list[IgnoredImpactRecord] = []

    @property
    def dispatch_records(self) -> tuple[ImpactDispatchRecord, ...]:
        return tuple(self._dispatch_records)

    @property
    def created_object_records(self) -> tuple[CreatedObjectRecord, ...]:
        return tuple(self._created_object_records)

    @property
    def ignored_requests(self) -> tuple[IgnoredImpactRecord, ...]:
        return tuple(self._ignored_requests)

    def update_frame(self, context: SimulationContext, frame: int) -> None:
        if frame < 0:
            msg = "帧号不能为负数"
            raise ValueError(msg)

        self._current_frame = frame
        self._dispatch_due_action_impacts(context, frame)
        if context.space_runtime is None:
            return
        created_object_runtime = context.space_runtime.created_object_runtime
        created_object_runtime.update_frame(context, frame)
        self._handle_requests(context, created_object_runtime.drain_impact_requests())
        self._sync_created_objects_to_space(context)

    def is_idle(self) -> bool:
        return True

    def _dispatch_due_action_impacts(self, context: SimulationContext, frame: int) -> None:
        for instance in self.action_manager.instances:
            for impact_point in instance.impact_points:
                if impact_point.frame > frame:
                    continue
                point_id = (instance.instance_id, impact_point.frame, impact_point.impact_key)
                if point_id in self._processed_impact_points:
                    continue
                self._processed_impact_points.add(point_id)

                if not self.dispatcher.has_factory(impact_point.impact_key):
                    continue

                seed = _request_from_action_impact_point(
                    impact_point,
                    owner_slot=instance.owner_slot,
                    action_key=instance.action_key,
                    source_impact_point_id=_source_impact_point_id(
                        instance.instance_id,
                        impact_point,
                    ),
                )
                requests = self.dispatcher.dispatch(seed)
                self._dispatch_records.append(
                    ImpactDispatchRecord(
                        frame=frame,
                        action_key=instance.action_key,
                        impact_key=impact_point.impact_key,
                        requests=requests,
                    )
                )
                self._handle_requests(context, requests)

    def _handle_requests(
        self,
        context: SimulationContext,
        requests: tuple[ImpactRequest, ...],
    ) -> None:
        for request in requests:
            if request.kind is ImpactKind.CREATE_ENTITY:
                self._handle_create_entity_request(context, request)
                continue
            self._ignored_requests.append(
                IgnoredImpactRecord(
                    frame=request.frame,
                    request=request,
                    reason="机制系统尚未接入该影响请求类型",
                )
            )

    def _handle_create_entity_request(
        self,
        context: SimulationContext,
        request: ImpactRequest,
    ) -> None:
        if context.space_runtime is None:
            self._ignored_requests.append(
                IgnoredImpactRecord(
                    frame=request.frame,
                    request=request,
                    reason="缺少 SpaceRuntime，无法创建空间实体",
                )
            )
            return

        spec = _created_object_spec_from_request(request)
        state = context.space_runtime.created_object_runtime.create_or_refresh(
            spec,
            request.frame,
        )
        self._created_object_records.append(
            CreatedObjectRecord(
                frame=request.frame,
                request=request,
                object_key=state.object_key,
                entity_id=state.entity.entity_id,
            )
        )
        context.space_runtime.sync_entity_to_space(state.entity)

    def _sync_created_objects_to_space(self, context: SimulationContext) -> None:
        if context.space_runtime is None:
            return
        context.space_runtime.sync_created_objects_to_space()


def _request_from_action_impact_point(
    impact_point: ActionImpactPoint,
    *,
    owner_slot: int,
    action_key: str,
    source_impact_point_id: str,
) -> ImpactRequest:
    return ImpactRequest(
        frame=impact_point.frame,
        kind=ImpactKind.ACTION,
        impact_key=impact_point.impact_key,
        owner_slot=owner_slot,
        action_key=action_key,
        source_impact_point_id=source_impact_point_id,
        target_refs=tuple(target.target_id for target in impact_point.candidate_targets),
        params={
            "candidate_entity_ids": tuple(impact_point.candidate_entity_ids),
            "candidate_targets": tuple(
                {
                    "spatial_entity_id": target.spatial_entity_id,
                    "target_id": target.target_id,
                }
                for target in impact_point.candidate_targets
            ),
        },
    )


def _source_impact_point_id(instance_id: int, impact_point: ActionImpactPoint) -> str:
    return f"action:{instance_id}:{impact_point.frame}:{impact_point.impact_key}"


def _created_object_spec_from_request(request: ImpactRequest) -> CreatedObjectSpec:
    params = dict(request.params)
    object_key = _required_text(params, "object_key")
    duration_frames = _required_positive_int(params, "duration_frames")
    position = _vector3_from_param(params.get("position"), "position")
    facing = _vector3_from_param(params.get("facing"), "facing", default=Vector3(0.0, 0.0, 1.0))
    behavior_key = _optional_text(params, "behavior_key")
    entity_id = _optional_text(params, "entity_id")
    owner_key = _optional_text(params, "owner_key") or _owner_key_from_request(request)
    source_key = _optional_text(params, "source_key") or request.action_key or request.impact_key
    tick_interval_frames = _optional_positive_int(params, "tick_interval_frames")
    first_tick_frame_offset = _optional_non_negative_int(params, "first_tick_frame_offset")
    max_instances = _optional_positive_int(params, "max_instances") or 1
    refresh_existing = _optional_bool(params, "refresh_existing", default=True)
    tags = _tuple_of_text(params.get("tags"), "tags")
    spec_params = _mapping_param(params.get("object_params"), "object_params")

    return CreatedObjectSpec(
        object_key=object_key,
        duration_frames=duration_frames,
        position=position,
        facing=facing,
        owner_key=owner_key,
        source_key=source_key,
        behavior_key=behavior_key,
        entity_id=entity_id,
        tick_interval_frames=tick_interval_frames,
        first_tick_frame_offset=first_tick_frame_offset,
        max_instances=max_instances,
        refresh_existing=refresh_existing,
        tags=tags,
        params=spec_params,
    )


def _owner_key_from_request(request: ImpactRequest) -> str | None:
    if request.owner_slot is None:
        return None
    return f"slot:{request.owner_slot}"


def _required_text(params: Mapping[str, object], field_name: str) -> str:
    value = params.get(field_name)
    if not isinstance(value, str) or not value.strip():
        msg = f"create_entity.params.{field_name} 必须是非空字符串"
        raise ValueError(msg)
    return value


def _optional_text(params: Mapping[str, object], field_name: str) -> str | None:
    value = params.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        msg = f"create_entity.params.{field_name} 必须是非空字符串"
        raise ValueError(msg)
    return value


def _required_positive_int(params: Mapping[str, object], field_name: str) -> int:
    value = params.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        msg = f"create_entity.params.{field_name} 必须是正整数"
        raise ValueError(msg)
    return value


def _optional_positive_int(params: Mapping[str, object], field_name: str) -> int | None:
    value = params.get(field_name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        msg = f"create_entity.params.{field_name} 必须是正整数"
        raise ValueError(msg)
    return value


def _optional_non_negative_int(params: Mapping[str, object], field_name: str) -> int | None:
    value = params.get(field_name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        msg = f"create_entity.params.{field_name} 必须是非负整数"
        raise ValueError(msg)
    return value


def _optional_bool(params: Mapping[str, object], field_name: str, *, default: bool) -> bool:
    value = params.get(field_name)
    if value is None:
        return default
    if not isinstance(value, bool):
        msg = f"create_entity.params.{field_name} 必须是布尔值"
        raise ValueError(msg)
    return value


def _vector3_from_param(
    value: object,
    field_name: str,
    *,
    default: Vector3 | None = None,
) -> Vector3:
    if value is None:
        if default is not None:
            return default
        return Vector3()
    if isinstance(value, Vector3):
        return value
    if not isinstance(value, Mapping):
        msg = f"create_entity.params.{field_name} 必须是坐标对象"
        raise ValueError(msg)
    return Vector3(
        x=_number_param(value, "x", field_name),
        y=_number_param(value, "y", field_name),
        z=_number_param(value, "z", field_name),
    )


def _number_param(params: Mapping[str, object], name: str, parent_name: str) -> float:
    value = params.get(name)
    if isinstance(value, bool) or not isinstance(value, int | float):
        msg = f"create_entity.params.{parent_name}.{name} 必须是数字"
        raise ValueError(msg)
    return float(value)


def _tuple_of_text(value: object, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, tuple | list):
        msg = f"create_entity.params.{field_name} 必须是字符串数组"
        raise ValueError(msg)
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            msg = f"create_entity.params.{field_name} 必须是字符串数组"
            raise ValueError(msg)
        result.append(item)
    return tuple(result)


def _mapping_param(value: object, field_name: str) -> Mapping[str, object]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        msg = f"create_entity.params.{field_name} 必须是对象"
        raise ValueError(msg)
    return dict(value)
