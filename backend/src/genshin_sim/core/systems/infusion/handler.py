"""APPLY_INFUSION Impact 适配与 Damage 结算帧最终元素适配。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from genshin_sim.core.attributes import (
    AttributeSubjectKind,
    AttributeSubjectRef,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.elements import AuraAmount, Element
from genshin_sim.core.systems.aura import AuraStrength
from genshin_sim.core.systems.infusion.errors import (
    InfusionImpactContractError,
    UnsupportedWeaponAuraRuleError,
)
from genshin_sim.core.systems.infusion.models import (
    ApplyInfusionRequest,
    EffectiveElementResolution,
    InfusionApplicationResult,
)
from genshin_sim.core.systems.infusion.protocols import EffectiveElementReader
from genshin_sim.core.systems.infusion.runtime import InfusionRuntime

if TYPE_CHECKING:
    from genshin_sim.core.impacts.models import DamageImpactSpec, ImpactRequest


@dataclass(frozen=True, slots=True)
class InfusionImpactRecord:
    """一次 APPLY_INFUSION Impact 展开出的附魔应用记录。"""

    frame: int
    impact_request: ImpactRequest
    infusion_requests: tuple[ApplyInfusionRequest, ...]
    results: tuple[InfusionApplicationResult, ...]


class InfusionImpactRequestHandler:
    """把 params.infusion 一次性转换为 ApplyInfusionRequest 批次。"""

    def __init__(self, runtime: InfusionRuntime) -> None:
        self.runtime = runtime
        self._records: list[InfusionImpactRecord] = []

    @property
    def records(self) -> tuple[InfusionImpactRecord, ...]:
        return tuple(self._records)

    @staticmethod
    def has_infusion_contract(request: ImpactRequest) -> bool:
        return isinstance(request.params.get("infusion"), Mapping)

    def handle_impact_request(
        self,
        context,
        request: ImpactRequest,
    ) -> tuple[InfusionApplicationResult, ...]:
        payload = request.params.get("infusion")
        if not isinstance(payload, Mapping):
            raise InfusionImpactContractError(
                "APPLY_INFUSION ImpactRequest 缺少 params.infusion 对象"
            )
        infusion_requests = self._adapt(context, request, payload)
        results = self.runtime.apply_many(infusion_requests)
        self._records.append(
            InfusionImpactRecord(
                frame=request.frame,
                impact_request=request,
                infusion_requests=infusion_requests,
                results=results,
            )
        )
        return results

    def _adapt(
        self,
        context,
        request: ImpactRequest,
        payload: Mapping[str, object],
    ) -> tuple[ApplyInfusionRequest, ...]:
        _reject_unknown_fields(payload, allowed={"definition_key", "applier_ref"})
        if not request.target_refs:
            raise InfusionImpactContractError("APPLY_INFUSION ImpactRequest target_refs 不能为空")
        definition_key = _required_text(payload, "definition_key")
        definition = self.runtime.definition_registry.get(definition_key)
        applier_ref = _optional_subject_ref(payload.get("applier_ref"), "applier_ref")
        source_occurrence_id = request.source_impact_point_id or request.request_id
        if source_occurrence_id is None:
            raise InfusionImpactContractError(
                "APPLY_INFUSION ImpactRequest 必须提供 source_impact_point_id 或 request_id"
            )
        character_refs = tuple(
            _character_ref_from_target(context, value) for value in request.target_refs
        )
        if len(character_refs) != len(set(character_refs)):
            raise InfusionImpactContractError("APPLY_INFUSION ImpactRequest target_refs 不能重复")
        source_context = RuntimeSourceRef(
            RuntimeSourceKind.MECHANIC,
            definition.mechanic_key,
            None if request.owner_slot is None else f"slot:{request.owner_slot}",
        )
        requests = []
        for order, character_ref in enumerate(character_refs):
            requests.append(
                ApplyInfusionRequest(
                    request_id=_infusion_impact_request_id(
                        source_occurrence_id=source_occurrence_id,
                        impact_request_id=request.request_id,
                        definition_key=definition_key,
                        character_ref=character_ref,
                        order=order,
                    ),
                    frame=request.frame,
                    order=order,
                    definition_key=definition_key,
                    character_ref=character_ref,
                    source_context=source_context,
                    applier_ref=applier_ref,
                )
            )
        return tuple(requests)


@dataclass(frozen=True, slots=True)
class InfusionElementResolutionRecord:
    """一次 Damage 结算帧附魔解析的审计记录。"""

    frame: int
    impact_key: str
    request_id: str | None
    attack_tag: str
    base_element: Element
    resolution: EffectiveElementResolution
    applied: bool


class InfusionDamageElementAdapter:
    """在 Damage Impact 结算帧解析并替换最终元素。"""

    def __init__(self, reader: EffectiveElementReader) -> None:
        self._reader = reader
        self._records: list[InfusionElementResolutionRecord] = []

    @property
    def records(self) -> tuple[InfusionElementResolutionRecord, ...]:
        return tuple(self._records)

    def apply(
        self,
        frame: int,
        character_ref: AttributeSubjectRef,
        spec: DamageImpactSpec,
        *,
        impact_key: str,
        request_id: str | None,
    ) -> tuple[DamageImpactSpec, InfusionElementResolutionRecord]:
        resolution = self._reader.resolve_effective_element(
            frame,
            character_ref,
            spec.element,
            attack_tag=spec.main_attack_tag,
        )
        applied = resolution.mode is not None
        record = InfusionElementResolutionRecord(
            frame=frame,
            impact_key=impact_key,
            request_id=request_id,
            attack_tag=spec.main_attack_tag,
            base_element=spec.element,
            resolution=resolution,
            applied=applied,
        )
        if not applied:
            self._records.append(record)
            return spec, record
        if spec.elemental_amount.is_zero:
            gauge = resolution.weapon_gauge
            if gauge is None:
                raise InfusionImpactContractError("生效附魔/转化缺少 weapon_gauge")
            spec = replace(
                spec,
                element=resolution.element,
                elemental_strength=_strength_for_weapon_gauge(gauge),
                elemental_amount=gauge,
            )
        else:
            spec = replace(spec, element=resolution.element)
        self._records.append(record)
        return spec, record


def _reject_unknown_fields(payload: Mapping[str, object], *, allowed: set[str]) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise InfusionImpactContractError(f"infusion.{unknown[0]} 不是受支持字段")


def _required_text(payload: Mapping[str, object], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise InfusionImpactContractError(f"infusion.{field_name} 必须是非空字符串")
    return value


def _optional_subject_ref(value: object, field_name: str) -> AttributeSubjectRef | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise InfusionImpactContractError(f"infusion.{field_name} 必须是对象或 null")
    _reject_unknown_fields(value, allowed={"kind", "entity_id"})
    kind_value = value.get("kind")
    entity_id = value.get("entity_id")
    if not isinstance(kind_value, str) or not isinstance(entity_id, str):
        raise InfusionImpactContractError(f"infusion.{field_name}.kind 和 entity_id 必须是字符串")
    if kind_value != AttributeSubjectKind.CHARACTER.value:
        raise InfusionImpactContractError(
            f"infusion.{field_name}.kind 只支持 character：{kind_value}"
        )
    return AttributeSubjectRef.character(entity_id)


def _character_ref_from_target(context, value: str) -> AttributeSubjectRef:
    if not isinstance(value, str) or not value.strip():
        raise InfusionImpactContractError("APPLY_INFUSION target_ref 必须是非空字符串")
    if context.space_runtime is None:
        if value.startswith("character:"):
            return AttributeSubjectRef.character(value)
        raise InfusionImpactContractError(f"APPLY_INFUSION target_ref 不受支持：{value}")
    if value == "player:active":
        character = context.space_runtime.team_state.current_character
        return AttributeSubjectRef.character(character.combat_entity_id)
    if value.startswith("character:"):
        for character in context.space_runtime.team_state.characters:
            if character.combat_entity_id == value:
                return AttributeSubjectRef.character(character.combat_entity_id)
        raise InfusionImpactContractError(f"APPLY_INFUSION 角色目标不存在：{value}")
    raise InfusionImpactContractError(f"APPLY_INFUSION target_ref 不受支持：{value}")


def _strength_for_weapon_gauge(gauge: AuraAmount) -> AuraStrength:
    if gauge == AuraAmount(1):
        return AuraStrength.WEAK
    if gauge == AuraAmount("3/2"):
        return AuraStrength.MEDIUM
    if gauge == AuraAmount(2):
        return AuraStrength.STRONG
    if gauge == AuraAmount(4):
        return AuraStrength.SUPER_STRONG
    raise UnsupportedWeaponAuraRuleError(f"不支持的武器挂载量到附着强度映射：{gauge}")


def _infusion_impact_request_id(
    *,
    source_occurrence_id: str,
    impact_request_id: str | None,
    definition_key: str,
    character_ref: AttributeSubjectRef,
    order: int,
) -> str:
    request_component = impact_request_id or ""
    return (
        "infusion-impact"
        f":{len(source_occurrence_id)}:{source_occurrence_id}"
        f":{len(request_component)}:{request_component}"
        f":{len(definition_key)}:{definition_key}"
        f":{len(character_ref.kind.value)}:{character_ref.kind.value}"
        f":{len(character_ref.entity_id)}:{character_ref.entity_id}"
        f":{order}"
    )
