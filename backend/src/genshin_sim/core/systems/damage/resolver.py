"""伤害公式选择、modifier 收集和公共结果组装入口。"""

from __future__ import annotations

from dataclasses import dataclass, field

from genshin_sim.core.attributes import (
    AttributeKey,
    AttributeQuery,
    AttributeResolution,
    AttributeResolutionSession,
    AttributeResolveOptions,
    AttributeResolver,
    AttributeSubjectKind,
    AttributeSubjectRef,
    ProviderAttributeSubjectScope,
    TraceLevel,
)
from genshin_sim.core.systems.damage.enums import CritOutcome
from genshin_sim.core.systems.damage.errors import DamageProviderViolationError
from genshin_sim.core.systems.damage.formulas import (
    DamageFormulaContext,
    DamageFormulaRegistry,
    DamageFormulaSpec,
    create_default_damage_formula_registry,
)
from genshin_sim.core.systems.damage.models import (
    DamageQuery,
    DamageResult,
    DefenseResolution,
    GeneralDamageResolution,
    LunarReactionDamageResolution,
    TransformativeReactionResolution,
)
from genshin_sim.core.systems.damage.modifiers import (
    DamageAttributeRead,
    DamageModifierCollection,
    DamageModifierIndex,
    DamageModifierProviderSpec,
)


@dataclass(slots=True)
class DamageResolutionSession:
    """一次伤害结算期间共享的属性解析会话和 provider 访问边界。"""

    attribute_resolver: AttributeResolver
    query: DamageQuery
    trace_level: TraceLevel = TraceLevel.FULL
    attribute_session: AttributeResolutionSession = field(init=False)
    active_provider_spec: DamageModifierProviderSpec | None = None

    def __post_init__(self) -> None:
        """创建与本次伤害结算绑定的属性解析 session。"""

        self.attribute_session = self.attribute_resolver.new_session()

    def begin_provider(self, spec: DamageModifierProviderSpec) -> None:
        """进入指定 damage provider 的受限执行区间。"""

        if self.active_provider_spec is not None:
            raise DamageProviderViolationError("damage provider 调用不能嵌套")
        self.active_provider_spec = spec

    def end_provider(self, spec: DamageModifierProviderSpec) -> None:
        """离开当前 damage provider 的受限执行区间。"""

        if self.active_provider_spec != spec:
            raise DamageProviderViolationError("damage provider session 状态不一致")
        self.active_provider_spec = None

    def resolve_for_provider(
        self,
        attribute_key: AttributeKey,
        scope: ProviderAttributeSubjectScope = ProviderAttributeSubjectScope.QUERY_SUBJECT,
    ) -> AttributeResolution:
        """按 provider 声明的读取权限解析属性。"""

        spec = self.active_provider_spec
        if spec is None:
            raise DamageProviderViolationError("只有活动 damage provider 可以读取属性")
        read = DamageAttributeRead(attribute_key, scope)
        if read not in spec.reads:
            raise DamageProviderViolationError(
                f"provider {spec.provider_key} 未声明读取 {attribute_key} ({scope.value})"
            )
        if scope is ProviderAttributeSubjectScope.QUERY_SUBJECT:
            subject_ref = self.query.request.source_ref
            context = self.query.source_attribute_context
        elif scope is ProviderAttributeSubjectScope.QUERY_TARGET:
            subject_ref = self.query.request.target_ref
            context = self.query.target_attribute_context
        else:
            if spec.owner_ref is None:
                raise DamageProviderViolationError(f"provider {spec.provider_key} 没有 owner_ref")
            subject_ref = spec.owner_ref
            context = (
                self.query.source_attribute_context
                if subject_ref.kind is AttributeSubjectKind.CHARACTER
                else self.query.target_attribute_context
            )
        return self._resolve(subject_ref, attribute_key, context)

    def resolve_source(self, attribute_key: AttributeKey) -> AttributeResolution:
        """解析本次伤害来源主体上的属性。"""

        return self._resolve(
            self.query.request.source_ref,
            attribute_key,
            self.query.source_attribute_context,
        )

    def resolve_target(self, attribute_key: AttributeKey) -> AttributeResolution:
        """解析本次伤害目标主体上的属性。"""

        return self._resolve(
            self.query.request.target_ref,
            attribute_key,
            self.query.target_attribute_context,
        )

    def _resolve(self, subject_ref: AttributeSubjectRef, attribute_key: AttributeKey, context):
        """通过属性系统执行带统一帧和 trace level 的底层查询。"""

        return self.attribute_resolver.resolve(
            AttributeQuery(
                subject_ref=subject_ref,
                attribute_key=attribute_key,
                frame=self.query.request.frame,
                context=context,
            ),
            options=AttributeResolveOptions(trace_level=self.trace_level),
            session=self.attribute_session,
        )


@dataclass(frozen=True, slots=True)
class DamageResolver:
    """统一伤害入口：选择完整公式并组装不可变 ``DamageResult``。"""

    attribute_resolver: AttributeResolver
    modifier_index: DamageModifierIndex = field(default_factory=DamageModifierIndex)
    formula_registry: DamageFormulaRegistry = field(
        default_factory=create_default_damage_formula_registry
    )

    def resolve(
        self,
        query: DamageQuery,
        *,
        trace_level: TraceLevel = TraceLevel.FULL,
    ) -> DamageResult:
        """选择完整公式，执行结算，并返回可审计结果。"""

        formula = self.formula_registry.require(query.request.formula_key)
        session = DamageResolutionSession(self.attribute_resolver, query, trace_level)
        modifiers = self.modifier_index.collect(query, session)
        _validate_formula_stages(formula.formula_spec, modifiers)
        resolution = formula.resolve(
            DamageFormulaContext(
                query=query,
                session=session,
                modifiers=modifiers,
                trace_level=trace_level,
            )
        )
        return _build_damage_result(query, resolution, modifiers, trace_level)


def _validate_formula_stages(
    formula_spec: DamageFormulaSpec,
    modifiers: DamageModifierCollection,
) -> None:
    """确保 provider 实际返回的 term 都被当前完整公式允许。"""

    for term in (*modifiers.applied_terms, *modifiers.rejected_terms):
        if term.stage not in formula_spec.allowed_modifier_stages:
            raise DamageProviderViolationError(
                f"伤害公式 {formula_spec.formula_key} 不允许阶段：{term.stage.value}"
            )


def _build_damage_result(
    query: DamageQuery,
    resolution: (
        GeneralDamageResolution
        | TransformativeReactionResolution
        | LunarReactionDamageResolution
    ),
    modifiers: DamageModifierCollection,
    trace_level: TraceLevel,
) -> DamageResult:
    """把公式专属 resolution 映射回第一轮兼容的扁平结果模型。"""

    if isinstance(resolution, LunarReactionDamageResolution):
        return DamageResult(
            request_id=query.request.request_id,
            frame=query.request.frame,
            formula_key=query.request.formula_key,
            main_attack_tag=query.request.main_attack_tag,
            source_ref=query.request.source_ref,
            target_ref=query.request.target_ref,
            element=query.request.element,
            base_damage=resolution.weighted_base_damage,
            base_damage_additions=(),
            damage_bonus_multiplier=1.0,
            crit_outcome=CritOutcome.NOT_APPLICABLE,
            crit_rate=0.0,
            crit_damage=0.0,
            crit_multiplier=1.0,
            reaction_multiplier=1.0,
            defense=DefenseResolution(
                source_level=query.request.source_level,
                target_level=query.request.target_level,
                defense_reduction=0.0,
                defense_ignore=0.0,
                multiplier=1.0,
            ),
            resistance=resolution.resistance,
            official_damage=resolution.official_damage,
            debug_multiplier=resolution.debug_multiplier,
            final_damage=resolution.final_damage,
            damage_name=query.request.damage_name,
            lunar_reaction_resolution=resolution,
            source_attribute_trace=(
                () if trace_level is TraceLevel.NONE else resolution.source_attribute_trace
            ),
            target_attribute_trace=(
                () if trace_level is TraceLevel.NONE else resolution.target_attribute_trace
            ),
            applied_terms=(),
            rejected_terms=(),
            trace_level=trace_level,
            trace_metadata={
                "lunar_mode": resolution.reaction.mode.value,
                "lunar_participant_count": len(resolution.components),
            },
        )

    if isinstance(resolution, TransformativeReactionResolution):
        return DamageResult(
            request_id=query.request.request_id,
            frame=query.request.frame,
            formula_key=query.request.formula_key,
            main_attack_tag=query.request.main_attack_tag,
            source_ref=query.request.source_ref,
            target_ref=query.request.target_ref,
            element=query.request.element,
            base_damage=resolution.reaction.level_multiplier * resolution.reaction.base_multiplier,
            base_damage_additions=(),
            damage_bonus_multiplier=1.0,
            crit_outcome=CritOutcome.NOT_APPLICABLE,
            crit_rate=0.0,
            crit_damage=0.0,
            crit_multiplier=1.0,
            reaction_multiplier=1
            + resolution.reaction.mastery_bonus
            + resolution.reaction.reaction_bonus,
            defense=resolution.defense,
            resistance=resolution.resistance,
            official_damage=resolution.official_damage,
            debug_multiplier=resolution.debug_multiplier,
            final_damage=resolution.final_damage,
            damage_name=query.request.damage_name,
            reaction_details=resolution.reaction,
            secondary_amplifying_resolution=resolution.secondary_amplifying_resolution,
            source_attribute_trace=(),
            target_attribute_trace=(
                () if trace_level is TraceLevel.NONE else resolution.target_attribute_trace
            ),
            applied_terms=(),
            rejected_terms=(),
            trace_level=trace_level,
            trace_metadata={"defense_policy": resolution.reaction.defense_policy},
        )

    applied_terms = () if trace_level is TraceLevel.NONE else modifiers.applied_terms
    rejected_terms = modifiers.rejected_terms if trace_level is TraceLevel.FULL else ()
    source_trace = () if trace_level is TraceLevel.NONE else resolution.source_attribute_trace
    target_trace = () if trace_level is TraceLevel.NONE else resolution.target_attribute_trace
    return DamageResult(
        request_id=query.request.request_id,
        frame=query.request.frame,
        formula_key=query.request.formula_key,
        main_attack_tag=query.request.main_attack_tag,
        source_ref=query.request.source_ref,
        target_ref=query.request.target_ref,
        element=query.request.element,
        base_damage=resolution.scaling.value,
        base_damage_additions=resolution.scaling.additions,
        damage_bonus_multiplier=resolution.damage_bonus.multiplier,
        crit_outcome=resolution.critical.outcome,
        crit_rate=resolution.critical.crit_rate,
        crit_damage=resolution.critical.crit_damage,
        crit_multiplier=resolution.critical.multiplier,
        reaction_multiplier=resolution.reaction.multiplier,
        defense=resolution.defense,
        resistance=resolution.resistance,
        official_damage=resolution.official_damage,
        debug_multiplier=resolution.debug_multiplier,
        final_damage=resolution.final_damage,
        damage_name=query.request.damage_name,
        reaction_details=resolution.reaction,
        catalyze_reaction_resolution=resolution.catalyze,
        component_results=resolution.scaling.component_results,
        source_attribute_trace=source_trace,
        target_attribute_trace=target_trace,
        applied_terms=applied_terms,
        rejected_terms=rejected_terms,
        trace_level=trace_level,
        trace_metadata={"effective_crit_rate": resolution.critical.effective_crit_rate},
        damage_bonus_zone=resolution.damage_bonus,
        critical_zone=resolution.critical,
    )
