"""完整伤害公式协议、注册表和通用公式实现。"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol

from genshin_sim.core.attributes import (
    ELEMENT_TO_RESISTANCE_KEY,
    STAT_ELEMENTAL_MASTERY,
    AttributeQueryContext,
    AttributeResolution,
    RuntimeSourceKind,
    RuntimeSourceRef,
    TraceLevel,
)
from genshin_sim.core.elements import TransformativeReactionSourceKind
from genshin_sim.core.systems.damage.enums import (
    DamageModifierStage,
    LunarReactionDamageMode,
)
from genshin_sim.core.systems.damage.errors import (
    DamageFormulaInputError,
    DamageResolutionError,
    DuplicateDamageFormulaError,
    InvalidDamageScalingError,
    UnsupportedDamageFormulaError,
)
from genshin_sim.core.systems.damage.keys import (
    FORMULA_KEY_GENERAL,
    FORMULA_KEY_LUNAR_REACTION,
    FORMULA_KEY_TRANSFORMATIVE_REACTION,
    KNOWN_FORMULA_KEYS,
)
from genshin_sim.core.systems.damage.level_multipliers import transformative_level_multiplier
from genshin_sim.core.systems.damage.models import (
    BaseDamageAddition,
    CatalyzeReactionResolution,
    DamageFormulaResolution,
    DamageModifierTerm,
    DamageQuery,
    DamageRequest,
    DebugDamageAdjustment,
    DefenseResolution,
    GeneralDamageResolution,
    LunarReactionComponentResolution,
    LunarReactionDamageInput,
    LunarReactionDamageResolution,
    LunarReactionParticipantInput,
    ResistanceResolution,
    ScalingZoneResolution,
    SecondaryAmplifyingReactionResolution,
    TransformativeReactionResolution,
    validate_damage_float,
)
from genshin_sim.core.systems.damage.modifiers import DamageModifierCollection
from genshin_sim.core.systems.damage.policies import (
    CriticalZonePolicy,
    DamageBonusZonePolicy,
    GeneralReactionZonePolicy,
    ScalingZonePolicy,
    StandardCriticalZonePolicy,
    StandardDamageBonusZonePolicy,
    StandardDefensePolicy,
    StandardGeneralReactionZonePolicy,
    StandardResistancePolicy,
    StandardScalingZonePolicy,
)

if TYPE_CHECKING:
    from genshin_sim.core.systems.damage.resolver import DamageResolutionSession


GENERAL_ALLOWED_MODIFIER_STAGES = frozenset(
    {
        DamageModifierStage.COMPONENT_COEFFICIENT_PERCENT_ADD,
        DamageModifierStage.COMPONENT_COEFFICIENT_FLAT_ADD,
        DamageModifierStage.BASE_DAMAGE_FLAT_ADD,
        DamageModifierStage.DAMAGE_BONUS_ADD,
        DamageModifierStage.DEFENSE_REDUCTION,
        DamageModifierStage.DEFENSE_IGNORE,
        DamageModifierStage.CRIT_RATE_ADD,
        DamageModifierStage.CRIT_DAMAGE_ADD,
        DamageModifierStage.RESISTANCE_ADD,
    }
)
TRANSFORMATIVE_ALLOWED_MODIFIER_STAGES = frozenset[DamageModifierStage]()


@dataclass(frozen=True, slots=True)
class DamageFormulaSpec:
    """完整公式的稳定类型和允许的 modifier stage。"""

    formula_key: str
    allowed_modifier_stages: frozenset[DamageModifierStage]

    def __post_init__(self) -> None:
        """冻结 stage 声明并校验公式键。"""

        if self.formula_key not in KNOWN_FORMULA_KEYS:
            raise DamageFormulaInputError("damage formula spec 的 formula_key 不受支持")
        if any(
            not isinstance(stage, DamageModifierStage) for stage in self.allowed_modifier_stages
        ):
            raise DamageFormulaInputError("damage formula spec 包含非法 modifier stage")
        object.__setattr__(self, "allowed_modifier_stages", frozenset(self.allowed_modifier_stages))


@dataclass(frozen=True, slots=True)
class DamageFormulaContext:
    """resolver 传给完整公式的受限结算上下文。"""

    query: DamageQuery
    session: DamageResolutionSession
    modifiers: DamageModifierCollection
    trace_level: TraceLevel


class DamageFormula(Protocol):
    """完整伤害公式协议。"""

    @property
    def formula_spec(self) -> DamageFormulaSpec:
        """返回公式对应的伤害类型和允许 modifier stage。"""

        ...

    def resolve(self, context: DamageFormulaContext) -> DamageFormulaResolution:
        """执行完整公式并返回公式专属审计结果。"""

        ...


class DamageFormulaRegistry:
    """按伤害类型保存完整公式的稳定注册表。"""

    def __init__(self, formulas: Sequence[DamageFormula]) -> None:
        """注册公式并拒绝重复公式键。"""

        self._formulas: dict[str, DamageFormula] = {}
        for formula in formulas:
            formula_key = formula.formula_spec.formula_key
            if formula_key in self._formulas:
                raise DuplicateDamageFormulaError(f"重复伤害公式：{formula_key}")
            self._formulas[formula_key] = formula

    def require(self, formula_key: str) -> DamageFormula:
        """返回指定公式键的完整公式；未注册时明确失败。"""

        try:
            return self._formulas[formula_key]
        except KeyError as exc:
            raise UnsupportedDamageFormulaError(f"未注册的伤害公式：{formula_key}") from exc


@dataclass(frozen=True, slots=True)
class GeneralDamageFormula:
    """普通直伤与未来增幅反应共用的通用完整公式。"""

    scaling_policy: ScalingZonePolicy = field(default_factory=StandardScalingZonePolicy)
    damage_bonus_policy: DamageBonusZonePolicy = field(
        default_factory=StandardDamageBonusZonePolicy
    )
    critical_policy: CriticalZonePolicy = field(default_factory=StandardCriticalZonePolicy)
    reaction_policy: GeneralReactionZonePolicy = field(
        default_factory=StandardGeneralReactionZonePolicy
    )
    defense_policy: StandardDefensePolicy = field(default_factory=StandardDefensePolicy)
    resistance_policy: StandardResistancePolicy = field(default_factory=StandardResistancePolicy)
    debug_adjustment: DebugDamageAdjustment = field(default_factory=DebugDamageAdjustment)

    @property
    def formula_spec(self) -> DamageFormulaSpec:
        """通用公式第一轮允许全部正式直伤 modifier stage。"""

        return DamageFormulaSpec(
            formula_key=FORMULA_KEY_GENERAL,
            allowed_modifier_stages=GENERAL_ALLOWED_MODIFIER_STAGES,
        )

    def resolve(self, context: DamageFormulaContext) -> GeneralDamageResolution:
        """按倍率、增伤、暴击、反应、防御和抗性区计算通用伤害。"""

        query = context.query
        if query.request.formula_key is not FORMULA_KEY_GENERAL:
            raise DamageFormulaInputError("GeneralDamageFormula 只能处理 GENERAL 伤害")
        if query.request.flat_base_damage < 0:
            raise InvalidDamageScalingError("普通直伤 flat_base_damage 不能为负数")
        if not query.request.scaling_terms and query.request.flat_base_damage == 0:
            raise InvalidDamageScalingError("普通直伤必须包含 scaling term 或固定基础伤害")
        terms = context.modifiers.applied_terms
        source_trace: list[AttributeResolution] = []

        scaling, scaling_trace = self.scaling_policy.resolve(query, context.session, terms)
        source_trace.extend(scaling_trace)

        catalyze_resolution = None
        catalyze_input = query.request.catalyze_reaction
        if catalyze_input is not None:
            if query.request.amplifying_reaction is not None:
                raise DamageFormulaInputError("通用公式不能同时携带增幅与激化输入")
            if catalyze_input.trigger_element.value != query.request.element.value:
                raise DamageFormulaInputError("激化 trigger_element 必须匹配当前伤害元素")
            table_key, level_multiplier = transformative_level_multiplier(
                TransformativeReactionSourceKind.CHARACTER,
                query.request.source_level,
            )
            mastery_trace = context.session.resolve_source(STAT_ELEMENTAL_MASTERY)
            mastery = validate_damage_float(mastery_trace.final_value, "elemental_mastery")
            if mastery < 0:
                raise DamageResolutionError("元素精通不能为负数")
            mastery_bonus = 5 * mastery / (1200 + mastery)
            addition_value = (
                level_multiplier
                * catalyze_input.reaction_multiplier
                * (1 + mastery_bonus + catalyze_input.reaction_bonus)
            )
            if not math.isfinite(addition_value) or addition_value < 0:
                raise DamageResolutionError("激化基础伤害附加值必须是有限非负数")
            addition = BaseDamageAddition(
                addition_key=f"catalyze.{catalyze_input.reaction_profile_key}",
                value=addition_value,
                source_ref=RuntimeSourceRef(
                    RuntimeSourceKind.MECHANIC,
                    catalyze_input.reaction_profile_key,
                    catalyze_input.occurrence_ref,
                ),
                audit_tags=("catalyze", catalyze_input.reaction_profile_key),
            )
            catalyze_resolution = CatalyzeReactionResolution(
                target_impact_ref=catalyze_input.target_impact_ref,
                occurrence_ref=catalyze_input.occurrence_ref,
                reaction_profile_key=catalyze_input.reaction_profile_key,
                trigger_element=catalyze_input.trigger_element,
                source_level=query.request.source_level,
                level_multiplier_table_key=table_key,
                level_multiplier=level_multiplier,
                elemental_mastery=mastery,
                mastery_bonus=mastery_bonus,
                reaction_multiplier=catalyze_input.reaction_multiplier,
                reaction_bonus=catalyze_input.reaction_bonus,
                base_damage_addition=addition,
                elemental_mastery_trace=mastery_trace,
            )
            source_trace.append(mastery_trace)
            additions = (*scaling.additions, addition)
            scaling = ScalingZoneResolution(
                component_results=scaling.component_results,
                additions=additions,
                value=math.fsum(
                    (
                        *(component.damage for component in scaling.component_results),
                        *(item.value for item in additions),
                    )
                ),
            )

        damage_bonus, damage_bonus_trace = self.damage_bonus_policy.resolve(
            query,
            context.session,
            terms,
        )
        source_trace.append(damage_bonus_trace)

        critical, critical_trace = self.critical_policy.resolve(query, context.session, terms)
        source_trace.extend(critical_trace)

        reaction = self.reaction_policy.resolve(query, context.session)
        if reaction.elemental_mastery_trace is not None:
            source_trace.append(reaction.elemental_mastery_trace)
        defense = self.defense_policy.resolve(
            query.request.source_level,
            query.request.target_level,
            _sum_terms(terms, DamageModifierStage.DEFENSE_REDUCTION),
            _sum_terms(terms, DamageModifierStage.DEFENSE_IGNORE),
        )

        resistance_resolution = context.session.resolve_target(
            ELEMENT_TO_RESISTANCE_KEY[query.request.element.value]
        )
        resistance_add = _sum_terms(terms, DamageModifierStage.RESISTANCE_ADD)
        resistance = self.resistance_policy.resolve(
            resistance_resolution.final_value + resistance_add,
            base_resistance=resistance_resolution.final_value,
            resistance_add=resistance_add,
        )

        official_damage = (
            scaling.value
            * damage_bonus.multiplier
            * critical.multiplier
            * reaction.multiplier
            * defense.multiplier
            * resistance.multiplier
        )
        if not math.isfinite(official_damage) or official_damage < 0:
            raise DamageResolutionError("正式伤害必须是有限非负数")
        debug_multiplier = self.debug_adjustment.multiplier
        final_damage = official_damage * debug_multiplier
        if not math.isfinite(final_damage) or final_damage < 0:
            raise DamageResolutionError("最终伤害必须是有限非负数")
        return GeneralDamageResolution(
            scaling=scaling,
            damage_bonus=damage_bonus,
            critical=critical,
            reaction=reaction,
            defense=defense,
            resistance=resistance,
            official_damage=official_damage,
            debug_multiplier=debug_multiplier,
            final_damage=final_damage,
            source_attribute_trace=tuple(_unique_resolutions(source_trace)),
            target_attribute_trace=(resistance_resolution,),
            catalyze=catalyze_resolution,
        )


@dataclass(frozen=True, slots=True)
class TransformativeReactionDamageFormula:
    """普通剧变伤害的固定公式。

    该公式刻意不接入普通倍率、增伤、暴击或标准防御区；这些字段若进入
    ``DamageRequest`` 会在模型层直接拒绝，避免常规直伤字段悄然参与计算。
    """

    resistance_policy: StandardResistancePolicy = field(default_factory=StandardResistancePolicy)
    debug_adjustment: DebugDamageAdjustment = field(default_factory=DebugDamageAdjustment)

    @property
    def formula_spec(self) -> DamageFormulaSpec:
        return DamageFormulaSpec(
            formula_key=FORMULA_KEY_TRANSFORMATIVE_REACTION,
            allowed_modifier_stages=TRANSFORMATIVE_ALLOWED_MODIFIER_STAGES,
        )

    def resolve(self, context: DamageFormulaContext) -> TransformativeReactionResolution:
        query = context.query
        request = query.request
        if request.formula_key is not FORMULA_KEY_TRANSFORMATIVE_REACTION:
            raise DamageFormulaInputError("TransformativeReactionDamageFormula 只能处理剧变伤害")
        reaction = request.transformative_reaction
        if reaction is None:
            raise DamageFormulaInputError("剧变伤害缺少 TransformativeReactionInput")
        if context.modifiers.applied_terms or context.modifiers.rejected_terms:
            raise DamageFormulaInputError("剧变伤害不能使用普通伤害 modifier")

        resistance_attribute = context.session.resolve_target(
            ELEMENT_TO_RESISTANCE_KEY[request.element.value]
        )
        resistance = self.resistance_policy.resolve(resistance_attribute.final_value)
        secondary_resolution = None
        secondary_multiplier = 1.0
        secondary_reaction = request.secondary_amplifying_reaction
        if secondary_reaction is not None:
            mastery_bonus = (
                2.78
                * secondary_reaction.captured_elemental_mastery
                / (secondary_reaction.captured_elemental_mastery + 1400)
            )
            secondary_multiplier = secondary_reaction.base_multiplier * (
                1 + mastery_bonus + secondary_reaction.reaction_bonus
            )
            secondary_resolution = SecondaryAmplifyingReactionResolution(
                reaction=secondary_reaction,
                mastery_bonus=mastery_bonus,
                multiplier=secondary_multiplier,
            )
        damage = (
            reaction.level_multiplier
            * reaction.base_multiplier
            * (1 + reaction.mastery_bonus + reaction.reaction_bonus)
            * secondary_multiplier
            * resistance.multiplier
        )
        if not math.isfinite(damage) or damage < 0:
            raise DamageResolutionError("剧变正式伤害必须是有限非负数")
        final_damage = damage * self.debug_adjustment.multiplier
        if not math.isfinite(final_damage) or final_damage < 0:
            raise DamageResolutionError("剧变最终伤害必须是有限非负数")
        return TransformativeReactionResolution(
            reaction=reaction,
            defense=DefenseResolution(
                source_level=reaction.source_level,
                target_level=request.target_level,
                defense_reduction=0.0,
                defense_ignore=0.0,
                multiplier=1.0,
            ),
            resistance=ResistanceResolution(
                resistance=resistance.resistance,
                multiplier=resistance.multiplier,
            ),
            official_damage=damage,
            debug_multiplier=self.debug_adjustment.multiplier,
            final_damage=final_damage,
            target_attribute_trace=(resistance_attribute,),
            secondary_amplifying_resolution=secondary_resolution,
        )


@dataclass(frozen=True, slots=True)
class LunarReactionDamageFormula:
    """月曜单来源与多来源组分的完整伤害公式。

    该公式只负责已经冻结的参与者和显式公式参数。等级基数与精通系数默认
    使用已确认资料中的生产数值，也可以通过构造参数覆盖。
    """

    level_base_damage: Mapping[int, float]
    mastery_numerator: float
    mastery_denominator: float
    critical_policy: CriticalZonePolicy = field(default_factory=StandardCriticalZonePolicy)
    resistance_policy: StandardResistancePolicy = field(default_factory=StandardResistancePolicy)
    debug_adjustment: DebugDamageAdjustment = field(default_factory=DebugDamageAdjustment)

    def __post_init__(self) -> None:
        table = dict(self.level_base_damage)
        for level, value in table.items():
            if isinstance(level, bool) or not isinstance(level, int) or level <= 0:
                raise DamageFormulaInputError("月曜等级基数表的等级必须是正整数")
            normalized = validate_damage_float(value, f"lunar level base {level}")
            if normalized <= 0:
                raise DamageFormulaInputError("月曜等级基数必须为正数")
            table[level] = normalized
        mastery_numerator = validate_damage_float(
            self.mastery_numerator,
            "lunar mastery_numerator",
        )
        mastery_denominator = validate_damage_float(
            self.mastery_denominator,
            "lunar mastery_denominator",
        )
        if mastery_numerator < 0 or mastery_denominator <= 0:
            raise DamageFormulaInputError("月曜精通系数必须合法")
        object.__setattr__(self, "level_base_damage", MappingProxyType(table))
        object.__setattr__(self, "mastery_numerator", mastery_numerator)
        object.__setattr__(self, "mastery_denominator", mastery_denominator)

    @property
    def formula_spec(self) -> DamageFormulaSpec:
        """月曜公式暂不接受普通 Damage modifier stage。"""

        return DamageFormulaSpec(
            formula_key=FORMULA_KEY_LUNAR_REACTION,
            allowed_modifier_stages=frozenset(),
        )

    def resolve(self, context: DamageFormulaContext) -> LunarReactionDamageResolution:
        """逐参与者完成组分公式，再执行稳定排序和权重聚合。"""

        query = context.query
        request = query.request
        if request.formula_key is not FORMULA_KEY_LUNAR_REACTION:
            raise DamageFormulaInputError("LunarReactionDamageFormula 只能处理月曜伤害")
        reaction = request.lunar_reaction
        if reaction is None:
            raise DamageFormulaInputError("月曜伤害缺少 LunarReactionDamageInput")
        if context.modifiers.applied_terms or context.modifiers.rejected_terms:
            raise DamageFormulaInputError("月曜伤害暂不接受普通 Damage modifier")
        if reaction.mode is LunarReactionDamageMode.CHARACTER_DIRECT:
            participant = reaction.participants[0]
            if not participant.scaling_terms and participant.flat_base_damage == 0:
                raise DamageFormulaInputError("角色直接月曜伤害必须提供属性倍率或固定基础伤害")

        raw_components = tuple(
            self._resolve_component(context, query, reaction, participant)
            for participant in reaction.participants
        )
        ordered_components = tuple(
            sorted(
                raw_components,
                key=lambda item: (-item.component_damage, item.participant_ref.entity_id),
            )
        )
        weighted_components = tuple(
            replace(
                component,
                weight=_lunar_component_weight(reaction.mode, index),
                weighted_damage=component.component_damage
                * _lunar_component_weight(reaction.mode, index),
            )
            for index, component in enumerate(ordered_components)
        )
        weighted_base_damage = math.fsum(
            component.base_damage_after_reaction * component.weight
            for component in weighted_components
        )
        official_damage = math.fsum(component.weighted_damage for component in weighted_components)
        debug_multiplier = self.debug_adjustment.multiplier
        final_damage = official_damage * debug_multiplier
        if not math.isfinite(final_damage) or final_damage < 0:
            raise DamageResolutionError("月曜最终伤害必须是有限非负数")

        source_trace = [
            trace for component in weighted_components for trace in component.source_attribute_trace
        ]
        target_trace = [
            trace for component in weighted_components for trace in component.target_attribute_trace
        ]
        return LunarReactionDamageResolution(
            reaction=reaction,
            components=weighted_components,
            weighted_base_damage=weighted_base_damage,
            resistance=weighted_components[0].resistance,
            official_damage=official_damage,
            debug_multiplier=debug_multiplier,
            final_damage=final_damage,
            source_attribute_trace=tuple(_unique_resolutions(source_trace)),
            target_attribute_trace=tuple(_unique_resolutions(target_trace)),
        )

    def _resolve_component(
        self,
        context: DamageFormulaContext,
        query: DamageQuery,
        reaction: LunarReactionDamageInput,
        participant: LunarReactionParticipantInput,
    ) -> LunarReactionComponentResolution:
        component_query = _lunar_component_query(query, reaction, participant)
        component_session = _new_damage_session(context, component_query)
        source_trace: list[AttributeResolution] = []
        scaling = None
        if participant.scaling_terms or participant.flat_base_damage != 0:
            scaling, scaling_trace = StandardScalingZonePolicy().resolve(
                component_query,
                component_session,
                (),
            )
            core_base_damage = scaling.value
            source_trace.extend(scaling_trace)
            base_damage_source = "participant_scaling"
        else:
            try:
                core_base_damage = self.level_base_damage[participant.source_level]
            except KeyError as exc:
                raise DamageFormulaInputError(
                    f"月曜等级基数表缺少等级：{participant.source_level}"
                ) from exc
            base_damage_source = f"level_base:{participant.source_level}"

        mastery_trace = component_session.resolve_source(STAT_ELEMENTAL_MASTERY)
        elemental_mastery = validate_damage_float(
            mastery_trace.final_value,
            "lunar elemental_mastery",
        )
        if elemental_mastery < 0:
            raise DamageResolutionError("月曜元素精通不能为负数")
        mastery_bonus = (
            self.mastery_numerator
            * elemental_mastery
            / (elemental_mastery + self.mastery_denominator)
        )
        reaction_uplift_multiplier = 1 + mastery_bonus + reaction.reaction_bonus
        if reaction_uplift_multiplier <= 0:
            raise DamageResolutionError("月曜反应提升乘数必须为正数")
        base_damage_after_reaction = (
            core_base_damage
            * reaction.reaction_multiplier
            * (1 + reaction.base_damage_bonus)
            * reaction_uplift_multiplier
            + participant.additional_base_damage
        )
        if base_damage_after_reaction < 0:
            raise DamageResolutionError("月曜基础伤害区不能为负数")

        critical, critical_trace = self.critical_policy.resolve(
            component_query,
            component_session,
            (),
        )
        source_trace.append(mastery_trace)
        source_trace.extend(critical_trace)
        resistance_attribute = component_session.resolve_target(
            ELEMENT_TO_RESISTANCE_KEY[component_query.request.element.value]
        )
        resistance = self.resistance_policy.resolve(resistance_attribute.final_value)
        component_damage = (
            base_damage_after_reaction
            * critical.multiplier
            * participant.ascension_multiplier
            * resistance.multiplier
        )
        if not math.isfinite(component_damage) or component_damage < 0:
            raise DamageResolutionError("月曜组分伤害必须是有限非负数")
        if context.trace_level is TraceLevel.NONE:
            source_attribute_trace = ()
            target_attribute_trace = ()
        else:
            source_attribute_trace = tuple(_unique_resolutions(source_trace))
            target_attribute_trace = (resistance_attribute,)
        return LunarReactionComponentResolution(
            participant_ref=participant.participant_ref,
            source_level=participant.source_level,
            base_damage_source=base_damage_source,
            scaling=scaling,
            core_base_damage=core_base_damage,
            reaction_multiplier=reaction.reaction_multiplier,
            base_damage_bonus=reaction.base_damage_bonus,
            elemental_mastery=elemental_mastery,
            mastery_bonus=mastery_bonus,
            reaction_bonus=reaction.reaction_bonus,
            reaction_uplift_multiplier=reaction_uplift_multiplier,
            base_damage_after_reaction=base_damage_after_reaction,
            additional_base_damage=participant.additional_base_damage,
            critical=critical,
            ascension_multiplier=participant.ascension_multiplier,
            resistance=resistance,
            component_damage=component_damage,
            weight=0.0,
            weighted_damage=0.0,
            source_attribute_trace=source_attribute_trace,
            target_attribute_trace=target_attribute_trace,
        )


def _lunar_component_query(
    query: DamageQuery,
    reaction: LunarReactionDamageInput,
    participant: LunarReactionParticipantInput,
) -> DamageQuery:
    """为一个月曜角色组分创建独立的属性查询。"""

    request = query.request
    component_request = DamageRequest(
        request_id=f"{request.request_id}:participant:{participant.participant_ref.entity_id}",
        frame=request.frame,
        formula_key=FORMULA_KEY_GENERAL,
        main_attack_tag=request.main_attack_tag,
        impact_key=request.impact_key,
        source_ref=participant.participant_ref,
        target_ref=request.target_ref,
        source_level=participant.source_level,
        target_level=request.target_level,
        element=request.element,
        source_context=request.source_context,
        scaling_terms=participant.scaling_terms,
        flat_base_damage=participant.flat_base_damage,
        tags=frozenset((*request.tags, reaction.reaction_profile_key)),
        can_crit=participant.can_crit,
    )
    tags = component_request.tags
    return DamageQuery(
        request=component_request,
        source_attribute_context=AttributeQueryContext(
            tags=tags,
            source_ref=request.source_context,
            target_ref=request.target_ref,
        ),
        target_attribute_context=AttributeQueryContext(
            tags=tags,
            source_ref=request.source_context,
            target_ref=participant.participant_ref,
        ),
    )


def _new_damage_session(
    context: DamageFormulaContext,
    query: DamageQuery,
):
    """创建不共享来源主体的组分属性 session。"""

    from genshin_sim.core.systems.damage.resolver import DamageResolutionSession

    return DamageResolutionSession(
        context.session.attribute_resolver,
        query,
        context.trace_level,
    )


def _lunar_component_weight(mode: LunarReactionDamageMode, index: int) -> float:
    """返回月曜复合伤害按完整组分排序后的固定权重。"""

    if mode is LunarReactionDamageMode.CHARACTER_DIRECT:
        return 1.0
    if index == 0:
        return 0.60
    if index == 1:
        return 0.30
    return 0.05


PRODUCTION_LUNAR_REACTION_LEVEL_BASE_DAMAGE: Mapping[int, float] = {
    80: 1077.4,
    90: 1446.9,
    95: 1561.5,
    100: 1674.8,
}
PRODUCTION_LUNAR_MASTERY_NUMERATOR = 6.0
PRODUCTION_LUNAR_MASTERY_DENOMINATOR = 2000.0


def create_default_damage_formula_registry(
    *,
    lunar_formula: LunarReactionDamageFormula | None = None,
) -> DamageFormulaRegistry:
    """创建生产默认公式注册表；月曜公式默认使用已确认的生产数值。

    ``lunar_formula`` 仅供测试或未来配置覆盖生产默认值。
    """

    formulas: list[DamageFormula] = [
        GeneralDamageFormula(),
        TransformativeReactionDamageFormula(),
    ]
    formulas.append(
        lunar_formula
        if lunar_formula is not None
        else LunarReactionDamageFormula(
            level_base_damage=PRODUCTION_LUNAR_REACTION_LEVEL_BASE_DAMAGE,
            mastery_numerator=PRODUCTION_LUNAR_MASTERY_NUMERATOR,
            mastery_denominator=PRODUCTION_LUNAR_MASTERY_DENOMINATOR,
        )
    )
    return DamageFormulaRegistry(tuple(formulas))


def _sum_terms(
    terms: tuple[DamageModifierTerm, ...],
    stage: DamageModifierStage,
) -> float:
    """使用 ``math.fsum`` 汇总指定阶段的修饰项数值。"""

    return math.fsum(term.value for term in terms if term.stage is stage)


def _unique_resolutions(
    resolutions: list[AttributeResolution],
) -> tuple[AttributeResolution, ...]:
    """保留首次出现的属性解析结果，避免 trace 重复记录。"""

    result: list[AttributeResolution] = []
    identities: set[tuple[object, ...]] = set()
    for resolution in resolutions:
        identity = (resolution.subject_ref, resolution.attribute_key)
        if identity in identities:
            continue
        identities.add(identity)
        result.append(resolution)
    return tuple(result)
