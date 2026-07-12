"""把通用 ``ImpactRequest`` 转换并同步结算为伤害结果。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from genshin_sim.core.attributes import (
    AttributeQueryContext,
    AttributeSubjectRef,
    RuntimeSourceKind,
    RuntimeSourceRef,
    TraceLevel,
    attribute_key,
)
from genshin_sim.core.events import DamageResolvedPayload, EventType, GameEvent
from genshin_sim.core.systems.damage.enums import DamageElement, DamageType
from genshin_sim.core.systems.damage.errors import (
    DamageSourceNotFoundError,
    DamageTargetNotFoundError,
    DamageValidationError,
    UnsupportedDamageElementError,
    UnsupportedDamageTypeError,
)
from genshin_sim.core.systems.damage.models import (
    DamageQuery,
    DamageRequest,
    DamageResult,
    DamageScalingTerm,
)
from genshin_sim.core.systems.damage.resolver import DamageResolver

if TYPE_CHECKING:
    from genshin_sim.core.impacts.models import ImpactRequest


@dataclass(frozen=True, slots=True)
class DamageResolutionRecord:
    """一次 ImpactRequest 结算出的类型化请求与最终结果记录。"""

    frame: int
    impact_request: ImpactRequest
    damage_request: DamageRequest
    result: DamageResult


class DamageRequestHandler:
    """伤害系统挂接到 ImpactRequestDispatcher 的同步处理入口。"""

    def __init__(
        self,
        resolver: DamageResolver,
        *,
        trace_level: TraceLevel = TraceLevel.FULL,
    ) -> None:
        """保存结算器与 trace 级别，并初始化内存审计记录。"""

        self.resolver = resolver
        self.trace_level = trace_level
        self._records: list[DamageResolutionRecord] = []

    @property
    def records(self) -> tuple[DamageResolutionRecord, ...]:
        """返回已经处理过的伤害结算记录快照。"""

        return tuple(self._records)

    @staticmethod
    def has_damage_contract(request: ImpactRequest) -> bool:
        """判断通用影响请求是否携带结构化 ``params.damage`` 契约。"""

        return isinstance(request.params.get("damage"), Mapping)

    def handle_impact_request(
        self,
        context,
        request: ImpactRequest,
    ) -> tuple[DamageResult, ...]:
        """解析来源和目标，逐目标构造 ``DamageRequest`` 并发布结果事件。"""

        damage_payload = request.params.get("damage")
        if not isinstance(damage_payload, Mapping):
            raise DamageValidationError("伤害 ImpactRequest 缺少 params.damage 对象")
        if context.space_runtime is None:
            raise DamageSourceNotFoundError("缺少 SpaceRuntime，无法解析伤害来源")
        if request.owner_slot is None:
            raise DamageSourceNotFoundError("伤害请求缺少 owner_slot")
        source = context.space_runtime.team_state.get_character(request.owner_slot)
        if source is None:
            raise DamageSourceNotFoundError(f"伤害来源槽位不存在：{request.owner_slot}")
        if not request.target_refs:
            return ()

        element = _damage_element(request, damage_payload)
        damage_type = _damage_type(damage_payload)
        scaling_terms = _scaling_terms(damage_payload)
        flat_base_damage = _number(damage_payload.get("flat_base_damage", 0.0), "flat_base_damage")
        can_crit = _boolean(damage_payload.get("can_crit", True), "can_crit")
        tags = frozenset((*request.tags, *_string_sequence(damage_payload.get("tags", ()), "tags")))
        source_context = RuntimeSourceRef(
            RuntimeSourceKind.ACTION,
            request.action_key or request.impact_key,
            request.request_id or request.source_impact_point_id,
        )
        source_ref = AttributeSubjectRef.character(source.combat_entity_id)
        results: list[DamageResult] = []
        for index, target_ref_value in enumerate(request.target_refs):
            target = context.space_runtime.targets.get(target_ref_value)
            if target is None and target_ref_value.startswith("target:"):
                target = context.space_runtime.targets.get(target_ref_value.removeprefix("target:"))
            if target is None:
                raise DamageTargetNotFoundError(f"伤害目标不存在：{target_ref_value}")
            target_id = target.target_id
            if target.level is None:
                raise DamageTargetNotFoundError(f"伤害目标缺少等级：{target_id}")
            target_ref = AttributeSubjectRef.target(target.spatial_entity_id)
            request_id = _damage_request_id(request, target_id, index)
            damage_request = DamageRequest(
                request_id=request_id,
                frame=request.frame,
                damage_type=damage_type,
                impact_key=request.impact_key,
                source_ref=source_ref,
                target_ref=target_ref,
                source_level=source.level,
                target_level=target.level,
                element=element,
                scaling_terms=scaling_terms,
                flat_base_damage=flat_base_damage,
                tags=tags,
                can_crit=can_crit,
                source_context=source_context,
            )
            query = DamageQuery(
                request=damage_request,
                source_attribute_context=AttributeQueryContext(
                    tags=tags,
                    source_ref=source_context,
                    target_ref=target_ref,
                ),
                target_attribute_context=AttributeQueryContext(
                    tags=tags,
                    source_ref=source_context,
                    target_ref=source_ref,
                ),
            )
            result = self.resolver.resolve(query, trace_level=self.trace_level)
            self._records.append(
                DamageResolutionRecord(request.frame, request, damage_request, result)
            )
            results.append(result)
            context.events.publish(
                GameEvent(
                    event_type=EventType.DAMAGE_RESOLVED,
                    frame=request.frame,
                    payload=DamageResolvedPayload(result),
                    source=source,
                )
            )
        return tuple(results)


def _damage_element(
    request: ImpactRequest,
    payload: Mapping[str, object],
) -> DamageElement:
    """从 ImpactRequest 或 payload 中读取并校验伤害元素。"""

    raw = request.element or payload.get("element")
    if not isinstance(raw, str) or not raw.strip():
        raise UnsupportedDamageElementError("伤害请求缺少 element")
    try:
        return DamageElement(raw)
    except ValueError as exc:
        raise UnsupportedDamageElementError(f"不支持的伤害元素：{raw}") from exc


def _damage_type(payload: Mapping[str, object]) -> DamageType:
    """从 payload 中读取并校验显式伤害类型。"""

    raw = payload.get("damage_type")
    if not isinstance(raw, str) or not raw.strip():
        raise UnsupportedDamageTypeError("伤害请求缺少 damage_type")
    try:
        return DamageType(raw)
    except ValueError as exc:
        raise UnsupportedDamageTypeError(f"不支持的伤害类型：{raw}") from exc


def _scaling_terms(payload: Mapping[str, object]) -> tuple[DamageScalingTerm, ...]:
    """把 ``params.damage.scaling_terms`` 转换为类型化倍率项。"""

    raw = payload.get("scaling_terms", ())
    if isinstance(raw, str) or not isinstance(raw, Sequence):
        raise DamageValidationError("damage.scaling_terms 必须是数组")
    result: list[DamageScalingTerm] = []
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise DamageValidationError(f"damage.scaling_terms[{index}] 必须是对象")
        component_key = item.get("component_key")
        attribute_key_value = item.get("attribute_key")
        if not isinstance(component_key, str):
            raise DamageValidationError(f"damage.scaling_terms[{index}].component_key 必须是字符串")
        if not isinstance(attribute_key_value, str):
            raise DamageValidationError(f"damage.scaling_terms[{index}].attribute_key 必须是字符串")
        result.append(
            DamageScalingTerm(
                component_key=component_key,
                attribute_key=attribute_key(attribute_key_value),
                coefficient=_number(item.get("coefficient"), f"scaling_terms[{index}].coefficient"),
            )
        )
    return tuple(result)


def _number(value: object, field_name: str) -> float:
    """读取 payload 中必须为数字的字段。"""

    if isinstance(value, bool) or not isinstance(value, int | float):
        raise DamageValidationError(f"damage.{field_name} 必须是数字")
    return float(value)


def _boolean(value: object, field_name: str) -> bool:
    """读取 payload 中必须为布尔值的字段。"""

    if not isinstance(value, bool):
        raise DamageValidationError(f"damage.{field_name} 必须是布尔值")
    return value


def _string_sequence(value: object, field_name: str) -> tuple[str, ...]:
    """读取 payload 中必须为非空字符串数组的字段。"""

    if isinstance(value, str) or not isinstance(value, Sequence):
        raise DamageValidationError(f"damage.{field_name} 必须是字符串数组")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise DamageValidationError(f"damage.{field_name} 必须是字符串数组")
        result.append(item)
    return tuple(result)


def _damage_request_id(request: ImpactRequest, target_id: str, index: int) -> str:
    """为多目标伤害生成稳定且可追踪的单目标请求 id。"""

    base = (
        request.request_id
        or request.source_impact_point_id
        or (f"damage:{request.frame}:{request.impact_key}")
    )
    return f"{base}:target:{target_id}:{index}"
