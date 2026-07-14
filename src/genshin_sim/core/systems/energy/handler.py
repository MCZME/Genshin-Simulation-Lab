"""ImpactRequest 到强类型元素能量请求的适配器。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from genshin_sim.core.attributes import AttributeSubjectRef, RuntimeSourceKind, RuntimeSourceRef
from genshin_sim.core.systems.energy.errors import (
    EnergyValidationError,
    UnsupportedEnergyOperationError,
)
from genshin_sim.core.systems.energy.models import (
    DrainEnergyRequest,
    EnergyElement,
    EnergyPickupKind,
    RestoreEnergyRequest,
    SpawnEnergyPickupRequest,
    SpendBurstEnergyRequest,
)
from genshin_sim.core.systems.energy.runtime import EnergyRuntime


@dataclass(frozen=True, slots=True)
class EnergyImpactRecord:
    frame: int
    impact_request: object
    request: object
    result: object


class EnergyImpactRequestHandler:
    def __init__(self, runtime: EnergyRuntime) -> None:
        self.runtime = runtime
        self._records: list[EnergyImpactRecord] = []

    @property
    def records(self) -> tuple[EnergyImpactRecord, ...]:
        return tuple(self._records)

    @staticmethod
    def has_energy_contract(request) -> bool:
        return isinstance(request.params.get("energy"), Mapping)

    def handle_impact_request(self, context, request):
        payload = request.params.get("energy")
        if not isinstance(payload, Mapping):
            raise EnergyValidationError("元素能量 ImpactRequest 缺少 params.energy 对象")
        operation = _required_text(payload, "operation")
        source_context = RuntimeSourceRef(
            RuntimeSourceKind.ACTION,
            request.action_key or request.impact_key,
            request.request_id or request.source_impact_point_id,
        )
        if operation == "spawn_pickup":
            _require_exact_keys(
                payload,
                {
                    "schema_version",
                    "operation",
                    "pickup_kind",
                    "element",
                    "count",
                    "travel_frames",
                    "tags",
                },
            )
            typed = SpawnEnergyPickupRequest(
                request_id=_default_id(request),
                frame=request.frame,
                pickup_kind=_pickup_kind(payload.get("pickup_kind")),
                element=_element(payload.get("element")),
                count=_positive_int(payload.get("count"), "count"),
                travel_frames=_non_negative_int(payload.get("travel_frames"), "travel_frames"),
                source_ref=_owner_ref(context, request),
                source_context=source_context,
                tags=frozenset((*request.tags, *_tags(payload.get("tags", ())))),
            )
            result = self.runtime.spawn_pickup(typed)
        elif operation in {"restore", "drain", "spend_burst"}:
            allowed = {"schema_version", "operation", "tags"}
            if operation == "spend_burst":
                allowed.add("action_instance_id")
            else:
                allowed.add("amount")
            _require_exact_keys(payload, allowed)
            target = _single_target_ref(context, request)
            change_id = _default_id(request)
            tags = frozenset((*request.tags, *_tags(payload.get("tags", ()))))
            if operation == "restore":
                typed = RestoreEnergyRequest(
                    change_id,
                    request.frame,
                    target,
                    _amount(payload),
                    _owner_ref(context, request),
                    source_context,
                    tags,
                )
                result = self.runtime.restore(typed)
            elif operation == "drain":
                typed = DrainEnergyRequest(
                    change_id,
                    request.frame,
                    target,
                    _amount(payload),
                    _owner_ref(context, request),
                    source_context,
                    tags,
                )
                result = self.runtime.drain(typed)
            else:
                typed = SpendBurstEnergyRequest(
                    change_id,
                    request.frame,
                    target,
                    _required_text(payload, "action_instance_id"),
                    source_context,
                    tags,
                )
                result = self.runtime.spend_burst(typed)
        else:
            raise UnsupportedEnergyOperationError(f"不支持的 params.energy.operation：{operation}")
        self._records.append(EnergyImpactRecord(request.frame, request, typed, result))
        return result


def _owner_ref(context, request) -> AttributeSubjectRef | None:
    if request.owner_slot is None or context.space_runtime is None:
        return None
    character = context.space_runtime.team_state.get_character(request.owner_slot)
    return None if character is None else AttributeSubjectRef.character(character.combat_entity_id)


def _single_target_ref(context, request) -> AttributeSubjectRef:
    if len(request.target_refs) != 1:
        raise EnergyValidationError("直接元素能量操作必须有一个明确角色 target_ref")
    target = request.target_refs[0]
    entity_id = getattr(target, "entity_id", target)
    if not isinstance(entity_id, str):
        raise EnergyValidationError("元素能量 target_ref 不受支持")
    if context.space_runtime is not None:
        for character in context.space_runtime.team_state.characters:
            if character.combat_entity_id == entity_id:
                return AttributeSubjectRef.character(entity_id)
    return AttributeSubjectRef.character(entity_id)


def _required_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EnergyValidationError(f"energy.{key} 必须是非空字符串")
    return value


def _default_id(request) -> str:
    if request.request_id:
        return request.request_id
    return f"energy:{request.source_impact_point_id or request.impact_key}:{request.frame}"


def _amount(payload: Mapping[str, object]) -> float:
    value = payload.get("amount")
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise EnergyValidationError("energy.amount 必须是数字")
    return float(value)


def _positive_int(value: object, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise EnergyValidationError(f"energy.{key} 必须是正整数")
    return value


def _non_negative_int(value: object, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EnergyValidationError(f"energy.{key} 必须是非负整数")
    return value


def _element(value: object) -> EnergyElement:
    try:
        return EnergyElement(value)
    except ValueError as exc:
        raise EnergyValidationError(f"不支持的 energy.element：{value}") from exc


def _pickup_kind(value: object) -> EnergyPickupKind:
    try:
        return EnergyPickupKind(value)
    except ValueError as exc:
        raise EnergyValidationError(f"不支持的 energy.pickup_kind：{value}") from exc


def _tags(value: object) -> tuple[str, ...]:
    if not isinstance(value, tuple | list) or isinstance(value, str):
        raise EnergyValidationError("energy.tags 必须是字符串数组")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise EnergyValidationError("energy.tags 必须是非空字符串数组")
    return tuple(value)


def _require_exact_keys(payload: Mapping[str, object], allowed: set[str]) -> None:
    if payload.get("schema_version") != 1:
        raise EnergyValidationError("energy.schema_version 必须为 1")
    unknown = set(payload) - allowed
    if unknown:
        raise EnergyValidationError(f"energy 包含未知字段：{', '.join(sorted(unknown))}")
