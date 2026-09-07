"""把通用 ``ImpactRequest`` 转换并同步结算为伤害结果。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from genshin_sim.core.attributes import (
    AttributeQueryContext,
    AttributeSubjectRef,
    RuntimeSourceKind,
    RuntimeSourceRef,
    TraceLevel,
)
from genshin_sim.core.events import DamageResolvedPayload, EventType, GameEvent
from genshin_sim.core.systems.damage.enums import DamageReactionCapability
from genshin_sim.core.systems.damage.errors import (
    DamageSourceNotFoundError,
    DamageTargetNotFoundError,
    DamageValidationError,
)
from genshin_sim.core.systems.damage.keys import (
    FORMULA_KEY_GENERAL,
    FORMULA_KEY_LUNAR_REACTION,
)
from genshin_sim.core.systems.damage.models import (
    _CHARACTER_TARGET_DAMAGE_TAGS,
    AmplifyingReactionInput,
    CatalyzeReactionInput,
    DamageQuery,
    DamageRequest,
    DamageResult,
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
        """判断通用影响请求是否携带类型化 ``DamageImpactSpec``。"""

        return request.damage_spec is not None

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

        damage_spec = request.damage_spec
        if damage_spec is None:
            raise DamageValidationError("伤害 ImpactRequest 必须提供 damage_spec")
        if context.space_runtime is None:
            raise DamageSourceNotFoundError("缺少 SpaceRuntime，无法解析伤害来源")
        if request.owner_slot is None:
            raise DamageSourceNotFoundError("伤害请求缺少 owner_slot")
        source = context.space_runtime.team_state.get_character(request.owner_slot)
        if source is None:
            raise DamageSourceNotFoundError(f"伤害来源槽位不存在：{request.owner_slot}")
        if not request.target_refs:
            return ()

        profile = self.profile_registry.resolve_for_main_attack_tag(damage_spec.main_attack_tag)
        formula_key = profile.formula_key
        main_attack_tag = damage_spec.main_attack_tag
        element = damage_spec.element
        scaling_terms = damage_spec.scaling_terms
        flat_base_damage = float(damage_spec.flat_base_damage)
        can_crit = damage_spec.can_crit
        damage_name = damage_spec.display_name
        tags = frozenset(
            (
                *request.tags,
                main_attack_tag,
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
                if target_ref_value != character.combat_entity_id or (
                    main_attack_tag not in _CHARACTER_TARGET_DAMAGE_TAGS
                ):
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
            if lunar_reaction is not None and formula_key is not FORMULA_KEY_LUNAR_REACTION:
                raise DamageValidationError("DamageProfile 未选择月曜完整公式")
            catalyze_reaction = (
                None
                if catalyze_reactions is None
                else catalyze_reactions.get(target_ref_value)
                or catalyze_reactions.get(target_id)
                or catalyze_reactions.get(target_spatial_entity_id)
            )
            if catalyze_reaction is not None:
                if formula_key is not FORMULA_KEY_GENERAL:
                    raise DamageValidationError("只有通用公式可以接收激化输入")
                target_impact_ref = f"{damage_spec.impact_ref}:target:{target_ref_value}"
                if catalyze_reaction.target_impact_ref != target_impact_ref:
                    raise DamageValidationError("激化必须引用同一 target impact ref")
                if catalyze_reaction.trigger_element.value != element.value:
                    raise DamageValidationError("激化 trigger_element 必须匹配当前伤害元素")
            damage_request = DamageRequest(
                request_id=request_id,
                frame=request.frame,
                formula_key=formula_key,
                main_attack_tag=main_attack_tag,
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
                damage_name=damage_name,
                reaction_capabilities=profile.reaction_capabilities,
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


def _damage_request_id(request: ImpactRequest, target_id: str, index: int) -> str:
    """为多目标伤害生成稳定且可追踪的单目标请求 id。"""

    base = (
        request.request_id
        or request.source_impact_point_id
        or (f"damage:{request.frame}:{request.impact_key}")
    )
    return f"{base}:target:{target_id}:{index}"
