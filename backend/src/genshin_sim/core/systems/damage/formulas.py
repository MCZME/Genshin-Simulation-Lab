"""完整伤害公式协议、注册表和通用公式实现。"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol

from genshin_sim.core.attributes import (
    ELEMENT_TO_RESISTANCE_KEY,
    STAT_ELEMENTAL_MASTERY,
    AttributeQueryContext,
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
    DamageProviderViolationError,
    DamageResolutionError,
    DuplicateDamageFormulaError,
    InvalidDamageScalingError,
    UnsupportedDamageFormulaError,
)
from genshin_sim.core.systems.damage.keys import (
    FORMULA_KEY_GENERAL,
    FORMULA_KEY_LUNAR_REACTION,
    FORMULA_KEY_STELLAR_REACTION,
    FORMULA_KEY_TRANSFORMATIVE_REACTION,
    KNOWN_FORMULA_KEYS,
)
from genshin_sim.core.systems.damage.level_multipliers import transformative_level_multiplier
from genshin_sim.core.systems.damage.lunar import (
    LUNAR_COMPOSITE_WEIGHTS,
    LUNAR_SLOT_ADDITIONAL_BASE_DAMAGE,
    LUNAR_SLOT_ASCENSION_MULTIPLIER,
    LUNAR_SLOT_BASE_DAMAGE_BONUS,
    LUNAR_SLOT_REACTION_BONUS,
    LunarZoneSlotAudit,
    resolve_lunar_zone_damage,
)
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
    ScalingZoneResolution,
    SecondaryAmplifyingReactionResolution,
    TransformativeReactionResolution,
    validate_damage_float,
)
from genshin_sim.core.systems.damage.modifiers import DamageModifierCollection
from genshin_sim.core.systems.damage.policies import (
    CriticalDecisionProvider,
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
from genshin_sim.core.systems.damage.stellar import (
    STELLAR_COMPOSITE_PARTICIPANT_LIMIT,
    STELLAR_SLOT_ASCENSION_BONUS,
    STELLAR_SLOT_AUTHORITY_MULTIPLIER,
    STELLAR_SLOT_BASE_BONUS,
    STELLAR_SLOT_BASE_MULTIPLIER,
    STELLAR_SLOT_FEATHER_ADDITION,
    STELLAR_SLOT_REACTION_BONUS,
    StellarReactionComponentResolution,
    StellarReactionDamageInput,
    StellarReactionDamageResolution,
    StellarReactionParticipantInput,
    StellarZoneSlotAudit,
    resolve_stellar_zone_damage,
)

if TYPE_CHECKING:
    from genshin_sim.core.systems.damage.resolver import DamageResolutionScope

    # 组分查询的修饰收集入口签名：由 resolver 注入 ``index.collect``。
    DamageModifierCollector = Callable[
        [DamageQuery, DamageResolutionScope], DamageModifierCollection
    ]


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
TRANSFORMATIVE_ALLOWED_MODIFIER_STAGES = frozenset(
    {
        DamageModifierStage.TRANSFORMATIVE_REACTION_BONUS_ADD,
        # 抗性位与通用公式的位置相同，复用通用阶段。公式体必须先把
        # 「目标面板抗性 + Σ」合并成有效抗性再传策略，否则是零效果阶段。
        DamageModifierStage.RESISTANCE_ADD,
    }
)
STELLAR_ALLOWED_MODIFIER_STAGES = frozenset(
    {
        # 倍率：与通用公式的位置相同，复用通用阶段，需绑定 component_key。
        DamageModifierStage.COMPONENT_COEFFICIENT_PERCENT_ADD,
        DamageModifierStage.COMPONENT_COEFFICIENT_FLAT_ADD,
        # 基础系数：基线是机制按层数/反应类型冻结的乘数，没有面板来源。
        DamageModifierStage.STELLAR_BASE_MULTIPLIER_ADD,
        # 基础增伤：乘性括号 (1 + Σ)，与月曜的基础伤害提升同形。
        DamageModifierStage.STELLAR_BASE_BONUS_ADD,
        # 精通和增伤区：精通由面板读取，本阶段只贡献反应增伤部分。
        DamageModifierStage.STELLAR_REACTION_BONUS_ADD,
        # 大权区乘数：没有面板来源，内容效果是它唯一的贡献入口，
        # 与增伤位阶段分处不同乘区。
        DamageModifierStage.STELLAR_AUTHORITY_MULTIPLIER_ADD,
        # 羽毛区：形状与通用 base_damage_flat_add 相似但宿主乘区不同
        # （星烁羽毛不被基础系数/基础增伤/精通增伤区/大权区乘算），因此另设专属阶段。
        DamageModifierStage.STELLAR_FEATHER_ADDITION_ADD,
        # 暴击区：暴击率与暴击伤害都读取面板，复用通用阶段，
        # 作用范围由 provider 自筛 formula_key 决定。
        DamageModifierStage.CRIT_RATE_ADD,
        DamageModifierStage.CRIT_DAMAGE_ADD,
        # 抗性区：与通用公式的位置相同，复用通用阶段。
        DamageModifierStage.RESISTANCE_ADD,
        # 擢升：乘性括号 (1 + Σ)，多个擢升来源互相加算。
        DamageModifierStage.STELLAR_ASCENSION_BONUS_ADD,
    }
)
# 月曜的倍率位与反应系数位刻意不放行：
# - 反应系数的系数是机制侧冻结的反应口径，没有内容侧来源；
# - 倍率位在复合模式下是机制冻结的等级基础伤害；直伤模式下倍率由**参与者**
#   的 scaling_terms 承载，而 ``DamageModifierIndex`` 校验 component_key 绑定时
#   以 ``query.request.scaling_terms`` 为已知 component 集合，请求级为空时顶层
#   收集会在进入公式前就拒绝绑定到参与者组件的 term。要开放它需把直伤倍率挪到
#   请求级，属契约变更，另行评估。白名单只列「可被内容真实产出并消费」的位置。
LUNAR_ALLOWED_MODIFIER_STAGES = frozenset(
    {
        # 基础伤害提升：乘性括号 (1 + Σ)，与星烁基础增伤同形；
        # 来源为各月兆角色的月兆祝赐（按攻击/精通/防御/生命缩放）。
        DamageModifierStage.LUNAR_BASE_DAMAGE_BONUS_ADD,
        # 反应加成：并入精通区的加算括号，与剧变、星烁的增伤位同形。
        DamageModifierStage.LUNAR_REACTION_BONUS_ADD,
        # 附加伤害：基础区括号内末项，不被反应倍率、基础伤害提升与
        # 精通提升乘算，只被暴击、擢升与抗性乘算；形状与星烁羽毛区同构。
        DamageModifierStage.LUNAR_ADDITIONAL_BASE_DAMAGE_ADD,
        # 擢升乘数：乘性括号 (1 + Σ)，多个擢升来源互相加算。
        DamageModifierStage.LUNAR_ASCENSION_BONUS_ADD,
        # 暴击区：暴击率与暴击伤害都读取面板，复用通用阶段，
        # 作用范围由 provider 自筛 formula_key 决定。
        DamageModifierStage.CRIT_RATE_ADD,
        DamageModifierStage.CRIT_DAMAGE_ADD,
        # 抗性区：与通用公式的位置相同，复用通用阶段。
        DamageModifierStage.RESISTANCE_ADD,
    }
)


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
    scope: DamageResolutionScope
    modifiers: DamageModifierCollection
    trace_level: TraceLevel
    # 组分查询的修饰收集入口：由 resolver 注入 index.collect，供逐参与者结算
    # 的公式对每个组分重新收集修饰。必填：复合路径的修饰完全由组分收集决定，
    # 缺少收集入口就没有修饰可言，不允许静默退化。
    modifier_collector: DamageModifierCollector


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
        panel_terms: list[DamageModifierTerm] = []

        scaling, scaling_panel_terms = self.scaling_policy.resolve(
            query,
            context.scope,
            terms,
        )
        panel_terms.extend(scaling_panel_terms)

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
            mastery_trace = context.scope.resolve_source(STAT_ELEMENTAL_MASTERY)
            mastery = validate_damage_float(mastery_trace.final_value, "elemental_mastery")
            if mastery < 0:
                raise DamageResolutionError("元素精通不能为负数")
            panel_terms.append(
                DamageModifierTerm.panel_read(
                    stage=DamageModifierStage.PANEL_ELEMENTAL_MASTERY,
                    attribute=mastery_trace,
                )
            )
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
            )
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

        damage_bonus, bonus_panel_term = self.damage_bonus_policy.resolve(
            query,
            context.scope,
            terms,
        )
        panel_terms.append(bonus_panel_term)

        critical, critical_panel_terms = self.critical_policy.resolve(
            query,
            context.scope,
            terms,
        )
        panel_terms.extend(critical_panel_terms)

        reaction, reaction_panel_term = self.reaction_policy.resolve(query, context.scope)
        if reaction_panel_term is not None:
            panel_terms.append(reaction_panel_term)
        defense = self.defense_policy.resolve(
            query.request.source_level,
            query.request.target_level,
            _sum_terms(terms, DamageModifierStage.DEFENSE_REDUCTION),
            _sum_terms(terms, DamageModifierStage.DEFENSE_IGNORE),
        )

        resistance_resolution = context.scope.resolve_target(
            ELEMENT_TO_RESISTANCE_KEY[query.request.element.value]
        )
        resistance_panel_term = DamageModifierTerm.panel_read(
            stage=DamageModifierStage.PANEL_RESISTANCE,
            attribute=resistance_resolution,
        )
        panel_terms.append(resistance_panel_term)
        resistance_add = _sum_terms(terms, DamageModifierStage.RESISTANCE_ADD)
        resistance = self.resistance_policy.resolve(
            resistance_panel_term.value + resistance_add,
            base_resistance=resistance_panel_term.value,
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
            catalyze=catalyze_resolution,
            panel_terms=tuple(panel_terms),
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
        validate_formula_modifier_stages(self.formula_spec, context.modifiers)
        modifier_terms = context.modifiers.applied_terms
        reaction_bonus = reaction.reaction_bonus + _sum_terms(
            modifier_terms,
            DamageModifierStage.TRANSFORMATIVE_REACTION_BONUS_ADD,
        )

        resistance_attribute = context.scope.resolve_target(
            ELEMENT_TO_RESISTANCE_KEY[request.element.value]
        )
        # 抗性位复用通用阶段：先把「目标面板抗性 + Σ」合并成有效抗性再传策略，
        # 否则阶段只进白名单而不被消费，会是零效果阶段。
        resistance_panel_term = DamageModifierTerm.panel_read(
            stage=DamageModifierStage.PANEL_RESISTANCE,
            attribute=resistance_attribute,
        )
        resistance_add = _sum_terms(modifier_terms, DamageModifierStage.RESISTANCE_ADD)
        resistance = self.resistance_policy.resolve(
            resistance_panel_term.value + resistance_add,
            base_resistance=resistance_panel_term.value,
            resistance_add=resistance_add,
        )
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
            * (1 + reaction.mastery_bonus + reaction_bonus)
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
            # 直接传策略结果，保留 base_resistance / resistance_add 审计。
            resistance=resistance,
            official_damage=damage,
            debug_multiplier=self.debug_adjustment.multiplier,
            final_damage=final_damage,
            panel_terms=(resistance_panel_term,),
            secondary_amplifying_resolution=secondary_resolution,
        )


@dataclass(frozen=True, slots=True)
class LunarReactionDamageFormula:
    """月曜单来源与多来源组分的完整伤害公式。

    月曜与通用公式共用同一套槽位账单：精通由面板读取，暴击与抗性复用通用阶段，
    基础伤害提升、反应加成、附加伤害与擢升使用月曜专属阶段。等级基数与精通系数
    默认为已确认资料中的生产数值，也可以通过构造参数覆盖。
    """

    level_base_damage: Mapping[int, float]
    mastery_numerator: float
    mastery_denominator: float
    scaling_policy: ScalingZonePolicy = field(default_factory=StandardScalingZonePolicy)
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
        """月曜公式按位置放行月曜专属阶段与对应的通用直伤阶段。"""

        return DamageFormulaSpec(
            formula_key=FORMULA_KEY_LUNAR_REACTION,
            allowed_modifier_stages=LUNAR_ALLOWED_MODIFIER_STAGES,
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
        # 请求级倍率与固定基础伤害在月曜公式中没有位置：倍率由参与者的
        # scaling_terms 承载，因此只能出现在参与者的组分查询上。
        if request.scaling_terms or request.flat_base_damage != 0:
            raise DamageFormulaInputError("月曜伤害的倍率必须由参与者承载，请求级不得携带")
        validate_formula_modifier_stages(self.formula_spec, context.modifiers)
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

        # 直伤模式只有一个参与者，槽位账本因此可以提到顶层；复合模式的账本在
        # 组分内各自保留，顶层不重复列入，避免同一词条被署名两次。
        top = weighted_components[0]
        direct = reaction.mode is LunarReactionDamageMode.CHARACTER_DIRECT
        return LunarReactionDamageResolution(
            reaction=reaction,
            components=weighted_components,
            weighted_base_damage=weighted_base_damage,
            resistance=top.resistance,
            official_damage=official_damage,
            debug_multiplier=debug_multiplier,
            final_damage=final_damage,
            slots=top.slots if direct else (),
            panel_terms=top.panel_terms if direct else (),
        )

    def _resolve_component(
        self,
        context: DamageFormulaContext,
        query: DamageQuery,
        reaction: LunarReactionDamageInput,
        participant: LunarReactionParticipantInput,
    ) -> LunarReactionComponentResolution:
        """按月曜位置组装一个组分，并把槽位合并值与账本一起写进审计。"""

        component_query = _lunar_component_query(query, reaction, participant)
        component_session = _new_damage_session(context, component_query)
        # 逐参与者重新收集：组分查询的来源主体是该参与者，因此按 source_ref
        # 自筛的 provider 只对它自己这份生效；不按来源过滤的 provider 则
        # 对每个参与者各贡献一次（队伍级效果的既有语义）。
        component_modifiers = context.modifier_collector(component_query, component_session)
        validate_formula_modifier_stages(self.formula_spec, component_modifiers)
        component_terms = component_modifiers.applied_terms
        panel_terms: list[DamageModifierTerm] = []

        # 倍率：直伤模式的系数与属性分别由参与者 scaling_terms 的
        # coefficient 与 attribute_key 承载，因此可以被各自独立地修饰；反应复合
        # 模式没有 scaling_terms，基线是机制侧冻结的等级基础伤害，无内容侧来源。
        scaling = None
        if participant.scaling_terms or participant.flat_base_damage != 0:
            scaling, scaling_panel_terms = self.scaling_policy.resolve(
                component_query,
                component_session,
                component_terms,
            )
            core_base_damage = scaling.value
            panel_terms.extend(scaling_panel_terms)
            base_damage_source = "participant_scaling"
        else:
            try:
                core_base_damage = self.level_base_damage[participant.source_level]
            except KeyError as exc:
                raise DamageFormulaInputError(
                    f"月曜等级基数表缺少等级：{participant.source_level}"
                ) from exc
            base_damage_source = f"level_base:{participant.source_level}"

        # 精通：面板读取物化为账本词条，精通加成由它派生。
        mastery_trace = component_session.resolve_source(STAT_ELEMENTAL_MASTERY)
        elemental_mastery = validate_damage_float(
            mastery_trace.final_value,
            "lunar elemental_mastery",
        )
        if elemental_mastery < 0:
            raise DamageResolutionError("月曜元素精通不能为负数")
        panel_terms.append(
            DamageModifierTerm.panel_read(
                stage=DamageModifierStage.PANEL_ELEMENTAL_MASTERY,
                attribute=mastery_trace,
            )
        )
        mastery_bonus = (
            self.mastery_numerator
            * elemental_mastery
            / (elemental_mastery + self.mastery_denominator)
        )

        # 暴击区：暴击率与暴击伤害都从面板读取，复用通用阶段。
        critical, critical_panel_terms = self.critical_policy.resolve(
            component_query,
            component_session,
            component_terms,
        )
        panel_terms.extend(critical_panel_terms)

        # 抗性区：有效抗性由面板值加修饰项合计得到。
        resistance_attribute = component_session.resolve_target(
            ELEMENT_TO_RESISTANCE_KEY[component_query.request.element.value]
        )
        resistance_panel_term = DamageModifierTerm.panel_read(
            stage=DamageModifierStage.PANEL_RESISTANCE,
            attribute=resistance_attribute,
        )
        panel_terms.append(resistance_panel_term)
        resistance_add = _sum_terms(component_terms, DamageModifierStage.RESISTANCE_ADD)
        resistance = self.resistance_policy.resolve(
            resistance_panel_term.value + resistance_add,
            base_resistance=resistance_panel_term.value,
            resistance_add=resistance_add,
        )

        # 基础伤害提升、反应加成、附加伤害与擢升：机制侧冻结基线 + 槽位账单修饰项
        # 合计。擢升取加算口径——多个擢升来源互相加算，基线为无擢升时的乘数 1。
        slots = (
            _merge_lunar_slot(
                LUNAR_SLOT_BASE_DAMAGE_BONUS,
                reaction.base_damage_bonus,
                _sum_terms(component_terms, DamageModifierStage.LUNAR_BASE_DAMAGE_BONUS_ADD),
            ),
            _merge_lunar_slot(
                LUNAR_SLOT_REACTION_BONUS,
                reaction.reaction_bonus,
                _sum_terms(component_terms, DamageModifierStage.LUNAR_REACTION_BONUS_ADD),
            ),
            _merge_lunar_slot(
                LUNAR_SLOT_ADDITIONAL_BASE_DAMAGE,
                participant.additional_base_damage,
                _sum_terms(
                    component_terms,
                    DamageModifierStage.LUNAR_ADDITIONAL_BASE_DAMAGE_ADD,
                ),
            ),
            _merge_lunar_slot(
                LUNAR_SLOT_ASCENSION_MULTIPLIER,
                participant.ascension_multiplier,
                _sum_terms(component_terms, DamageModifierStage.LUNAR_ASCENSION_BONUS_ADD),
            ),
        )
        merged = {slot.slot_key: slot.merged for slot in slots}
        zone = resolve_lunar_zone_damage(
            core_base_damage=core_base_damage,
            reaction_multiplier=reaction.reaction_multiplier,
            elemental_mastery=elemental_mastery,
            mastery_numerator=self.mastery_numerator,
            mastery_denominator=self.mastery_denominator,
            base_damage_bonus=merged[LUNAR_SLOT_BASE_DAMAGE_BONUS],
            reaction_bonus=merged[LUNAR_SLOT_REACTION_BONUS],
            additional_base_damage=merged[LUNAR_SLOT_ADDITIONAL_BASE_DAMAGE],
            critical_multiplier=critical.multiplier,
            ascension_multiplier=merged[LUNAR_SLOT_ASCENSION_MULTIPLIER],
            resistance_multiplier=resistance.multiplier,
        )
        return LunarReactionComponentResolution(
            participant_ref=participant.participant_ref,
            source_level=participant.source_level,
            base_damage_source=base_damage_source,
            scaling=scaling,
            core_base_damage=core_base_damage,
            reaction_multiplier=reaction.reaction_multiplier,
            base_damage_bonus=merged[LUNAR_SLOT_BASE_DAMAGE_BONUS],
            elemental_mastery=elemental_mastery,
            mastery_bonus=mastery_bonus,
            reaction_bonus=merged[LUNAR_SLOT_REACTION_BONUS],
            reaction_uplift_multiplier=zone.reaction_uplift_multiplier,
            base_damage_after_reaction=zone.base_damage_after_reaction,
            additional_base_damage=merged[LUNAR_SLOT_ADDITIONAL_BASE_DAMAGE],
            critical=critical,
            ascension_multiplier=merged[LUNAR_SLOT_ASCENSION_MULTIPLIER],
            resistance=resistance,
            component_damage=zone.damage,
            weight=0.0,
            weighted_damage=0.0,
            modifier_terms=component_terms,
            slots=slots,
            panel_terms=tuple(panel_terms),
        )


@dataclass(frozen=True, slots=True)
class StellarReactionDamageFormula:
    """星烁独立完整公式的结算分支。

    星烁的全部乘区与通用公式共用同一套槽位账单：倍率区、精通和增伤区、暴击区
    与抗性区复用通用阶段，基础系数、基础增伤、大权区、羽毛区与擢升使用星烁
    专属阶段。公式不再接收预乘好的区间值——所有效果都在本分支收集、署名、
    合并后才进入纯计算。
    """

    scaling_policy: ScalingZonePolicy = field(default_factory=StandardScalingZonePolicy)
    critical_policy: CriticalZonePolicy = field(default_factory=StandardCriticalZonePolicy)
    resistance_policy: StandardResistancePolicy = field(default_factory=StandardResistancePolicy)
    debug_adjustment: DebugDamageAdjustment = field(default_factory=DebugDamageAdjustment)

    @property
    def formula_spec(self) -> DamageFormulaSpec:
        """星烁公式按位置放行星烁专属阶段与对应的通用直伤阶段。"""

        return DamageFormulaSpec(
            formula_key=FORMULA_KEY_STELLAR_REACTION,
            allowed_modifier_stages=STELLAR_ALLOWED_MODIFIER_STAGES,
        )

    def resolve(self, context: DamageFormulaContext) -> StellarReactionDamageResolution:
        query = context.query
        request = query.request
        if request.formula_key is not FORMULA_KEY_STELLAR_REACTION:
            raise DamageFormulaInputError("StellarReactionDamageFormula 只能处理星烁伤害")
        stellar = request.stellar_reaction
        if stellar is None:
            raise DamageFormulaInputError("星烁伤害缺少 StellarReactionDamageInput")
        validate_formula_modifier_stages(self.formula_spec, context.modifiers)
        if stellar.mode == "reaction_composite":
            if not stellar.participants:
                raise DamageFormulaInputError("反应星烁复合伤害必须提供参与者列表")
            if request.scaling_terms:
                raise DamageFormulaInputError("反应星烁复合伤害不能携带请求级倍率")
            return self._resolve_reaction_composite(context, query, stellar)
        if stellar.mode != "character_direct":
            raise DamageFormulaInputError("星烁伤害 mode 不受支持")
        if not request.scaling_terms:
            raise DamageFormulaInputError("角色直伤星烁必须提供属性倍率")
        return self._resolve_character_direct(context, query, stellar)

    def _resolve_character_direct(
        self,
        context: DamageFormulaContext,
        query: DamageQuery,
        stellar: StellarReactionDamageInput,
    ) -> StellarReactionDamageResolution:
        """按乘区组装直伤星烁，并把槽位合并值与账本一起写进审计。"""

        terms = context.modifiers.applied_terms
        panel_terms: list[DamageModifierTerm] = []

        # 倍率与属性分别由 scaling_terms 的 coefficient 与 attribute_key
        # 承载，两者因此可以被各自独立地修饰。
        scaling, scaling_panel_terms = self.scaling_policy.resolve(
            query,
            context.scope,
            terms,
        )
        panel_terms.extend(scaling_panel_terms)

        mastery_trace = context.scope.resolve_source(STAT_ELEMENTAL_MASTERY)
        elemental_mastery = validate_damage_float(
            mastery_trace.final_value,
            "stellar elemental_mastery",
        )
        if elemental_mastery < 0:
            raise DamageResolutionError("星烁元素精通不能为负数")
        mastery_bonus = 6.0 * elemental_mastery / (elemental_mastery + 2000.0)
        panel_terms.append(
            DamageModifierTerm.panel_read(
                stage=DamageModifierStage.PANEL_ELEMENTAL_MASTERY,
                attribute=mastery_trace,
            )
        )

        # 暴击区与通用公式共用阶段，暴击率与暴击伤害都从面板读取。
        critical, critical_panel_terms = self.critical_policy.resolve(
            query,
            context.scope,
            terms,
        )
        panel_terms.extend(critical_panel_terms)

        # 抗性区与通用公式共用阶段，有效抗性由面板值加修饰项合计得到。
        resistance_attribute = context.scope.resolve_target(
            ELEMENT_TO_RESISTANCE_KEY[query.request.element.value]
        )
        resistance_panel_term = DamageModifierTerm.panel_read(
            stage=DamageModifierStage.PANEL_RESISTANCE,
            attribute=resistance_attribute,
        )
        panel_terms.append(resistance_panel_term)
        resistance_add = _sum_terms(terms, DamageModifierStage.RESISTANCE_ADD)
        resistance = self.resistance_policy.resolve(
            resistance_panel_term.value + resistance_add,
            base_resistance=resistance_panel_term.value,
            resistance_add=resistance_add,
        )

        # 基础系数、基础增伤、增伤位、大权区、羽毛区与擢升：机制侧冻结基线 +
        # 槽位账单修饰项合计。
        slots = (
            _merge_stellar_slot(
                STELLAR_SLOT_BASE_MULTIPLIER,
                stellar.stellar_base_multiplier,
                _sum_terms(terms, DamageModifierStage.STELLAR_BASE_MULTIPLIER_ADD),
            ),
            _merge_stellar_slot(
                STELLAR_SLOT_BASE_BONUS,
                stellar.stellar_base_bonus,
                _sum_terms(terms, DamageModifierStage.STELLAR_BASE_BONUS_ADD),
            ),
            _merge_stellar_slot(
                STELLAR_SLOT_REACTION_BONUS,
                stellar.stellar_bonus,
                _sum_terms(terms, DamageModifierStage.STELLAR_REACTION_BONUS_ADD),
            ),
            _merge_stellar_slot(
                STELLAR_SLOT_AUTHORITY_MULTIPLIER,
                stellar.stellar_authority_multiplier,
                _sum_terms(terms, DamageModifierStage.STELLAR_AUTHORITY_MULTIPLIER_ADD),
            ),
            _merge_stellar_slot(
                STELLAR_SLOT_FEATHER_ADDITION,
                stellar.direct_stellar_feather_addition,
                _sum_terms(terms, DamageModifierStage.STELLAR_FEATHER_ADDITION_ADD),
            ),
            _merge_stellar_slot(
                STELLAR_SLOT_ASCENSION_BONUS,
                stellar.stellar_ascension_bonus,
                _sum_terms(terms, DamageModifierStage.STELLAR_ASCENSION_BONUS_ADD),
            ),
        )
        merged = {slot.slot_key: slot.merged for slot in slots}

        zone = resolve_stellar_zone_damage(
            scaling_zone_damage=scaling.value,
            stellar_base_multiplier=merged[STELLAR_SLOT_BASE_MULTIPLIER],
            elemental_mastery=elemental_mastery,
            stellar_base_bonus=merged[STELLAR_SLOT_BASE_BONUS],
            stellar_bonus=merged[STELLAR_SLOT_REACTION_BONUS],
            stellar_authority_multiplier=merged[STELLAR_SLOT_AUTHORITY_MULTIPLIER],
            feather_addition=merged[STELLAR_SLOT_FEATHER_ADDITION],
            critical_multiplier=critical.multiplier,
            resistance_multiplier=resistance.multiplier,
            stellar_ascension_bonus=merged[STELLAR_SLOT_ASCENSION_BONUS],
        )
        debug_multiplier = self.debug_adjustment.multiplier
        final_damage = zone.damage * debug_multiplier
        if not math.isfinite(final_damage) or final_damage < 0:
            raise DamageResolutionError("星烁最终伤害必须是有限非负数")
        return StellarReactionDamageResolution(
            stellar,
            zone.damage,
            base_damage=zone.base_damage,
            elemental_mastery=elemental_mastery,
            mastery_bonus=mastery_bonus,
            critical=critical,
            resistance=resistance,
            official_damage=zone.damage,
            debug_multiplier=debug_multiplier,
            final_damage=final_damage,
            slots=slots,
            panel_terms=tuple(panel_terms),
            scaling=scaling,
        )

    def _resolve_reaction_composite(
        self,
        context: DamageFormulaContext,
        query: DamageQuery,
        stellar: StellarReactionDamageInput,
    ) -> StellarReactionDamageResolution:
        """逐参与者结算单人伤害，稳定排序取前 4 名后按固定权重聚合。

        每个组分是独立计算：修饰项按组分查询重新收集，因此只按来源自筛的
        provider 只作用于对应参与者自己的那一份。
        """

        raw_components = tuple(
            self._resolve_stellar_component(
                context,
                query,
                stellar,
                participant,
            )
            for participant in stellar.participants
        )
        ordered_components = tuple(
            sorted(
                raw_components,
                key=lambda item: (-item.component_damage, item.participant_ref.entity_id),
            )[:STELLAR_COMPOSITE_PARTICIPANT_LIMIT]
        )
        weighted_components = tuple(
            replace(
                component,
                weight=_stellar_component_weight(index),
                weighted_damage=component.component_damage * _stellar_component_weight(index),
            )
            for index, component in enumerate(ordered_components)
        )
        official_damage = math.fsum(component.weighted_damage for component in weighted_components)
        weighted_base_damage = math.fsum(
            component.base_damage * component.weight for component in weighted_components
        )
        debug_multiplier = self.debug_adjustment.multiplier
        final_damage = official_damage * debug_multiplier
        if not math.isfinite(final_damage) or final_damage < 0:
            raise DamageResolutionError("星烁最终伤害必须是有限非负数")
        top = weighted_components[0]
        return StellarReactionDamageResolution(
            stellar,
            official_damage,
            base_damage=weighted_base_damage,
            elemental_mastery=top.elemental_mastery,
            mastery_bonus=top.mastery_bonus,
            critical=top.critical,
            resistance=top.resistance,
            official_damage=official_damage,
            debug_multiplier=debug_multiplier,
            final_damage=final_damage,
            components=weighted_components,
        )

    def _resolve_stellar_component(
        self,
        context: DamageFormulaContext,
        query: DamageQuery,
        stellar: StellarReactionDamageInput,
        participant: StellarReactionParticipantInput,
    ) -> StellarReactionComponentResolution:
        component_query = _stellar_component_query(query, participant)
        component_session = _new_damage_session(context, component_query)
        # 逐参与者重新收集：组分查询的来源主体是该参与者，因此按 source_ref
        # 自筛的 provider 只对它自己这份生效；不按来源过滤的 provider 则
        # 对每个参与者各贡献一次（队伍级效果的既有语义）。
        component_modifiers = context.modifier_collector(component_query, component_session)
        validate_formula_modifier_stages(self.formula_spec, component_modifiers)
        component_terms = component_modifiers.applied_terms
        mastery_trace = component_session.resolve_source(STAT_ELEMENTAL_MASTERY)
        elemental_mastery = validate_damage_float(
            mastery_trace.final_value,
            "stellar elemental_mastery",
        )
        if elemental_mastery < 0:
            raise DamageResolutionError("星烁元素精通不能为负数")
        mastery_bonus = 6.0 * elemental_mastery / (elemental_mastery + 2000.0)
        # 面板账单项与直伤路径同构：精通、暴击、抗性都在读取点物化，作为该组分
        # 槽位账单的基础贡献（顶层不重复列入，账本落在组分内）。
        panel_terms: list[DamageModifierTerm] = [
            DamageModifierTerm.panel_read(
                stage=DamageModifierStage.PANEL_ELEMENTAL_MASTERY,
                attribute=mastery_trace,
            )
        ]
        critical, critical_panel_terms = self.critical_policy.resolve(
            component_query,
            component_session,
            component_terms,
        )
        panel_terms.extend(critical_panel_terms)
        resistance_attribute = component_session.resolve_target(
            ELEMENT_TO_RESISTANCE_KEY[query.request.element.value]
        )
        panel_terms.append(
            DamageModifierTerm.panel_read(
                stage=DamageModifierStage.PANEL_RESISTANCE,
                attribute=resistance_attribute,
            )
        )
        resistance_add = _sum_terms(component_terms, DamageModifierStage.RESISTANCE_ADD)
        resistance = self.resistance_policy.resolve(
            resistance_attribute.final_value + resistance_add,
            base_resistance=resistance_attribute.final_value,
            resistance_add=resistance_add,
        )

        # 复合模式的倍率区基线是该参与者的反应基础值（等级系数），其余位置与
        # 直伤共用同一套槽位与合并口径。
        slots = (
            _merge_stellar_slot(
                STELLAR_SLOT_BASE_MULTIPLIER,
                stellar.stellar_base_multiplier,
                _sum_terms(component_terms, DamageModifierStage.STELLAR_BASE_MULTIPLIER_ADD),
            ),
            _merge_stellar_slot(
                STELLAR_SLOT_BASE_BONUS,
                participant.stellar_base_bonus,
                _sum_terms(component_terms, DamageModifierStage.STELLAR_BASE_BONUS_ADD),
            ),
            _merge_stellar_slot(
                STELLAR_SLOT_REACTION_BONUS,
                participant.stellar_bonus,
                _sum_terms(component_terms, DamageModifierStage.STELLAR_REACTION_BONUS_ADD),
            ),
            _merge_stellar_slot(
                STELLAR_SLOT_AUTHORITY_MULTIPLIER,
                participant.stellar_authority_multiplier,
                _sum_terms(component_terms, DamageModifierStage.STELLAR_AUTHORITY_MULTIPLIER_ADD),
            ),
            _merge_stellar_slot(
                STELLAR_SLOT_FEATHER_ADDITION,
                participant.stellar_feather_addition,
                _sum_terms(component_terms, DamageModifierStage.STELLAR_FEATHER_ADDITION_ADD),
            ),
            _merge_stellar_slot(
                STELLAR_SLOT_ASCENSION_BONUS,
                participant.stellar_ascension_bonus,
                _sum_terms(component_terms, DamageModifierStage.STELLAR_ASCENSION_BONUS_ADD),
            ),
        )
        merged = {slot.slot_key: slot.merged for slot in slots}
        zone = resolve_stellar_zone_damage(
            scaling_zone_damage=participant.reaction_base_value,
            stellar_base_multiplier=merged[STELLAR_SLOT_BASE_MULTIPLIER],
            elemental_mastery=elemental_mastery,
            stellar_base_bonus=merged[STELLAR_SLOT_BASE_BONUS],
            stellar_bonus=merged[STELLAR_SLOT_REACTION_BONUS],
            stellar_authority_multiplier=merged[STELLAR_SLOT_AUTHORITY_MULTIPLIER],
            feather_addition=merged[STELLAR_SLOT_FEATHER_ADDITION],
            critical_multiplier=critical.multiplier,
            resistance_multiplier=resistance.multiplier,
            stellar_ascension_bonus=merged[STELLAR_SLOT_ASCENSION_BONUS],
        )
        return StellarReactionComponentResolution(
            participant_ref=participant.participant_ref,
            source_level=participant.source_level,
            reaction_base_value=participant.reaction_base_value,
            elemental_mastery=elemental_mastery,
            mastery_bonus=mastery_bonus,
            critical=critical,
            resistance=resistance,
            component_damage=zone.damage,
            base_damage=zone.base_damage,
            weight=0.0,
            weighted_damage=0.0,
            modifier_terms=component_terms,
            panel_terms=tuple(panel_terms),
            slots=slots,
        )


def _lunar_component_query(
    query: DamageQuery,
    reaction: LunarReactionDamageInput,
    participant: LunarReactionParticipantInput,
) -> DamageQuery:
    """为一个月曜角色组分创建独立的属性查询。

    组分查询**继承月曜公式键**：按 ``formula_key`` 自筛的月曜 provider 必须能在
    组分收集里被识别，否则会在复合路径静默返回空。倍率由参与者携带，因此
    ``scaling_terms`` / ``flat_base_damage`` 取自参与者而不是请求。
    """

    request = query.request
    component_request = DamageRequest(
        request_id=f"{request.request_id}:participant:{participant.participant_ref.entity_id}",
        frame=request.frame,
        formula_key=FORMULA_KEY_LUNAR_REACTION,
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
        lunar_reaction=reaction,
        tags=frozenset((*request.tags, reaction.reaction_profile_key)),
        request_facts=request.request_facts,
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
    """创建不共享来源主体的组分属性 session。

    组分 session 与父结算共享同一事实索引：会话级事实是整次仿真的状态投影，
    不随参与者切换；请求级事实则经 ``DamageRequest.request_facts`` 由组分
    查询自行继承。
    """

    from genshin_sim.core.systems.damage.resolver import DamageResolutionScope

    return DamageResolutionScope(
        context.scope.attribute_resolver,
        query,
        context.trace_level,
        fact_index=context.scope.fact_index,
    )


def validate_formula_modifier_stages(
    formula_spec: DamageFormulaSpec,
    modifiers: DamageModifierCollection,
) -> None:
    """修饰项必须落在该公式的 ``allowed_modifier_stages`` 白名单内。

    常规路径由 resolver 在入公式前调用一次；公式体内保留同构调用作为兜底，
    因为公式也可以被直接调用。越界一律视为 provider 违规，不做静默忽略。
    """

    for term in (*modifiers.applied_terms, *modifiers.rejected_terms):
        if term.stage not in formula_spec.allowed_modifier_stages:
            raise DamageProviderViolationError(
                f"伤害公式 {formula_spec.formula_key} 不允许阶段：{term.stage.value}"
            )


def _stellar_component_query(
    query: DamageQuery,
    participant: StellarReactionParticipantInput,
) -> DamageQuery:
    """为一个星烁角色组分创建独立的属性查询与请求投影。

    只替换身份相关字段，公式键与星烁输入沿用整次请求：provider 按
    ``source_ref`` 与 ``formula_key`` 自筛时，组分查询仍被识别为星烁伤害，
    且归属是参与者自己。
    """

    request = query.request
    component_request = replace(
        request,
        request_id=f"{request.request_id}:participant:{participant.participant_ref.entity_id}",
        source_ref=participant.participant_ref,
        source_level=participant.source_level,
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


def _stellar_component_weight(index: int) -> float:
    """返回星烁复合伤害按完整单人伤害排序后的固定权重。

    星烁与月曜复合共用同一分配表 ``LUNAR_COMPOSITE_WEIGHTS``（``0.60 : 0.30 : 0.05``，
    超出表长沿用最后一项）：权重单点定义、不在公式体里重复硬写，口径见 D-083。
    """

    if index < len(LUNAR_COMPOSITE_WEIGHTS):
        return LUNAR_COMPOSITE_WEIGHTS[index]
    return LUNAR_COMPOSITE_WEIGHTS[-1]


def _merge_stellar_slot(
    slot_key: str,
    baseline: float,
    modifier_sum: float,
) -> StellarZoneSlotAudit:
    """按「冻结基线 + Σ修饰项」合并一个星烁槽位，并返回三段审计。

    合并值同时用于实算与审计，因此偏离基线时可以直接从 ``slots`` 读出是谁
    贡献了多少；provider 署名沿用 ``applied_terms`` 的既有机制。
    """

    merged = float(baseline) + float(modifier_sum)
    if not math.isfinite(merged):
        raise DamageResolutionError(f"星烁槽位 {slot_key} 合并值必须是有限数字")
    if merged < 0:
        raise DamageResolutionError(f"星烁槽位 {slot_key} 合并值不能为负数")
    return StellarZoneSlotAudit(
        slot_key=slot_key,
        baseline=baseline,
        modifier_sum=modifier_sum,
        merged=merged,
    )


def _merge_lunar_slot(
    slot_key: str,
    baseline: float,
    modifier_sum: float,
) -> LunarZoneSlotAudit:
    """按「冻结基线 + Σ修饰项」合并一个月曜槽位，并返回三段审计。

    合并值同时用于实算与审计，因此偏离基线时可以直接从 ``slots`` 读出是谁
    贡献了多少；provider 署名沿用 ``applied_terms`` 的既有机制。
    """

    merged = float(baseline) + float(modifier_sum)
    if not math.isfinite(merged):
        raise DamageResolutionError(f"月曜槽位 {slot_key} 合并值必须是有限数字")
    if merged < 0:
        raise DamageResolutionError(f"月曜槽位 {slot_key} 合并值不能为负数")
    return LunarZoneSlotAudit(
        slot_key=slot_key,
        baseline=baseline,
        modifier_sum=modifier_sum,
        merged=merged,
    )


def _lunar_component_weight(mode: LunarReactionDamageMode, index: int) -> float:
    """返回月曜复合伤害按完整组分排序后的固定权重。

    权重取自 ``LUNAR_COMPOSITE_WEIGHTS``（与机制侧反应系数配成一对口径）；超出表长
    的组分沿用最后一项，即资料口径里的「其余组分各 0.05」。直伤模式只有单一组分，
    不参与加权。
    """

    if mode is LunarReactionDamageMode.CHARACTER_DIRECT:
        return 1.0
    if index < len(LUNAR_COMPOSITE_WEIGHTS):
        return LUNAR_COMPOSITE_WEIGHTS[index]
    return LUNAR_COMPOSITE_WEIGHTS[-1]


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
    critical_decision_provider: CriticalDecisionProvider | None = None,
) -> DamageFormulaRegistry:
    """创建生产默认公式注册表；月曜公式默认使用已确认的生产数值。

    ``lunar_formula`` 仅供测试或未来配置覆盖生产默认值；
    ``critical_decision_provider`` 缺省时暴击区使用固定不暴击决策。
    """

    critical_policy = (
        StandardCriticalZonePolicy(decision_provider=critical_decision_provider)
        if critical_decision_provider is not None
        else StandardCriticalZonePolicy()
    )
    formulas: list[DamageFormula] = [
        GeneralDamageFormula(critical_policy=critical_policy),
        TransformativeReactionDamageFormula(),
    ]
    formulas.append(
        lunar_formula
        if lunar_formula is not None
        else LunarReactionDamageFormula(
            level_base_damage=PRODUCTION_LUNAR_REACTION_LEVEL_BASE_DAMAGE,
            mastery_numerator=PRODUCTION_LUNAR_MASTERY_NUMERATOR,
            mastery_denominator=PRODUCTION_LUNAR_MASTERY_DENOMINATOR,
            critical_policy=critical_policy,
        )
    )
    formulas.append(StellarReactionDamageFormula(critical_policy=critical_policy))
    return DamageFormulaRegistry(tuple(formulas))


def _sum_terms(
    terms: tuple[DamageModifierTerm, ...],
    stage: DamageModifierStage,
) -> float:
    """使用 ``math.fsum`` 汇总指定阶段的修饰项数值。"""

    return math.fsum(term.value for term in terms if term.stage is stage)
