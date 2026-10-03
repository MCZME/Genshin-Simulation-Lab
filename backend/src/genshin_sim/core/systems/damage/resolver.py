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
from genshin_sim.core.systems.damage.enums import CritOutcome, LunarReactionDamageMode
from genshin_sim.core.systems.damage.errors import (
    DamageProviderViolationError,
    DamageValidationError,
)
from genshin_sim.core.systems.damage.facts import (
    DamageFactIndex,
    DamageFactValue,
)
from genshin_sim.core.systems.damage.formulas import (
    DamageFormulaContext,
    DamageFormulaRegistry,
    create_default_damage_formula_registry,
    validate_formula_modifier_stages,
)
from genshin_sim.core.systems.damage.models import (
    DamageModifierTerm,
    DamageQuery,
    DamageResult,
    DefenseResolution,
    GeneralDamageResolution,
    LunarReactionDamageResolution,
    ResistanceResolution,
    StellarReactionDamageResolution,
    TransformativeReactionResolution,
)
from genshin_sim.core.systems.damage.modifiers import (
    DamageAttributeRead,
    DamageModifierCollection,
    DamageModifierIndex,
    DamageModifierProviderSpec,
)
from genshin_sim.core.systems.damage.stellar import STELLAR_SLOT_BASE_MULTIPLIER


@dataclass(slots=True)
class DamageResolutionScope:
    """一次伤害结算的作用域与 provider 能力边界。

    它只活在一次 ``DamageResolver.resolve`` 调用内，不跨伤害、不跨帧。职责
    有三：持有本次结算的 query 与 trace level；为属性读取和伤害事实读取提供
    一个共享入口；借 ``active_provider_spec`` 在 provider 执行区间上做越权
    校验。命名取"作用域"而非"会话"，正是为了表达它既划定生命周期、也划定
    权限边界这两层含义。
    """

    attribute_resolver: AttributeResolver
    query: DamageQuery
    trace_level: TraceLevel = TraceLevel.FULL
    fact_index: DamageFactIndex = field(default_factory=DamageFactIndex)
    attribute_session: AttributeResolutionSession = field(init=False)
    active_provider_spec: DamageModifierProviderSpec | None = None

    def __post_init__(self) -> None:
        """创建与本次伤害结算绑定的属性解析会话。"""

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

    def read_fact(self, key: str) -> DamageFactValue | None:
        """按 provider 声明的事实读取权限读取模拟事实。

        只允许活动 provider 读取自己声明过的 key。取值按作用域叠加：先查
        请求级事实（发射时绑定、随请求携带，对本次请求的全部目标结算一致），
        未命中再回落会话级事实索引；两处都没有时返回 ``None``，表示条件不
        成立，而不是错误。
        """

        spec = self.active_provider_spec
        if spec is None:
            raise DamageProviderViolationError("只有活动 damage provider 可以读取伤害事实")
        if key not in spec.reads_facts:
            raise DamageProviderViolationError(
                f"provider {spec.provider_key} 未声明读取伤害事实 {key}"
            )
        request_facts = self.query.request.request_facts
        if key in request_facts:
            return request_facts[key]
        return self.fact_index.read(key)

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
    fact_index: DamageFactIndex = field(default_factory=DamageFactIndex)
    # 装配期声明为请求级事实的全部 key（内容单元发射方可能写入的集合）。
    request_fact_keys: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        """交叉校验 provider 声明的事实读取都有来源，避免静默失效。

        事实读取的缺失语义是"条件不成立"，因此一个拼错或没被声明的 key 会
        让 provider 永远读到空值而不报错。这里在组装期一次性检出：声明读取
        的 key 必须由会话容器提供，或被某内容单元声明为请求级事实。请求级
        key 同时不得与会话容器 key 撞名——撞名意味着同一 key 承载两种作用域
        语义，叠加顺序会静默改变取值来源。
        """

        request_keys = frozenset(self.request_fact_keys)
        object.__setattr__(self, "request_fact_keys", request_keys)
        collisions = request_keys.intersection(self.fact_index.fact_keys)
        if collisions:
            raise DamageValidationError(
                f"请求级事实 key 与会话容器 key 冲突，同一 key 不能承载两种作用域语义："
                f"{sorted(collisions)}"
            )
        for provider_key, fact_key in self.modifier_index.declared_fact_reads:
            if self.fact_index.provides(fact_key) or fact_key in request_keys:
                continue
            raise DamageValidationError(
                f"provider {provider_key} 声明读取的伤害事实 {fact_key} "
                "没有容器提供，也没有内容单元声明为请求级事实"
            )

    def resolve(
        self,
        query: DamageQuery,
        *,
        trace_level: TraceLevel = TraceLevel.FULL,
    ) -> DamageResult:
        """选择完整公式，执行结算，并返回可审计结果。"""

        formula = self.formula_registry.require(query.request.formula_key)
        scope = DamageResolutionScope(
            attribute_resolver=self.attribute_resolver,
            query=query,
            trace_level=trace_level,
            fact_index=self.fact_index,
        )
        modifiers = self.modifier_index.collect(query, scope)
        validate_formula_modifier_stages(formula.formula_spec, modifiers)
        resolution = formula.resolve(
            DamageFormulaContext(
                query=query,
                scope=scope,
                modifiers=modifiers,
                trace_level=trace_level,
                modifier_collector=self.modifier_index.collect,
            )
        )
        return _build_damage_result(query, resolution, modifiers, trace_level)


def _build_damage_result(
    query: DamageQuery,
    resolution: (
        GeneralDamageResolution
        | TransformativeReactionResolution
        | LunarReactionDamageResolution
        | StellarReactionDamageResolution
    ),
    modifiers: DamageModifierCollection,
    trace_level: TraceLevel,
) -> DamageResult:
    """把公式专属 resolution 映射回第一轮兼容的扁平结果模型。"""

    if isinstance(resolution, StellarReactionDamageResolution):
        # 星烁的括号值（倍率区 × 基础系数 × 基础增伤 × 精通增伤区 × 大权区 + 羽毛区）
        # 落在 base_damage，与月曜同构；暴击、抗性、擢升留在各自乘区字段，
        # 因此扁平模型不再出现"没有字段承载的乘区"。
        scaling = resolution.scaling
        # 复合模式的逐参与者账本在 components[].modifier_terms，顶层不重复列入。
        if trace_level is TraceLevel.NONE or resolution.components:
            applied_terms: tuple[DamageModifierTerm, ...] = ()
            rejected_terms: tuple[DamageModifierTerm, ...] = ()
        else:
            applied_terms = (*modifiers.applied_terms, *resolution.panel_terms)
            rejected_terms = modifiers.rejected_terms if trace_level is TraceLevel.FULL else ()
        return DamageResult(
            request_id=query.request.request_id,
            frame=query.request.frame,
            formula_key=query.request.formula_key,
            main_attack_tag=query.request.main_attack_tag,
            source_ref=query.request.source_ref,
            target_ref=query.request.target_ref,
            element=query.request.element,
            base_damage=resolution.base_damage,
            base_damage_additions=(),
            damage_bonus_multiplier=1.0,
            crit_outcome=(
                CritOutcome.NOT_APPLICABLE
                if resolution.critical is None
                else resolution.critical.outcome
            ),
            crit_rate=0.0 if resolution.critical is None else resolution.critical.crit_rate,
            crit_damage=(0.0 if resolution.critical is None else resolution.critical.crit_damage),
            crit_multiplier=(
                1.0 if resolution.critical is None else resolution.critical.multiplier
            ),
            reaction_multiplier=1.0,
            defense=DefenseResolution(
                source_level=query.request.source_level,
                target_level=query.request.target_level,
                defense_reduction=0.0,
                defense_ignore=0.0,
                multiplier=1.0,
            ),
            resistance=(
                ResistanceResolution(resistance=0.0, multiplier=1.0)
                if resolution.resistance is None
                else resolution.resistance
            ),
            official_damage=resolution.official_damage,
            debug_multiplier=resolution.debug_multiplier,
            final_damage=resolution.final_damage,
            damage_name=query.request.damage_name,
            stellar_reaction_resolution=resolution,
            critical_zone=resolution.critical,
            component_results=(() if scaling is None else tuple(scaling.component_results)),
            applied_terms=applied_terms,
            rejected_terms=rejected_terms,
            request_facts=query.request.request_facts,
            trace_level=trace_level,
            trace_metadata={
                "stellar_mode": resolution.input.mode,
                "stellar_base_multiplier": resolution.merged_slot(
                    STELLAR_SLOT_BASE_MULTIPLIER, resolution.input.stellar_base_multiplier
                ),
                "stellar_mastery_bonus": resolution.mastery_bonus,
            },
        )

    if isinstance(resolution, LunarReactionDamageResolution):
        # 月曜的扁平结果取排名第一组分的实时读取投影；槽位账单在直伤模式下提到
        # 顶层，复合模式的账本在 components[].modifier_terms 内各自保留。
        top = resolution.components[0]
        lunar_direct = resolution.reaction.mode is LunarReactionDamageMode.CHARACTER_DIRECT
        # 直伤模式只有单一组分，账本直接取该组分的收集结果——与实算用的是同一份
        # 词条，避免顶层收集与组分收集因查询差异（来源、标签）而署名不一致。
        lunar_applied_terms: tuple[DamageModifierTerm, ...] = (
            ()
            if trace_level is TraceLevel.NONE or not lunar_direct
            else (*top.modifier_terms, *resolution.panel_terms)
        )
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
            # 直伤模式的倍率分解对齐星烁：取唯一组分的倍率区组件；复合模式的账本
            # 在组分内各自保留，顶层不再重复列入。倍率区数值是反应前值，
            # 与 base_damage（反应后加权值）不同量纲，由前端分区呈现。
            component_results=(
                ()
                if not lunar_direct or top.scaling is None
                else tuple(top.scaling.component_results)
            ),
            damage_bonus_multiplier=1.0,
            crit_outcome=top.critical.outcome,
            crit_rate=top.critical.crit_rate,
            crit_damage=top.critical.crit_damage,
            crit_multiplier=top.critical.multiplier,
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
            critical_zone=top.critical,
            applied_terms=lunar_applied_terms,
            rejected_terms=(
                modifiers.rejected_terms if trace_level is TraceLevel.FULL and lunar_direct else ()
            ),
            request_facts=query.request.request_facts,
            trace_level=trace_level,
            trace_metadata={
                "lunar_mode": resolution.reaction.mode.value,
                "lunar_participant_count": len(resolution.components),
                "lunar_slots": {slot.slot_key: slot.merged for slot in resolution.slots},
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
            # 槽位账单 = 本次伤害效果词条 + 面板属性读取词条。剧变已开放抗性位，
            # 目标面板抗性读取因此进入账单；未开放的位置不产生面板词条。
            applied_terms=(
                ()
                if trace_level is TraceLevel.NONE
                else (*modifiers.applied_terms, *resolution.panel_terms)
            ),
            rejected_terms=modifiers.rejected_terms if trace_level is TraceLevel.FULL else (),
            request_facts=query.request.request_facts,
            trace_level=trace_level,
            trace_metadata={"defense_policy": resolution.reaction.defense_policy},
        )

    # 通用公式的槽位账单 = 本次伤害效果词条 + 面板属性读取词条。
    applied_terms = (
        ()
        if trace_level is TraceLevel.NONE
        else (*modifiers.applied_terms, *resolution.panel_terms)
    )
    rejected_terms = modifiers.rejected_terms if trace_level is TraceLevel.FULL else ()
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
        applied_terms=applied_terms,
        rejected_terms=rejected_terms,
        request_facts=query.request.request_facts,
        trace_level=trace_level,
        trace_metadata={"effective_crit_rate": resolution.critical.effective_crit_rate},
        damage_bonus_zone=resolution.damage_bonus,
        critical_zone=resolution.critical,
    )
