"""ImpactRequest 到类型化 Buff 应用请求的适配器。"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from genshin_sim.core.attributes import (
    AttributeSubjectKind,
    AttributeSubjectRef,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.systems.buff.definitions import BuffDefinitionRegistry
from genshin_sim.core.systems.buff.errors import BuffImpactContractError
from genshin_sim.core.systems.buff.models import (
    ApplyBuffRequest,
    BuffApplicationResult,
    BuffInstanceRef,
    BuffModifierValue,
    BuffRemovalReason,
    BuffRemovalResult,
    RemoveBuffRequest,
)

if TYPE_CHECKING:
    from genshin_sim.core.impacts import ImpactRequest


class BuffApplyManyPort(Protocol):
    """Buff 批量应用入口的窄端口，由 `BuffRuntime` 与最大生命协调器满足。"""

    @property
    def definition_registry(self) -> BuffDefinitionRegistry: ...

    def apply_many(
        self,
        requests: Sequence[ApplyBuffRequest],
    ) -> tuple[BuffApplicationResult, ...]: ...


class BuffRemovePort(Protocol):
    """Buff 显式移除入口的窄端口，由 `BuffRuntime` 满足。"""

    def remove(self, request: RemoveBuffRequest) -> BuffRemovalResult: ...


@dataclass(frozen=True, slots=True)
class BuffApplicationRecord:
    frame: int
    impact_request: ImpactRequest
    buff_requests: tuple[ApplyBuffRequest, ...]
    results: tuple[BuffApplicationResult, ...]


@dataclass(frozen=True, slots=True)
class BuffRemovalRecord:
    frame: int
    impact_request: ImpactRequest
    removal_request: RemoveBuffRequest
    result: BuffRemovalResult


class BuffImpactRequestHandler:
    """把 params.buff 一次性转换为 ApplyBuffRequest 批次。"""

    def __init__(self, runtime: BuffApplyManyPort) -> None:
        self.runtime = runtime
        self._records: list[BuffApplicationRecord] = []

    @property
    def records(self) -> tuple[BuffApplicationRecord, ...]:
        return tuple(self._records)

    @staticmethod
    def has_buff_contract(request: ImpactRequest) -> bool:
        return isinstance(request.params.get("buff"), Mapping)

    def handle_impact_request(
        self,
        context,
        request: ImpactRequest,
    ) -> tuple[BuffApplicationResult, ...]:
        payload = request.params.get("buff")
        if not isinstance(payload, Mapping):
            raise BuffImpactContractError("APPLY_STATUS ImpactRequest 缺少 params.buff 对象")
        buff_requests = self._adapt(context, request, payload)
        results = self.runtime.apply_many(buff_requests)
        self._records.append(
            BuffApplicationRecord(
                frame=request.frame,
                impact_request=request,
                buff_requests=buff_requests,
                results=results,
            )
        )
        return results

    def _adapt(
        self,
        context,
        request: ImpactRequest,
        payload: Mapping[str, object],
    ) -> tuple[ApplyBuffRequest, ...]:
        _reject_unknown_fields(
            payload,
            allowed={
                "definition_key",
                "duration_frames",
                "stack_delta",
                "modifier_values",
                "applier_ref",
            },
        )
        if not request.target_refs:
            raise BuffImpactContractError("APPLY_STATUS ImpactRequest target_refs 不能为空")
        definition_key = _required_text(payload, "definition_key")
        definition = self.runtime.definition_registry.get(definition_key)
        duration_frames = _positive_int(payload.get("duration_frames"), "duration_frames")
        stack_delta = _positive_int(payload.get("stack_delta", 1), "stack_delta")
        modifier_values = _modifier_values(payload.get("modifier_values", ()))
        applier_ref = _optional_subject_ref(payload.get("applier_ref"), "applier_ref")
        source_occurrence_id = request.source_impact_point_id or request.request_id
        if source_occurrence_id is None:
            raise BuffImpactContractError(
                "APPLY_STATUS ImpactRequest 必须提供 source_impact_point_id 或 request_id"
            )
        target_refs = tuple(
            _subject_ref_from_target(context, value) for value in request.target_refs
        )
        if len(target_refs) != len(set(target_refs)):
            raise BuffImpactContractError("APPLY_STATUS ImpactRequest target_refs 不能重复")
        source_context = RuntimeSourceRef(
            RuntimeSourceKind.MECHANIC,
            definition.mechanic_key,
            None if request.owner_slot is None else f"slot:{request.owner_slot}",
        )
        requests = []
        for order, target_ref in enumerate(target_refs):
            requests.append(
                ApplyBuffRequest(
                    request_id=_buff_impact_request_id(
                        source_occurrence_id=source_occurrence_id,
                        impact_request_id=request.request_id,
                        definition_key=definition_key,
                        target_ref=target_ref,
                        order=order,
                    ),
                    frame=request.frame,
                    order=order,
                    definition_key=definition_key,
                    target_ref=target_ref,
                    source_context=source_context,
                    duration_frames=duration_frames,
                    stack_delta=stack_delta,
                    modifier_values=modifier_values,
                    applier_ref=applier_ref,
                )
            )
        return tuple(requests)


class BuffRemovalImpactRequestHandler:
    """把 REMOVE_STATUS ImpactRequest 转换为显式 Buff 移除请求。

    消费方（当前是角色的动作侧）先按主体读到活动记录，再把该记录的实例身份
    交给本入口；这里只做契约适配，不查询活动记录、不推断该移除哪一条。
    """

    def __init__(self, runtime: BuffRemovePort) -> None:
        self.runtime = runtime
        self._records: list[BuffRemovalRecord] = []

    @property
    def records(self) -> tuple[BuffRemovalRecord, ...]:
        return tuple(self._records)

    @staticmethod
    def has_removal_contract(request: ImpactRequest) -> bool:
        return isinstance(request.params.get("buff_remove"), Mapping)

    def handle_impact_request(
        self,
        context,
        request: ImpactRequest,
    ) -> BuffRemovalResult:
        del context
        payload = request.params.get("buff_remove")
        if not isinstance(payload, Mapping):
            msg = "REMOVE_STATUS ImpactRequest 缺少 params.buff_remove 对象"
            raise BuffImpactContractError(msg)
        _reject_unknown_fields(payload, allowed={"instance_ref", "reason"})
        instance_ref = _instance_ref(payload.get("instance_ref"))
        reason = _removal_reason(payload.get("reason"))
        removal_request = RemoveBuffRequest(
            request_id=_buff_removal_request_id(
                source_impact_point_id=request.source_impact_point_id,
                impact_request_id=request.request_id,
            ),
            frame=request.frame,
            instance_ref=instance_ref,
            reason=reason,
        )
        result = self.runtime.remove(removal_request)
        self._records.append(
            BuffRemovalRecord(
                frame=request.frame,
                impact_request=request,
                removal_request=removal_request,
                result=result,
            )
        )
        return result


def _instance_ref(value: object) -> BuffInstanceRef:
    """解析实例身份：支持 ``"buff:12"`` 紧凑串与 ``{"domain_key", "sequence"}`` 对象。"""

    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise BuffImpactContractError("buff_remove.instance_ref 必须是非空字符串")
        domain_key, separator, sequence_text = text.partition(":")
        if not separator:
            domain_key, sequence_text = "buff", domain_key
        try:
            sequence = int(sequence_text)
        except ValueError as exc:
            raise BuffImpactContractError("buff_remove.instance_ref.sequence 必须是正整数") from exc
        return BuffInstanceRef(
            sequence=_instance_sequence(sequence),
            domain_key=domain_key,
        )
    if isinstance(value, Mapping):
        _reject_unknown_fields(value, allowed={"domain_key", "sequence"})
        domain_key = value.get("domain_key", "buff")
        if not isinstance(domain_key, str) or not domain_key.strip():
            raise BuffImpactContractError("buff_remove.instance_ref.domain_key 必须是非空字符串")
        return BuffInstanceRef(
            sequence=_instance_sequence(value.get("sequence")),
            domain_key=domain_key,
        )
    raise BuffImpactContractError("buff_remove.instance_ref 必须是紧凑串或对象")


def _instance_sequence(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise BuffImpactContractError("buff_remove.instance_ref.sequence 必须是正整数")
    return value


def _removal_reason(value: object) -> BuffRemovalReason:
    if value is None:
        return BuffRemovalReason.CONSUMED
    if not isinstance(value, str):
        raise BuffImpactContractError("buff_remove.reason 必须是字符串")
    try:
        reason = BuffRemovalReason(value)
    except ValueError as exc:
        raise BuffImpactContractError(f"buff_remove.reason 不受支持：{value}") from exc
    if reason not in {
        BuffRemovalReason.DISPELLED,
        BuffRemovalReason.CONSUMED,
        BuffRemovalReason.EXPLICIT,
    }:
        raise BuffImpactContractError(f"buff_remove.reason 不受支持：{value}")
    return reason


def _buff_removal_request_id(
    *,
    source_impact_point_id: str | None,
    impact_request_id: str | None,
) -> str:
    source = source_impact_point_id or impact_request_id
    if source is None:
        raise BuffImpactContractError(
            "REMOVE_STATUS ImpactRequest 必须提供 source_impact_point_id 或 request_id"
        )
    request_component = impact_request_id or ""
    return f"buff-remove:{len(source)}:{source}:{len(request_component)}:{request_component}"


def _reject_unknown_fields(payload: Mapping[str, object], *, allowed: set[str]) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise BuffImpactContractError(f"buff.{unknown[0]} 不是受支持字段")


def _required_text(payload: Mapping[str, object], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise BuffImpactContractError(f"buff.{field_name} 必须是非空字符串")
    return value


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise BuffImpactContractError(f"buff.{field_name} 必须是正整数")
    return value


def _number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise BuffImpactContractError(f"buff.{field_name} 必须是数字")
    result = float(value)
    if not math.isfinite(result):
        raise BuffImpactContractError(f"buff.{field_name} 必须是有限数字")
    return result


def _modifier_values(value: object) -> tuple[BuffModifierValue, ...]:
    if value is None:
        return ()
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise BuffImpactContractError("buff.modifier_values 必须是数组")
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise BuffImpactContractError(f"buff.modifier_values[{index}] 必须是对象")
        _reject_unknown_fields(item, allowed={"term_key", "value"})
        result.append(
            BuffModifierValue(
                term_key=_required_item_text(
                    item,
                    "term_key",
                    f"modifier_values[{index}].term_key",
                ),
                value=_number(item.get("value"), f"modifier_values[{index}].value"),
            )
        )
    return tuple(result)


def _required_item_text(
    payload: Mapping[str, object],
    key: str,
    field_name: str,
) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BuffImpactContractError(f"buff.{field_name} 必须是非空字符串")
    return value


def _optional_subject_ref(value: object, field_name: str) -> AttributeSubjectRef | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise BuffImpactContractError(f"buff.{field_name} 必须是对象或 null")
    _reject_unknown_fields(value, allowed={"kind", "entity_id"})
    kind_value = value.get("kind")
    entity_id = value.get("entity_id")
    if not isinstance(kind_value, str) or not isinstance(entity_id, str):
        raise BuffImpactContractError(f"buff.{field_name}.kind 和 entity_id 必须是字符串")
    try:
        kind = AttributeSubjectKind(kind_value)
    except ValueError as exc:
        raise BuffImpactContractError(f"buff.{field_name}.kind 不受支持：{kind_value}") from exc
    if kind is AttributeSubjectKind.CHARACTER:
        return AttributeSubjectRef.character(entity_id)
    if kind is AttributeSubjectKind.TARGET:
        return AttributeSubjectRef.target(entity_id)
    raise BuffImpactContractError(f"buff.{field_name}.kind 不受支持：{kind_value}")


def _subject_ref_from_target(context, value: str) -> AttributeSubjectRef:
    if not isinstance(value, str) or not value.strip():
        raise BuffImpactContractError("APPLY_STATUS target_ref 必须是非空字符串")
    if context.space_runtime is None:
        return _parse_subject_ref(value)
    if value.startswith("character:"):
        for character in context.space_runtime.team_state.characters:
            if character.combat_entity_id == value:
                return AttributeSubjectRef.character(character.combat_entity_id)
        raise BuffImpactContractError(f"APPLY_STATUS 角色目标不存在：{value}")
    if value.startswith("target:"):
        target = context.space_runtime.targets.get_by_spatial_entity_id(value)
        if target is None:
            target = context.space_runtime.targets.get(value.removeprefix("target:"))
        if target is None:
            raise BuffImpactContractError(f"APPLY_STATUS 目标不存在：{value}")
        return AttributeSubjectRef.target(target.spatial_entity_id)
    return _parse_subject_ref(value)


def _parse_subject_ref(value: str) -> AttributeSubjectRef:
    if value.startswith("character:"):
        return AttributeSubjectRef.character(value)
    if value.startswith("target:"):
        return AttributeSubjectRef.target(value)
    raise BuffImpactContractError(f"APPLY_STATUS target_ref 不受支持：{value}")


def _buff_impact_request_id(
    *,
    source_occurrence_id: str,
    impact_request_id: str | None,
    definition_key: str,
    target_ref: AttributeSubjectRef,
    order: int,
) -> str:
    request_component = impact_request_id or ""
    return (
        "buff-impact"
        f":{len(source_occurrence_id)}:{source_occurrence_id}"
        f":{len(request_component)}:{request_component}"
        f":{len(definition_key)}:{definition_key}"
        f":{len(target_ref.kind.value)}:{target_ref.kind.value}"
        f":{len(target_ref.entity_id)}:{target_ref.entity_id}"
        f":{order}"
    )
