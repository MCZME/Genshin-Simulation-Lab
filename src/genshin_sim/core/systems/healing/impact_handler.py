"""把 ``ImpactKind.HEAL`` 通用影响请求转换为强类型治疗请求。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from genshin_sim.core.attributes import (
    AttributeSubjectRef,
    RuntimeSourceKind,
    RuntimeSourceRef,
    attribute_key,
)
from genshin_sim.core.systems.healing.errors import HealingValidationError
from genshin_sim.core.systems.healing.handler import (
    HealingApplicationRecord,
    HealingRequestHandler,
)
from genshin_sim.core.systems.healing.models import HealingRequest, HealingScalingTerm

if TYPE_CHECKING:
    from genshin_sim.core.impacts.models import ImpactRequest


CharacterRefResolver = Callable[
    [object, "ImpactRequest", str],
    AttributeSubjectRef,
]


def resolve_character_ref(
    context: object,
    request: ImpactRequest,
    entity_id: str,
) -> AttributeSubjectRef:
    """把 HEAL 锚点解析为治疗系统可用的角色主体引用。"""

    del request
    if entity_id.startswith("character:"):
        return AttributeSubjectRef.character(entity_id)
    if entity_id == "player:active":
        space_runtime = getattr(context, "space_runtime", None)
        team_state = getattr(space_runtime, "team_state", None)
        if team_state is None:
            raise HealingValidationError("HEAL 锚点解析缺少队伍运行态")
        return AttributeSubjectRef.character(team_state.current_character.combat_entity_id)
    raise HealingValidationError(f"不支持的 HEAL 目标锚点：{entity_id}")


@dataclass(frozen=True, slots=True)
class HealingImpactRecord:
    """一次 HEAL ImpactRequest 展开与全部治疗提交记录。"""

    frame: int
    impact_request: ImpactRequest
    healing_requests: tuple[HealingRequest, ...]
    records: tuple[HealingApplicationRecord, ...]


class HealingImpactRequestHandler:
    """把 HEAL Impact 请求适配为单目标治疗请求并提交。"""

    def __init__(
        self,
        handler: HealingRequestHandler,
        *,
        character_ref_resolver: CharacterRefResolver | None = None,
    ) -> None:
        self.handler = handler
        self._character_ref_resolver = character_ref_resolver or resolve_character_ref
        self._records: list[HealingImpactRecord] = []

    @property
    def records(self) -> tuple[HealingImpactRecord, ...]:
        return tuple(self._records)

    def has_heal_contract(self, request: ImpactRequest) -> bool:
        return request.kind.value == "heal" and isinstance(request.params.get("heal"), Mapping)

    def handle_impact_request(
        self,
        context: object,
        request: ImpactRequest,
    ) -> tuple[HealingApplicationRecord, ...]:
        """展开目标并逐个提交治疗请求。"""

        if not self.has_heal_contract(request):
            raise HealingValidationError("HEAL 请求缺少结构化 params.heal 契约")
        if request.owner_slot is None:
            raise HealingValidationError("HEAL 请求必须提供 owner_slot")
        source_ref = AttributeSubjectRef.character(f"character:slot_{request.owner_slot}")
        target_refs = tuple(self._resolve_targets(context, request))
        if not target_refs:
            raise HealingValidationError("HEAL 请求没有可治疗目标")
        payload = cast(Mapping[str, object], request.params["heal"])
        healing_id = self._healing_id(request, payload)
        scaling_terms = self._scaling_terms(payload.get("scaling_terms", ()))
        flat_healing = self._flat_healing(payload.get("flat_healing", 0.0))
        source_context = self._source_context(payload.get("source_context"))
        tags = self._tags(payload.get("tags", ()))

        healing_requests = tuple(
            HealingRequest(
                healing_id=f"{healing_id}:{index}",
                frame=request.frame,
                source_ref=source_ref,
                target_ref=target_ref,
                scaling_terms=scaling_terms,
                flat_healing=flat_healing,
                source_context=source_context,
                tags=tags,
            )
            for index, target_ref in enumerate(target_refs)
        )
        records = tuple(self.handler.handle(heal_request) for heal_request in healing_requests)
        self._records.append(
            HealingImpactRecord(
                frame=request.frame,
                impact_request=request,
                healing_requests=healing_requests,
                records=records,
            )
        )
        return records

    def _resolve_targets(
        self,
        context: object,
        request: ImpactRequest,
    ) -> tuple[AttributeSubjectRef, ...]:
        if request.target_refs:
            return tuple(
                self._character_ref_resolver(context, request, target_ref)
                for target_ref in request.target_refs
            )
        if request.anchor_entity_id is not None:
            return (
                self._character_ref_resolver(
                    context,
                    request,
                    request.anchor_entity_id,
                ),
            )
        return ()

    @staticmethod
    def _healing_id(request: ImpactRequest, payload: Mapping[str, object]) -> str:
        raw = payload.get("healing_id")
        if isinstance(raw, str) and raw.strip():
            return raw
        root = request.request_id or request.source_impact_point_id
        if root is None:
            raise HealingValidationError("HEAL 请求缺少 healing_id 与请求根身份")
        return f"{root}:{request.impact_key}"

    @staticmethod
    def _scaling_terms(
        raw_terms: object,
    ) -> tuple[HealingScalingTerm, ...]:
        if not isinstance(raw_terms, Sequence) or isinstance(raw_terms, (str, bytes)):
            raise HealingValidationError("HEAL scaling_terms 必须是序列")
        terms: list[HealingScalingTerm] = []
        for index, raw in enumerate(raw_terms):
            if not isinstance(raw, Mapping):
                raise HealingValidationError(f"HEAL scaling_terms[{index}] 必须是映射")
            component_key = raw.get("component_key")
            raw_attribute_key = raw.get("attribute_key")
            coefficient = raw.get("coefficient")
            if isinstance(coefficient, bool) or not isinstance(coefficient, int | float):
                raise HealingValidationError(f"HEAL scaling_terms[{index}] coefficient 必须是数字")
            if not isinstance(component_key, str) or not component_key.strip():
                raise HealingValidationError(f"HEAL scaling_terms[{index}] component_key 非法")
            if not isinstance(raw_attribute_key, str) or not raw_attribute_key.strip():
                raise HealingValidationError(f"HEAL scaling_terms[{index}] attribute_key 非法")
            terms.append(
                HealingScalingTerm(
                    component_key=component_key,
                    attribute_key=attribute_key(raw_attribute_key),
                    coefficient=coefficient,
                )
            )
        return tuple(terms)

    @staticmethod
    def _flat_healing(raw: object) -> float:
        if isinstance(raw, bool) or not isinstance(raw, int | float):
            raise HealingValidationError("HEAL flat_healing 必须是数字")
        return float(raw)

    @staticmethod
    def _source_context(raw: object) -> RuntimeSourceRef | None:
        if raw is None:
            return None
        if not isinstance(raw, Mapping):
            raise HealingValidationError("HEAL source_context 必须是映射或 None")
        kind = raw.get("kind")
        source_key = raw.get("source_key")
        instance_id = raw.get("instance_id")
        if not isinstance(kind, str) or not isinstance(source_key, str) or not source_key.strip():
            raise HealingValidationError("HEAL source_context kind/source_key 非法")
        try:
            source_kind = RuntimeSourceKind(kind)
        except ValueError as exc:
            raise HealingValidationError(f"HEAL source_context kind 不受支持：{kind}") from exc
        if instance_id is not None and not isinstance(instance_id, str):
            raise HealingValidationError("HEAL source_context instance_id 必须是字符串或 None")
        return RuntimeSourceRef(source_kind, source_key, instance_id)

    @staticmethod
    def _tags(raw: object) -> frozenset[str]:
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            raise HealingValidationError("HEAL tags 必须是字符串序列")
        tags = tuple(raw)
        if not all(isinstance(tag, str) and tag.strip() for tag in tags):
            raise HealingValidationError("HEAL tags 必须全部是非空字符串")
        return frozenset(tags)
