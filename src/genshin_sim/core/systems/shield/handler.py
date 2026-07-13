"""ImpactRequest 到类型化护盾请求，以及角色来伤应用处理器。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from genshin_sim.core.attributes import (
    AttributeSubjectRef,
    RuntimeSourceKind,
    RuntimeSourceRef,
    attribute_key,
)
from genshin_sim.core.systems.shield.enums import (
    ShieldElement,
    ShieldGrantPolicy,
    ShieldProtectionKind,
)
from genshin_sim.core.systems.shield.errors import (
    ShieldProtectionNotFoundError,
    ShieldValidationError,
)
from genshin_sim.core.systems.shield.formulas import (
    ShieldCapacityFormula,
    ShieldNativeMultiplierTerm,
    ShieldScalingTerm,
)
from genshin_sim.core.systems.shield.models import (
    CharacterIncomingDamage,
    IncomingDamageApplicationRecord,
    ShieldGrantRequest,
    ShieldGrantResult,
    ShieldProtectionRef,
)
from genshin_sim.core.systems.shield.runtime import ShieldRuntime

if TYPE_CHECKING:
    from genshin_sim.core.impacts import ImpactRequest


@dataclass(frozen=True, slots=True)
class ShieldGrantRecord:
    frame: int
    impact_request: ImpactRequest
    grant_request: ShieldGrantRequest
    result: ShieldGrantResult


class ShieldImpactRequestHandler:
    """把 params.shield 一次性转换为 ShieldGrantRequest。"""

    def __init__(self, runtime: ShieldRuntime) -> None:
        self.runtime = runtime
        self._records: list[ShieldGrantRecord] = []

    @property
    def records(self) -> tuple[ShieldGrantRecord, ...]:
        return tuple(self._records)

    @staticmethod
    def has_shield_contract(request: ImpactRequest) -> bool:
        return isinstance(request.params.get("shield"), Mapping)

    def handle_impact_request(self, context, request: ImpactRequest) -> ShieldGrantResult:
        payload = request.params.get("shield")
        if not isinstance(payload, Mapping):
            raise ShieldValidationError("护盾 ImpactRequest 缺少 params.shield 对象")
        grant_request = self._adapt(context, request, payload)
        result = self.runtime.grant(grant_request)
        self._records.append(
            ShieldGrantRecord(
                frame=request.frame,
                impact_request=request,
                grant_request=grant_request,
                result=result,
            )
        )
        return result

    def _adapt(
        self,
        context,
        request: ImpactRequest,
        payload: Mapping[str, object],
    ) -> ShieldGrantRequest:
        if context.space_runtime is None:
            raise ShieldProtectionNotFoundError("缺少 SpaceRuntime，无法解析护盾创建者")
        if request.owner_slot is None:
            raise ShieldProtectionNotFoundError("护盾请求缺少 owner_slot")
        creator = context.space_runtime.team_state.get_character(request.owner_slot)
        if creator is None:
            raise ShieldProtectionNotFoundError(f"护盾创建者槽位不存在：{request.owner_slot}")
        source_context = RuntimeSourceRef(
            RuntimeSourceKind.ACTION,
            request.action_key or request.impact_key,
            request.request_id or request.source_impact_point_id,
        )
        protection_ref = _protection_ref(payload.get("protection_ref"))
        element_value = request.element or payload.get("element", ShieldElement.NONE.value)
        if not isinstance(element_value, str):
            raise ShieldValidationError("shield.element 必须是字符串")
        try:
            element = ShieldElement(element_value)
        except ValueError as exc:
            raise ShieldValidationError(f"不支持的护盾元素：{element_value}") from exc
        grant_policy_value = payload.get("grant_policy", ShieldGrantPolicy.REPLACE.value)
        if not isinstance(grant_policy_value, str):
            raise ShieldValidationError("shield.grant_policy 必须是字符串")
        try:
            grant_policy = ShieldGrantPolicy(grant_policy_value)
        except ValueError as exc:
            raise ShieldValidationError(f"不支持的护盾 grant policy：{grant_policy_value}") from exc
        capacity_limit_payload = payload.get("capacity_limit_formula")
        capacity_limit_formula = None
        if capacity_limit_payload is not None:
            capacity_limit_formula = _formula(capacity_limit_payload, source_context)
        payload_tags = _string_sequence(payload.get("tags", ()), "shield.tags")
        return ShieldGrantRequest(
            grant_id=request.request_id
            or f"shield:{request.source_impact_point_id or request.impact_key}:{request.frame}",
            frame=request.frame,
            mechanic_key=_required_text(payload, "mechanic_key"),
            handler_key=_required_text(payload, "handler_key"),
            protection_ref=protection_ref,
            creator_ref=AttributeSubjectRef.character(creator.combat_entity_id),
            source_context=source_context,
            element=element,
            duration_frames=_positive_int(payload.get("duration_frames"), "duration_frames"),
            grant_formula=_formula(payload.get("grant_formula"), source_context),
            capacity_limit_formula=capacity_limit_formula,
            grant_policy=grant_policy,
            conflict_key=_required_text(payload, "conflict_key"),
            grants_interruption_resistance=_boolean(
                payload.get("grants_interruption_resistance", False),
                "grants_interruption_resistance",
            ),
            tags=frozenset((*request.tags, *payload_tags)),
        )


class IncomingDamageHandler:
    """角色来伤到护盾和生命提交的显式编排入口。"""

    def __init__(self, runtime: ShieldRuntime) -> None:
        self.runtime = runtime
        self._records: list[IncomingDamageApplicationRecord] = []

    @property
    def records(self) -> tuple[IncomingDamageApplicationRecord, ...]:
        return tuple(self._records)

    def apply(self, request: CharacterIncomingDamage) -> IncomingDamageApplicationRecord:
        record = self.runtime.apply_incoming_damage(request)
        self._records.append(record)
        return record


def _protection_ref(value: object) -> ShieldProtectionRef:
    if value is None:
        return ShieldProtectionRef.active_team()
    if not isinstance(value, Mapping):
        raise ShieldValidationError("shield.protection_ref 必须是对象")
    kind_value = value.get("kind", ShieldProtectionKind.ACTIVE_TEAM.value)
    protection_id = value.get("protection_id", "team:player")
    if not isinstance(kind_value, str) or not isinstance(protection_id, str):
        raise ShieldValidationError("shield.protection_ref 字段必须是字符串")
    try:
        kind = ShieldProtectionKind(kind_value)
    except ValueError as exc:
        raise ShieldValidationError(f"不支持的 protection kind：{kind_value}") from exc
    return ShieldProtectionRef(kind, protection_id)


def _formula(value: object, source_context: RuntimeSourceRef) -> ShieldCapacityFormula:
    if not isinstance(value, Mapping):
        raise ShieldValidationError("shield formula 必须是对象")
    scaling_terms_value = value.get("scaling_terms", ())
    if not isinstance(scaling_terms_value, Sequence) or isinstance(
        scaling_terms_value,
        str | bytes,
    ):
        raise ShieldValidationError("shield formula scaling_terms 必须是数组")
    scaling_terms = []
    for index, item in enumerate(scaling_terms_value):
        if not isinstance(item, Mapping):
            raise ShieldValidationError(f"scaling_terms[{index}] 必须是对象")
        attribute_key_value = item.get("attribute_key")
        if not isinstance(attribute_key_value, str):
            raise ShieldValidationError(f"scaling_terms[{index}].attribute_key 必须是字符串")
        scaling_terms.append(
            ShieldScalingTerm(
                component_key=_required_text(item, "component_key"),
                attribute_key=attribute_key(attribute_key_value),
                coefficient=_number(item.get("coefficient"), "coefficient"),
            )
        )
    multipliers_value = value.get("native_multipliers", ())
    if not isinstance(multipliers_value, Sequence) or isinstance(
        multipliers_value,
        str | bytes,
    ):
        raise ShieldValidationError("shield formula native_multipliers 必须是数组")
    multipliers = []
    for index, item in enumerate(multipliers_value):
        if not isinstance(item, Mapping):
            raise ShieldValidationError(f"native_multipliers[{index}] 必须是对象")
        multipliers.append(
            ShieldNativeMultiplierTerm(
                multiplier_key=_required_text(item, "multiplier_key"),
                multiplier=_number(item.get("multiplier"), "multiplier"),
                source_context=source_context,
            )
        )
    return ShieldCapacityFormula(
        scaling_terms=tuple(scaling_terms),
        flat_absorption=_number(value.get("flat_absorption", 0.0), "flat_absorption"),
        native_multipliers=tuple(multipliers),
    )


def _required_text(payload: Mapping[str, object], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ShieldValidationError(f"shield.{field_name} 必须是非空字符串")
    return value


def _number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ShieldValidationError(f"shield.{field_name} 必须是数字")
    return float(value)


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ShieldValidationError(f"shield.{field_name} 必须是正整数")
    return value


def _boolean(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ShieldValidationError(f"shield.{field_name} 必须是布尔值")
    return value


def _string_sequence(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise ShieldValidationError(f"{field_name} 必须是字符串数组")
    result = tuple(value)
    if any(not isinstance(item, str) or not item.strip() for item in result):
        raise ShieldValidationError(f"{field_name} 必须是非空字符串数组")
    return result
