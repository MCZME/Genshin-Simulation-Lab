from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Protocol

from genshin_sim.core.actions import (
    ActionImpactPoint,
    ActionManager,
    CandidateTargetRef,
    SnapshotPolicy,
)
from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.impacts.dispatcher import ImpactDispatcher
from genshin_sim.core.impacts.models import ActionImpactContext, ImpactKind, ImpactRequest
from genshin_sim.core.protocols import FrameUpdatable
from genshin_sim.core.space import (
    CircleArea,
    CreatedObjectSpec,
    CreatedObjectTickSpec,
    ImpactAreaSpec,
    SpatialEntity,
    SpatialEntityKind,
    Vector3,
)
from genshin_sim.core.systems.aura import (
    CharacterAuraImpactRecord,
    CharacterAuraImpactRequestHandler,
)
from genshin_sim.core.systems.buff import BuffApplicationRecord, BuffImpactRequestHandler
from genshin_sim.core.systems.damage import DamageRequestHandler, DamageResolutionRecord
from genshin_sim.core.systems.energy import EnergyImpactRecord, EnergyImpactRequestHandler
from genshin_sim.core.systems.healing import (
    HealingImpactRecord,
    HealingImpactRequestHandler,
)
from genshin_sim.core.systems.infusion.handler import (
    InfusionDamageElementAdapter,
    InfusionElementResolutionRecord,
    InfusionImpactRecord,
    InfusionImpactRequestHandler,
)
from genshin_sim.core.systems.movement import MovementImpactRequestHandler
from genshin_sim.core.systems.shield import ShieldGrantRecord, ShieldImpactRequestHandler


class ElementalSettlementPort(Protocol):
    """元素 settlement 协调器暴露给 ImpactRuntime 的窄入口。"""

    def settle_damage_impact(self, context, request: ImpactRequest) -> object:
        """结算一个携带元素施加的 Damage Impact。"""
        ...

    def settle_aura_impact(self, context, request: ImpactRequest) -> object:
        """结算一个不造成伤害的元素施加 Impact。"""
        ...


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
class CreatedObjectExtensionDispatchRecord:
    """由 extend_created_entity 请求完成的一次创建物延长记录。"""

    frame: int
    request: ImpactRequest
    object_key: str
    entity_id: str
    applied_frames: int
    remaining_cap_frames: int | None


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
        healing_handler: HealingImpactRequestHandler | None = None,
        character_aura_handler: CharacterAuraImpactRequestHandler | None = None,
        energy_handler: EnergyImpactRequestHandler | None = None,
        movement_handler: MovementImpactRequestHandler | None = None,
        infusion_handler: InfusionImpactRequestHandler | None = None,
        infusion_element_adapter: InfusionDamageElementAdapter | None = None,
        elemental_settlement_coordinator: ElementalSettlementPort | None = None,
    ) -> None:
        self.damage_handler = damage_handler
        self.shield_handler = shield_handler
        self.buff_handler = buff_handler
        self.healing_handler = healing_handler
        self.character_aura_handler = character_aura_handler
        self.energy_handler = energy_handler
        self.movement_handler = movement_handler
        self.infusion_handler = infusion_handler
        self.infusion_element_adapter = infusion_element_adapter
        self.elemental_settlement_coordinator = elemental_settlement_coordinator
        self._created_object_records: list[CreatedObjectRecord] = []
        self._created_object_extension_records: list[CreatedObjectExtensionDispatchRecord] = []
        self._ignored_requests: list[IgnoredImpactRecord] = []

    @property
    def created_object_records(self) -> tuple[CreatedObjectRecord, ...]:
        return tuple(self._created_object_records)

    @property
    def created_object_extension_records(
        self,
    ) -> tuple[CreatedObjectExtensionDispatchRecord, ...]:
        return tuple(self._created_object_extension_records)

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
    def healing_records(self) -> tuple[HealingImpactRecord, ...]:
        if self.healing_handler is None:
            return ()
        return self.healing_handler.records

    @property
    def character_aura_records(self) -> tuple[CharacterAuraImpactRecord, ...]:
        if self.character_aura_handler is None:
            return ()
        return self.character_aura_handler.records

    @property
    def energy_records(self) -> tuple[EnergyImpactRecord, ...]:
        if self.energy_handler is None:
            return ()
        return self.energy_handler.records

    @property
    def infusion_records(self) -> tuple[InfusionImpactRecord, ...]:
        if self.infusion_handler is None:
            return ()
        return self.infusion_handler.records

    @property
    def infusion_element_resolutions(self) -> tuple[InfusionElementResolutionRecord, ...]:
        if self.infusion_element_adapter is None:
            return ()
        return self.infusion_element_adapter.records

    def dispatch_requests(self, context, requests: tuple[ImpactRequest, ...]) -> None:
        for request in requests:
            if request.kind is ImpactKind.DAMAGE:
                self._handle_damage_request(context, request)
                continue
            if request.kind is ImpactKind.APPLY_INFUSION:
                self._handle_apply_infusion_request(context, request)
                continue
            if request.kind is ImpactKind.APPLY_AURA:
                self._handle_apply_aura_request(context, request)
                continue
            if request.kind is ImpactKind.SHIELD:
                self._handle_shield_request(context, request)
                continue
            if request.kind is ImpactKind.APPLY_STATUS:
                self._handle_apply_status_request(context, request)
                continue
            if request.kind is ImpactKind.HEAL:
                self._handle_heal_request(context, request)
                continue
            if request.kind is ImpactKind.ENERGY:
                self._handle_energy_request(context, request)
                continue
            if request.kind is ImpactKind.MOVEMENT:
                self._handle_movement_request(context, request)
                continue
            if request.kind is ImpactKind.CREATE_ENTITY:
                self._handle_create_entity_request(context, request)
                continue
            if request.kind is ImpactKind.EXTEND_CREATED_ENTITY:
                self._handle_extend_created_entity_request(context, request)
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
        if (
            self.infusion_element_adapter is not None
            and request.damage_spec is not None
            and request.owner_slot is not None
            and context.space_runtime is not None
        ):
            source = context.space_runtime.team_state.get_character(request.owner_slot)
            if source is not None:
                character_ref = AttributeSubjectRef.character(source.combat_entity_id)
                resolved_spec, _ = self.infusion_element_adapter.apply(
                    request.frame,
                    character_ref,
                    request.damage_spec,
                    impact_key=request.impact_key,
                    request_id=request.request_id,
                )
                request = replace(request, damage_spec=resolved_spec)
        if not request.target_refs:
            self._ignored_requests.append(
                IgnoredImpactRecord(
                    frame=request.frame,
                    request=request,
                    reason="伤害请求没有目标",
                )
            )
            return
        if (
            request.damage_spec is not None
            and (
                (
                    request.damage_spec.elemental_strength is not None
                    and not request.damage_spec.elemental_amount.is_zero
                )
                or request.damage_spec.strike_type is not None
                or request.damage_spec.icd_tag_key is not None
            )
            and self.elemental_settlement_coordinator is not None
        ):
            self.elemental_settlement_coordinator.settle_damage_impact(context, request)
            return
        self.damage_handler.handle_impact_request(context, request)

    def _handle_apply_infusion_request(self, context, request: ImpactRequest) -> None:
        if self.infusion_handler is None:
            self._ignored_requests.append(
                IgnoredImpactRecord(
                    frame=request.frame,
                    request=request,
                    reason="附魔请求处理器尚未接入",
                )
            )
            return
        if not self.infusion_handler.has_infusion_contract(request):
            self._ignored_requests.append(
                IgnoredImpactRecord(
                    frame=request.frame,
                    request=request,
                    reason="附魔请求缺少结构化 params.infusion 契约",
                )
            )
            return
        self.infusion_handler.handle_impact_request(context, request)

    def _handle_apply_aura_request(self, context, request: ImpactRequest) -> None:
        if request.elemental_application_spec is None:
            self._ignored_requests.append(
                IgnoredImpactRecord(
                    frame=request.frame,
                    request=request,
                    reason="元素施加请求缺少 ElementalApplicationSpec",
                )
            )
            return
        target_refs = tuple(request.target_refs)
        if not target_refs and request.anchor_entity_id is not None:
            target_refs = (request.anchor_entity_id,)
        if not target_refs:
            self._ignored_requests.append(
                IgnoredImpactRecord(
                    frame=request.frame,
                    request=request,
                    reason="元素施加请求没有目标",
                )
            )
            return
        character_refs = tuple(
            ref for ref in target_refs if ref == "player:active" or ref.startswith("character:")
        )
        entity_refs = tuple(ref for ref in target_refs if ref not in character_refs)
        if character_refs and self.character_aura_handler is None:
            self._ignored_requests.append(
                IgnoredImpactRecord(
                    frame=request.frame,
                    request=request,
                    reason="角色附着请求处理器尚未接入",
                )
            )
            return
        if entity_refs and self.elemental_settlement_coordinator is None:
            self._ignored_requests.append(
                IgnoredImpactRecord(
                    frame=request.frame,
                    request=request,
                    reason="元素施加结算协调器尚未接入",
                )
            )
            return
        if character_refs:
            assert self.character_aura_handler is not None
            self.character_aura_handler.handle_impact_request(
                context,
                replace(request, target_refs=character_refs),
            )
        if entity_refs:
            assert self.elemental_settlement_coordinator is not None
            self.elemental_settlement_coordinator.settle_aura_impact(
                context,
                replace(request, target_refs=entity_refs),
            )

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

    def _handle_heal_request(self, context, request: ImpactRequest) -> None:
        if self.healing_handler is None:
            self._ignored_requests.append(
                IgnoredImpactRecord(
                    frame=request.frame,
                    request=request,
                    reason="治疗请求处理器尚未接入",
                )
            )
            return
        if not self.healing_handler.has_heal_contract(request):
            self._ignored_requests.append(
                IgnoredImpactRecord(
                    frame=request.frame,
                    request=request,
                    reason="治疗请求缺少结构化 params.heal 契约",
                )
            )
            return
        self.healing_handler.handle_impact_request(context, request)

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

    def _handle_movement_request(self, context, request: ImpactRequest) -> None:
        if self.movement_handler is None:
            self._ignored_requests.append(
                IgnoredImpactRecord(
                    frame=request.frame,
                    request=request,
                    reason="位移请求处理器尚未接入",
                )
            )
            return
        if not self.movement_handler.has_movement_contract(request):
            self._ignored_requests.append(
                IgnoredImpactRecord(
                    frame=request.frame,
                    request=request,
                    reason="位移请求缺少结构化 params.movement 契约",
                )
            )
            return
        self.movement_handler.handle(context, request)

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

    def _handle_extend_created_entity_request(
        self,
        context,
        request: ImpactRequest,
    ) -> None:
        if context.space_runtime is None:
            self._ignored_requests.append(
                IgnoredImpactRecord(
                    frame=request.frame,
                    request=request,
                    reason="缺少 SpaceRuntime，无法延长空间实体",
                )
            )
            return

        params = dict(request.params)
        object_key = _required_text(params, "object_key")
        frames = _required_positive_int(params, "frames")
        max_extra_frames = _optional_positive_int(params, "max_extra_frames")
        owner_key = _optional_text(params, "owner_key") or _owner_key_from_request(request)
        runtime = context.space_runtime.created_object_runtime
        record = runtime.extend_duration(
            object_key=object_key,
            owner_key=owner_key,
            frames=frames,
            max_extra_frames=max_extra_frames,
            frame=request.frame,
        )
        if record is None:
            self._ignored_requests.append(
                IgnoredImpactRecord(
                    frame=request.frame,
                    request=request,
                    reason="未找到可延长的活动创建对象",
                )
            )
            return
        self._created_object_extension_records.append(
            CreatedObjectExtensionDispatchRecord(
                frame=request.frame,
                request=request,
                object_key=record.object_key,
                entity_id=record.entity_id,
                applied_frames=record.applied_frames,
                remaining_cap_frames=record.remaining_cap_frames,
            )
        )
        state = next(
            (obj for obj in runtime.objects if obj.entity.entity_id == record.entity_id),
            None,
        )
        if state is not None:
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

    @property
    def infusion_records(self) -> tuple[InfusionImpactRecord, ...]:
        return self.request_dispatcher.infusion_records

    @property
    def infusion_element_resolutions(self) -> tuple[InfusionElementResolutionRecord, ...]:
        return self.request_dispatcher.infusion_element_resolutions

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
        requests = self._expand_aura_areas(
            context,
            created_object_runtime.drain_impact_requests(),
        )
        self.request_dispatcher.dispatch_requests(context, requests)
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
            requests = self._expand_damage_areas(context, impact_point, requests)
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

    def _expand_aura_areas(
        self,
        context,
        requests: tuple[ImpactRequest, ...],
    ) -> tuple[ImpactRequest, ...]:
        """按 APPLY_AURA 的 AOE 在锚点处解析实际目标（角色与敌人）。"""

        if context.space_runtime is None:
            return requests
        expanded: list[ImpactRequest] = []
        for request in requests:
            spec = request.elemental_application_spec
            if request.kind is not ImpactKind.APPLY_AURA or spec is None or spec.area is None:
                expanded.append(request)
                continue
            if request.anchor_entity_id is not None:
                anchor = context.space_runtime.get_entity(request.anchor_entity_id)
                anchors: tuple[SpatialEntity, ...] = () if anchor is None else (anchor,)
            else:
                anchors = tuple(
                    anchor
                    for target_ref in request.target_refs
                    if (anchor := _spatial_anchor(context, target_ref)) is not None
                )
            target_refs: list[str] = []
            for anchor in anchors:
                area = _area_from_spec(spec.area, anchor)
                for entity in context.space_runtime.entities_in_area(
                    area,
                    kinds={
                        SpatialEntityKind.ACTIVE_CHARACTER,
                        SpatialEntityKind.TARGET,
                    },
                ):
                    ref = _aura_entity_ref(context, entity)
                    if ref is not None and ref not in target_refs:
                        target_refs.append(ref)
            if not target_refs:
                target_refs.extend(request.target_refs)
            expanded.append(replace(request, target_refs=tuple(target_refs)))
        return tuple(expanded)

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
        radius = (
            targeting.search_area.radius if targeting.search_area is not None else targeting.radius
        )
        entities = context.space_runtime.entities_in_radius(
            targeting.origin,
            radius,
            kinds=kinds,
            exclude_entity_ids=targeting.exclude_entity_ids,
        )
        if targeting.selection_policy_key == "分数":
            entities = _select_score_targets(entities, targeting.origin)
        return context.space_runtime.resolve_candidate_targets(
            tuple(entity.entity_id for entity in entities)
        )

    def _expand_damage_areas(
        self,
        context,
        impact_point: ActionImpactPoint,
        requests: tuple[ImpactRequest, ...],
    ) -> tuple[ImpactRequest, ...]:
        """按 Damage Impact 的 AOE 在选定锚点处解析实际受击目标。

        索敌阶段已经选择瞄准目标；带 ``area`` 的请求以该目标为锚点，用 AOE
        规格在 Space 中查询实际命中实体，再替换请求的目标集合。
        """

        if context.space_runtime is None:
            return requests
        targeting = impact_point.targeting
        kinds = _spatial_entity_kinds(targeting.kinds) if targeting is not None else None
        excluded = tuple(targeting.exclude_entity_ids) if targeting is not None else ()
        expanded: list[ImpactRequest] = []
        for request in requests:
            spec = request.damage_spec
            if request.kind is not ImpactKind.DAMAGE or spec is None or spec.area is None:
                expanded.append(request)
                continue
            target_refs: list[str] = []
            anchors: tuple[SpatialEntity, ...]
            fallback_refs: tuple[str, ...] = ()
            if request.anchor_entity_id is not None:
                anchor = context.space_runtime.get_entity(request.anchor_entity_id)
                anchors = () if anchor is None else (anchor,)
            else:
                anchor_list: list[SpatialEntity] = []
                fallback: list[str] = []
                for target_ref in request.target_refs:
                    anchor = _spatial_anchor(context, target_ref)
                    if anchor is None:
                        if target_ref not in fallback:
                            fallback.append(target_ref)
                        continue
                    anchor_list.append(anchor)
                anchors = tuple(anchor_list)
                fallback_refs = tuple(fallback)
            for anchor in anchors:
                area = _area_from_spec(spec.area, anchor)
                entities = context.space_runtime.entities_in_area(
                    area,
                    kinds=kinds,
                    exclude_entity_ids=excluded,
                )
                candidates = context.space_runtime.resolve_candidate_targets(
                    tuple(entity.entity_id for entity in entities)
                )
                for candidate in candidates:
                    if candidate.target_id not in target_refs:
                        target_refs.append(candidate.target_id)
            if not target_refs:
                target_refs.extend(fallback_refs)
            expanded.append(replace(request, target_refs=tuple(target_refs)))
        return tuple(expanded)


def _spatial_entity_kinds(kinds: tuple[str, ...]) -> set[SpatialEntityKind] | None:
    if not kinds:
        return None
    return {SpatialEntityKind(kind) for kind in kinds}


def _select_score_targets(
    entities: tuple[SpatialEntity, ...],
    origin: Vector3,
) -> tuple[SpatialEntity, ...]:
    """“分数”选择：按距锚点 X/Z 距离就近选择，并列取稳定实体 id 较小者。"""

    if not entities:
        return ()
    best = min(
        entities,
        key=lambda entity: (entity.position.distance_xz_to(origin), entity.entity_id),
    )
    return (best,)


def _spatial_anchor(context, target_ref: str) -> SpatialEntity | None:
    """把请求目标引用解析为空间实体（锚点）。"""

    targets = context.space_runtime.targets
    target = targets.get(target_ref) or targets.get_by_spatial_entity_id(target_ref)
    if target is None:
        return None
    return context.space_runtime.get_entity(target.spatial_entity_id)


def _aura_entity_ref(context, entity: SpatialEntity) -> str | None:
    """把 AOE 命中的空间实体转换为元素施加目标引用。"""

    if entity.kind is not SpatialEntityKind.TARGET:
        return entity.entity_id
    target = context.space_runtime.targets.get_by_spatial_entity_id(entity.entity_id)
    if target is None:
        return entity.entity_id
    return target.target_id


def _area_from_spec(spec: ImpactAreaSpec, anchor: SpatialEntity) -> CircleArea:
    """把未锚定的 AOE 规格投影到锚点位置（球/圆 -> 同半径 Circle）。"""

    offset = spec.local_offset_xz
    center = Vector3(
        anchor.position.x + offset.x,
        anchor.position.y + offset.y,
        anchor.position.z + offset.z,
    )
    if spec.shape not in {"球", "圆", "圆柱"}:
        raise ValueError(f"未支持的伤害 AOE 形状：{spec.shape}")
    return CircleArea(center=center, radius=spec.radius)


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
    tick_schedules = _optional_tick_schedules(params.get("tick_schedules"))
    follow_entity_id = _optional_text(params, "follow_entity_id")
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
        tick_schedules=tick_schedules,
        follow_entity_id=follow_entity_id,
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


def _optional_tick_schedules(value: object) -> tuple[CreatedObjectTickSpec, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        msg = "create_entity.params.tick_schedules 必须是序列"
        raise ValueError(msg)
    schedules: list[CreatedObjectTickSpec] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping):
            msg = f"create_entity.params.tick_schedules[{index}] 必须是映射"
            raise ValueError(msg)
        behavior_key = raw.get("behavior_key")
        first_tick_frame_offset = raw.get("first_tick_frame_offset", 0)
        interval_frames = raw.get("interval_frames")
        if not isinstance(behavior_key, str) or not behavior_key.strip():
            msg = f"create_entity.params.tick_schedules[{index}].behavior_key 必须是非空字符串"
            raise ValueError(msg)
        if (
            isinstance(first_tick_frame_offset, bool)
            or not isinstance(first_tick_frame_offset, int)
            or first_tick_frame_offset < 0
        ):
            msg = (
                f"create_entity.params.tick_schedules[{index}].first_tick_frame_offset "
                "必须是非负整数"
            )
            raise ValueError(msg)
        if interval_frames is not None and (
            isinstance(interval_frames, bool)
            or not isinstance(interval_frames, int)
            or interval_frames <= 0
        ):
            msg = (
                f"create_entity.params.tick_schedules[{index}].interval_frames 必须是正整数或 None"
            )
            raise ValueError(msg)
        schedules.append(
            CreatedObjectTickSpec(
                behavior_key=behavior_key,
                first_tick_frame_offset=first_tick_frame_offset,
                interval_frames=interval_frames,
            )
        )
    return tuple(schedules)


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
