from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from genshin_sim.core.actions import (
    ActionImpactPoint,
    ActionManager,
    CandidateTargetRef,
    SnapshotPolicy,
)
from genshin_sim.core.impacts.dispatcher import ImpactDispatcher
from genshin_sim.core.impacts.models import ActionImpactContext, ImpactKind, ImpactRequest
from genshin_sim.core.protocols import FrameUpdatable
from genshin_sim.core.space import CreatedObjectSpec, SpatialEntityKind, Vector3
from genshin_sim.core.systems.buff import BuffApplicationRecord, BuffImpactRequestHandler
from genshin_sim.core.systems.damage import DamageRequestHandler, DamageResolutionRecord
from genshin_sim.core.systems.energy import EnergyImpactRecord, EnergyImpactRequestHandler
from genshin_sim.core.systems.shield import ShieldGrantRecord, ShieldImpactRequestHandler


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


class ImpactRequestDispatcher:
    """按机制请求 kind 转交具体运行时系统。"""

    def __init__(
        self,
        damage_handler: DamageRequestHandler | None = None,
        shield_handler: ShieldImpactRequestHandler | None = None,
        buff_handler: BuffImpactRequestHandler | None = None,
        energy_handler: EnergyImpactRequestHandler | None = None,
    ) -> None:
        self.damage_handler = damage_handler
        self.shield_handler = shield_handler
        self.buff_handler = buff_handler
        self.energy_handler = energy_handler
        self._created_object_records: list[CreatedObjectRecord] = []
        self._ignored_requests: list[IgnoredImpactRecord] = []

    @property
    def created_object_records(self) -> tuple[CreatedObjectRecord, ...]:
        return tuple(self._created_object_records)

    @property
    def ignored_requests(self) -> tuple[IgnoredImpactRecord, ...]:
        return tuple(self._ignored_requests)

    @property
    def damage_records(self) -> tuple[DamageResolutionRecord, ...]:
        if self.damage_handler is None:
            return ()
        return self.damage_handler.records

    @property
    def shield_records(self) -> tuple[ShieldGrantRecord, ...]:
        if self.shield_handler is None:
            return ()
        return self.shield_handler.records

    @property
    def buff_records(self) -> tuple[BuffApplicationRecord, ...]:
        if self.buff_handler is None:
            return ()
        return self.buff_handler.records

    @property
    def energy_records(self) -> tuple[EnergyImpactRecord, ...]:
        if self.energy_handler is None:
            return ()
        return self.energy_handler.records

    def dispatch_requests(self, context, requests: tuple[ImpactRequest, ...]) -> None:
        for request in requests:
            if request.kind is ImpactKind.DAMAGE:
                self._handle_damage_request(context, request)
                continue
            if request.kind is ImpactKind.SHIELD:
                self._handle_shield_request(context, request)
                continue
            if request.kind is ImpactKind.APPLY_STATUS:
                self._handle_apply_status_request(context, request)
                continue
            if request.kind is ImpactKind.ENERGY:
                self._handle_energy_request(context, request)
                continue
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

    def _handle_damage_request(self, context, request: ImpactRequest) -> None:
        if self.damage_handler is None:
            self._ignored_requests.append(
                IgnoredImpactRecord(
                    frame=request.frame,
                    request=request,
                    reason="伤害请求处理器尚未接入",
                )
            )
            return
        if not self.damage_handler.has_damage_contract(request):
            self._ignored_requests.append(
                IgnoredImpactRecord(
                    frame=request.frame,
                    request=request,
                    reason="伤害请求缺少结构化 params.damage 契约",
                )
            )
            return
        if not request.target_refs:
            self._ignored_requests.append(
                IgnoredImpactRecord(
                    frame=request.frame,
                    request=request,
                    reason="伤害请求没有目标",
                )
            )
            return
        self.damage_handler.handle_impact_request(context, request)

    def _handle_shield_request(self, context, request: ImpactRequest) -> None:
        if self.shield_handler is None:
            self._ignored_requests.append(
                IgnoredImpactRecord(
                    frame=request.frame,
                    request=request,
                    reason="护盾请求处理器尚未接入",
                )
            )
            return
        if not self.shield_handler.has_shield_contract(request):
            self._ignored_requests.append(
                IgnoredImpactRecord(
                    frame=request.frame,
                    request=request,
                    reason="护盾请求缺少结构化 params.shield 契约",
                )
            )
            return
        self.shield_handler.handle_impact_request(context, request)

    def _handle_apply_status_request(self, context, request: ImpactRequest) -> None:
        if self.buff_handler is None:
            self._ignored_requests.append(
                IgnoredImpactRecord(
                    frame=request.frame,
                    request=request,
                    reason="状态效果请求处理器尚未接入",
                )
            )
            return
        self.buff_handler.handle_impact_request(context, request)

    def _handle_energy_request(self, context, request: ImpactRequest) -> None:
        if self.energy_handler is None:
            self._ignored_requests.append(
                IgnoredImpactRecord(request.frame, request, "元素能量请求处理器尚未接入")
            )
            return
        if not self.energy_handler.has_energy_contract(request):
            self._ignored_requests.append(
                IgnoredImpactRecord(
                    request.frame, request, "元素能量请求缺少结构化 params.energy 契约"
                )
            )
            return
        self.energy_handler.handle_impact_request(context, request)

    def _handle_create_entity_request(self, context, request: ImpactRequest) -> None:
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


class ImpactRuntime(FrameUpdatable):
    """把到期动作影响点展开为机制请求，并交给请求分发器。"""

    def __init__(
        self,
        action_manager: ActionManager,
        dispatcher: ImpactDispatcher,
        request_dispatcher: ImpactRequestDispatcher | None = None,
    ) -> None:
        self.action_manager = action_manager
        self.dispatcher = dispatcher
        self.request_dispatcher = request_dispatcher or ImpactRequestDispatcher()
        self._current_frame = 0
        self._dispatch_records: list[ImpactDispatchRecord] = []

    @property
    def dispatch_records(self) -> tuple[ImpactDispatchRecord, ...]:
        return tuple(self._dispatch_records)

    @property
    def created_object_records(self) -> tuple[CreatedObjectRecord, ...]:
        return self.request_dispatcher.created_object_records

    @property
    def ignored_requests(self) -> tuple[IgnoredImpactRecord, ...]:
        return self.request_dispatcher.ignored_requests

    @property
    def damage_records(self) -> tuple[DamageResolutionRecord, ...]:
        return self.request_dispatcher.damage_records

    @property
    def shield_records(self) -> tuple[ShieldGrantRecord, ...]:
        return self.request_dispatcher.shield_records

    @property
    def buff_records(self) -> tuple[BuffApplicationRecord, ...]:
        return self.request_dispatcher.buff_records

    @property
    def energy_records(self) -> tuple[EnergyImpactRecord, ...]:
        return self.request_dispatcher.energy_records

    def update_frame(self, context, frame: int) -> None:
        if frame < 0:
            msg = "帧号不能为负数"
            raise ValueError(msg)

        self._current_frame = frame
        self._dispatch_due_action_impacts(context, frame)
        if context.space_runtime is None:
            return
        created_object_runtime = context.space_runtime.created_object_runtime
        created_object_runtime.update_frame(context, frame)
        self.request_dispatcher.dispatch_requests(
            context,
            created_object_runtime.drain_impact_requests(),
        )
        context.space_runtime.sync_created_objects_to_space()

    def is_idle(self) -> bool:
        return True

    def _dispatch_due_action_impacts(self, context, frame: int) -> None:
        for impact_point in self.action_manager.due_impact_points(frame):
            if not self.dispatcher.has_factory(impact_point.impact_key):
                self.action_manager.mark_impact_dispatched(impact_point.impact_point_id)
                continue
            target_refs = self._resolve_target_refs(context, impact_point)
            impact_context = ActionImpactContext(
                frame=frame,
                impact_point_id=impact_point.impact_point_id,
                source_instance_id=impact_point.source_instance_id,
                owner=impact_point.owner,
                action_key=impact_point.action_key,
                impact_key=impact_point.impact_key,
                target_refs=target_refs,
                params=impact_point.params,
            )
            requests = self.dispatcher.dispatch(impact_context)
            self._dispatch_records.append(
                ImpactDispatchRecord(
                    frame=frame,
                    action_key=impact_point.action_key,
                    impact_key=impact_point.impact_key,
                    requests=requests,
                )
            )
            self.request_dispatcher.dispatch_requests(context, requests)
            self.action_manager.mark_impact_dispatched(impact_point.impact_point_id)

    def _resolve_target_refs(
        self,
        context,
        impact_point: ActionImpactPoint,
    ) -> tuple[CandidateTargetRef, ...]:
        targeting = impact_point.targeting
        if targeting is None or context.space_runtime is None:
            return ()
        if targeting.snapshot_policy is SnapshotPolicy.SNAPSHOT_ON_EMIT:
            return context.space_runtime.resolve_candidate_targets(targeting.snapshot_entity_ids)
        kinds = _spatial_entity_kinds(targeting.kinds)
        entities = context.space_runtime.entities_in_radius(
            targeting.origin,
            targeting.radius,
            kinds=kinds,
            exclude_entity_ids=targeting.exclude_entity_ids,
        )
        return context.space_runtime.resolve_candidate_targets(
            tuple(entity.entity_id for entity in entities)
        )


def _spatial_entity_kinds(kinds: tuple[str, ...]) -> set[SpatialEntityKind] | None:
    if not kinds:
        return None
    return {SpatialEntityKind(kind) for kind in kinds}


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
