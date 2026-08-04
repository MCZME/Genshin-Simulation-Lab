"""把通用 ``ImpactRequest`` 转换并同步结算为伤害结果。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
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
from genshin_sim.core.systems.damage.enums import (
    DamageElement,
    DamageReactionCapability,
    DamageType,
)
from genshin_sim.core.systems.damage.errors import (
    DamageSourceNotFoundError,
    DamageTargetNotFoundError,
    DamageValidationError,
    UnsupportedDamageElementError,
    UnsupportedDamageTypeError,
)
from genshin_sim.core.systems.damage.models import (
    AmplifyingReactionInput,
    CatalyzeReactionInput,
    DamageQuery,
    DamageRequest,
    DamageResult,
    DamageScalingTerm,
    LunarReactionDamageInput,
    SecondaryAmplifyingReactionInput,
    TransformativeReactionInput,
)
from genshin_sim.core.systems.damage.profiles import DamageProfileRegistry
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
        profile_registry: DamageProfileRegistry | None = None,
    ) -> None:
        """保存结算器与 trace 级别，并初始化内存审计记录。"""

        self.resolver = resolver
        self.trace_level = trace_level
        self.profile_registry = profile_registry or DamageProfileRegistry()
        self._records: list[DamageResolutionRecord] = []
        self._external_write_guard: Callable[[], bool] | None = None

    @property
    def records(self) -> tuple[DamageResolutionRecord, ...]:
        """返回已经处理过的伤害结算记录快照。"""

        return tuple(self._records)

    def set_external_write_guard(self, guard: Callable[[], bool] | None) -> None:
        self._external_write_guard = guard

    @staticmethod
    def has_damage_contract(request: ImpactRequest) -> bool:
        """判断通用影响请求是否携带结构化 ``params.damage`` 契约。"""

        return request.damage_spec is not None or isinstance(request.params.get("damage"), Mapping)

    def handle_impact_request(
        self,
        context,
        request: ImpactRequest,
        *,
        amplifying_reactions: Mapping[str, AmplifyingReactionInput] | None = None,
        secondary_amplifying_reactions: (
            Mapping[str, SecondaryAmplifyingReactionInput] | None
        ) = None,
        transformative_reactions: Mapping[str, TransformativeReactionInput] | None = None,
        catalyze_reactions: Mapping[str, CatalyzeReactionInput] | None = None,
        lunar_reactions: Mapping[str, LunarReactionDamageInput] | None = None,
    ) -> tuple[DamageResult, ...]:
        """预检并提交一次 Damage Impact 的全部目标结果。"""

        records = self.prepare_impact_request(
            context,
            request,
            amplifying_reactions=amplifying_reactions,
            secondary_amplifying_reactions=secondary_amplifying_reactions,
            transformative_reactions=transformative_reactions,
            catalyze_reactions=catalyze_reactions,
            lunar_reactions=lunar_reactions,
        )
        self.commit_prepared(context, records)
        return tuple(record.result for record in records)

    def prepare_impact_request(
        self,
        context,
        request: ImpactRequest,
        *,
        amplifying_reactions: Mapping[str, AmplifyingReactionInput] | None = None,
        secondary_amplifying_reactions: (
            Mapping[str, SecondaryAmplifyingReactionInput] | None
        ) = None,
        transformative_reactions: Mapping[str, TransformativeReactionInput] | None = None,
        catalyze_reactions: Mapping[str, CatalyzeReactionInput] | None = None,
        lunar_reactions: Mapping[str, LunarReactionDamageInput] | None = None,
    ) -> tuple[DamageResolutionRecord, ...]:
        """只解析 DamageRequest 和 DamageResult，不记录或发布领域事实。"""

        damage_payload = request.params.get("damage")
        damage_spec = request.damage_spec
        if damage_spec is None and not isinstance(damage_payload, Mapping):
            raise DamageValidationError("伤害 ImpactRequest 缺少 damage_spec 或 params.damage 对象")
        if context.space_runtime is None:
            raise DamageSourceNotFoundError("缺少 SpaceRuntime，无法解析伤害来源")
        if request.owner_slot is None:
            raise DamageSourceNotFoundError("伤害请求缺少 owner_slot")
        source = context.space_runtime.team_state.get_character(request.owner_slot)
        if source is None:
            raise DamageSourceNotFoundError(f"伤害来源槽位不存在：{request.owner_slot}")
        if not request.target_refs:
            return ()

        profile = None
        if damage_spec is None:
            assert isinstance(damage_payload, Mapping)
            element = _damage_element(request, damage_payload)
            damage_type = _damage_type(damage_payload)
            if damage_type is DamageType.CATALYZE_REACTION:
                raise UnsupportedDamageTypeError(
                    "自由 payload 不能直接填写 CATALYZE_REACTION；请通过 DamageProfile 选择激化公式"
                )
            profile_key = None
            scaling_terms = _scaling_terms(damage_payload)
            flat_base_damage = _number(
                damage_payload.get("flat_base_damage", 0.0),
                "flat_base_damage",
            )
            can_crit = _boolean(damage_payload.get("can_crit", True), "can_crit")
            tags = frozenset(
                (*request.tags, *_string_sequence(damage_payload.get("tags", ()), "tags"))
            )
        else:
            try:
                profile = self.profile_registry.require_for_main_attack_tag(
                    damage_spec.main_attack_tag
                )
            except KeyError as exc:
                raise DamageValidationError(str(exc)) from exc
            element = damage_spec.element
            damage_type = profile.damage_type
            profile_key = profile.profile_key
            scaling_terms = damage_spec.scaling_terms
            flat_base_damage = float(damage_spec.flat_base_damage)
            can_crit = damage_spec.can_crit
            tags = frozenset(
                (
                    *request.tags,
                    damage_spec.main_attack_tag,
                    *damage_spec.additional_attack_tags,
                )
            )
        source_context = RuntimeSourceRef(
            (
                RuntimeSourceKind.MECHANIC
                if (
                    transformative_reactions is not None
                    or secondary_amplifying_reactions is not None
                    or lunar_reactions is not None
                )
                else RuntimeSourceKind.ACTION
            ),
            request.action_key or request.impact_key,
            request.request_id or request.source_impact_point_id,
        )
        source_ref = AttributeSubjectRef.character(source.combat_entity_id)
        records: list[DamageResolutionRecord] = []
        for index, target_ref_value in enumerate(request.target_refs):
            target = context.space_runtime.targets.get(target_ref_value)
            if target is None and target_ref_value.startswith("target:"):
                target = context.space_runtime.targets.get(target_ref_value.removeprefix("target:"))
            if target is None:
                character = context.space_runtime.team_state.current_character
                if target_ref_value != character.combat_entity_id or profile_key not in {
                    "damage_profile.reaction.bloom_explosion",
                    "damage_profile.reaction.hyperbloom",
                    "damage_profile.reaction.burgeon",
                    "damage_profile.reaction.lunar_bloom",
                }:
                    raise DamageTargetNotFoundError(f"伤害目标不存在：{target_ref_value}")
                target_id = character.combat_entity_id
                target_ref = AttributeSubjectRef.character(character.combat_entity_id)
                target_level = character.level
                target_spatial_entity_id = character.combat_entity_id
            else:
                target_id = target.target_id
                if target.level is None:
                    raise DamageTargetNotFoundError(f"伤害目标缺少等级：{target_id}")
                target_ref = AttributeSubjectRef.target(target.spatial_entity_id)
                target_level = target.level
                target_spatial_entity_id = target.spatial_entity_id
            request_id = _damage_request_id(request, target_id, index)
            transformative_reaction = (
                None
                if transformative_reactions is None
                else transformative_reactions.get(target_ref_value)
                or transformative_reactions.get(target_id)
                or transformative_reactions.get(target_spatial_entity_id)
            )
            secondary_amplifying_reaction = (
                None
                if secondary_amplifying_reactions is None
                else secondary_amplifying_reactions.get(target_ref_value)
                or secondary_amplifying_reactions.get(target_id)
                or secondary_amplifying_reactions.get(target_spatial_entity_id)
            )
            if secondary_amplifying_reaction is not None:
                if profile is None or damage_spec is None:
                    raise DamageValidationError("二次增幅伤害必须使用已注册的 DamageProfile")
                if (
                    DamageReactionCapability.SECONDARY_AMPLIFYING
                    not in profile.reaction_capabilities
                ):
                    raise DamageValidationError("DamageProfile 未声明二次增幅 capability")
                if secondary_amplifying_reaction.target_impact_ref != damage_spec.impact_ref:
                    raise DamageValidationError("二次增幅必须引用同一 target impact ref")
            lunar_reaction = (
                None
                if lunar_reactions is None
                else lunar_reactions.get(target_ref_value)
                or lunar_reactions.get(target_id)
                or lunar_reactions.get(target_spatial_entity_id)
            )
            if lunar_reaction is not None:
                if profile is None or damage_spec is None:
                    raise DamageValidationError("月曜伤害必须使用已注册的 DamageProfile")
                if damage_type is not DamageType.LUNAR_REACTION:
                    raise DamageValidationError("DamageProfile 未选择月曜完整公式")
            catalyze_reaction = (
                None
                if catalyze_reactions is None
                else catalyze_reactions.get(target_ref_value)
                or catalyze_reactions.get(target_id)
                or catalyze_reactions.get(target_spatial_entity_id)
            )
            if catalyze_reaction is not None:
                if profile is None or damage_spec is None:
                    raise DamageValidationError("激化伤害必须使用已注册的 DamageProfile")
                if damage_type is not DamageType.CATALYZE_REACTION:
                    raise DamageValidationError("DamageProfile 未选择激化完整公式")
                target_impact_ref = f"{damage_spec.impact_ref}:target:{target_ref_value}"
                if catalyze_reaction.target_impact_ref != target_impact_ref:
                    raise DamageValidationError("激化必须引用同一 target impact ref")
                if catalyze_reaction.trigger_element.value != element.value:
                    raise DamageValidationError("激化 trigger_element 必须匹配当前伤害元素")
            elif damage_type is DamageType.CATALYZE_REACTION:
                # 允许无附加反应输入的激化 Profile，行为与普通直伤一致。
                pass
            damage_request = DamageRequest(
                request_id=request_id,
                frame=request.frame,
                damage_type=damage_type,
                impact_key=request.impact_key,
                source_ref=source_ref,
                target_ref=target_ref,
                source_level=source.level,
                target_level=target_level,
                element=element,
                scaling_terms=scaling_terms,
                flat_base_damage=flat_base_damage,
                tags=tags,
                can_crit=can_crit,
                source_context=source_context,
                profile_key=profile_key,
                reaction_capabilities=(
                    frozenset() if profile is None else profile.reaction_capabilities
                ),
                amplifying_reaction=(
                    None
                    if amplifying_reactions is None
                    else amplifying_reactions.get(target_ref_value)
                    or amplifying_reactions.get(target_id)
                ),
                secondary_amplifying_reaction=secondary_amplifying_reaction,
                transformative_reaction=transformative_reaction,
                catalyze_reaction=catalyze_reaction,
                lunar_reaction=lunar_reaction,
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
            records.append(
                DamageResolutionRecord(
                    request.frame,
                    request,
                    damage_request,
                    result,
                )
            )
        return tuple(records)

    def commit_prepared(
        self,
        context,
        records: tuple[DamageResolutionRecord, ...],
    ) -> None:
        """记录已完成预检的结果并在状态提交后发布 Damage 事实。"""

        self.commit_prepared_records(records)
        self.publish_committed_facts(context, records)

    def commit_prepared_records(
        self,
        records: tuple[DamageResolutionRecord, ...],
    ) -> None:
        """提交已预检的伤害记录，但不发布事实。"""

        if self._external_write_guard is not None and self._external_write_guard():
            raise DamageValidationError("元素结算事实发布期间不允许提交伤害")
        for record in records:
            self._records.append(record)

    @staticmethod
    def publish_committed_facts(
        context,
        records: tuple[DamageResolutionRecord, ...],
    ) -> None:
        """为已提交的伤害记录发布 Damage 事实。"""

        for record in records:
            context.events.publish(
                GameEvent(
                    event_type=EventType.DAMAGE_RESOLVED,
                    frame=record.frame,
                    payload=DamageResolvedPayload(record.result),
                )
            )


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
