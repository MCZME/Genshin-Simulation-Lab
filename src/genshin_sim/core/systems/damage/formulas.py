"""完整伤害公式协议、注册表和通用公式实现。"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from genshin_sim.core.attributes import (
    ELEMENT_TO_RESISTANCE_KEY,
    AttributeResolution,
    TraceLevel,
)
from genshin_sim.core.systems.damage.enums import DamageModifierStage, DamageType
from genshin_sim.core.systems.damage.errors import (
    DamageFormulaInputError,
    DamageResolutionError,
    DuplicateDamageFormulaError,
    InvalidDamageScalingError,
    UnsupportedDamageTypeError,
)
from genshin_sim.core.systems.damage.models import (
    DamageFormulaResolution,
    DamageModifierTerm,
    DamageQuery,
    DebugDamageAdjustment,
    GeneralDamageResolution,
)
from genshin_sim.core.systems.damage.modifiers import DamageModifierCollection
from genshin_sim.core.systems.damage.policies import (
    CriticalZonePolicy,
    DamageBonusZonePolicy,
    GeneralReactionZonePolicy,
    IdentityGeneralReactionZonePolicy,
    ScalingZonePolicy,
    StandardCriticalZonePolicy,
    StandardDamageBonusZonePolicy,
    StandardDefensePolicy,
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
    }
)


@dataclass(frozen=True, slots=True)
class DamageFormulaSpec:
    """完整公式的稳定类型和允许的 modifier stage。"""

    damage_type: DamageType
    allowed_modifier_stages: frozenset[DamageModifierStage]

    def __post_init__(self) -> None:
        """冻结 stage 声明并校验伤害类型。"""

        if not isinstance(self.damage_type, DamageType):
            raise DamageFormulaInputError("damage formula spec 的 damage_type 不受支持")
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
        """注册公式并拒绝重复 damage type。"""

        self._formulas: dict[DamageType, DamageFormula] = {}
        for formula in formulas:
            damage_type = formula.formula_spec.damage_type
            if damage_type in self._formulas:
                raise DuplicateDamageFormulaError(f"重复伤害公式：{damage_type.value}")
            self._formulas[damage_type] = formula

    def require(self, damage_type: DamageType) -> DamageFormula:
        """返回指定伤害类型的公式；未注册时明确失败。"""

        try:
            return self._formulas[damage_type]
        except KeyError as exc:
            raise UnsupportedDamageTypeError(f"未支持的伤害类型：{damage_type.value}") from exc


@dataclass(frozen=True, slots=True)
class GeneralDamageFormula:
    """普通直伤与未来增幅反应共用的通用完整公式。"""

    scaling_policy: ScalingZonePolicy = field(default_factory=StandardScalingZonePolicy)
    damage_bonus_policy: DamageBonusZonePolicy = field(
        default_factory=StandardDamageBonusZonePolicy
    )
    critical_policy: CriticalZonePolicy = field(default_factory=StandardCriticalZonePolicy)
    reaction_policy: GeneralReactionZonePolicy = field(
        default_factory=IdentityGeneralReactionZonePolicy
    )
    defense_policy: StandardDefensePolicy = field(default_factory=StandardDefensePolicy)
    resistance_policy: StandardResistancePolicy = field(default_factory=StandardResistancePolicy)
    debug_adjustment: DebugDamageAdjustment = field(default_factory=DebugDamageAdjustment)

    @property
    def formula_spec(self) -> DamageFormulaSpec:
        """通用公式第一轮允许全部正式直伤 modifier stage。"""

        return DamageFormulaSpec(
            damage_type=DamageType.GENERAL,
            allowed_modifier_stages=GENERAL_ALLOWED_MODIFIER_STAGES,
        )

    def resolve(self, context: DamageFormulaContext) -> GeneralDamageResolution:
        """按倍率、增伤、暴击、反应、防御和抗性区计算通用伤害。"""

        query = context.query
        if query.request.damage_type is not DamageType.GENERAL:
            raise DamageFormulaInputError("GeneralDamageFormula 只能处理 GENERAL 伤害")
        if query.request.flat_base_damage < 0:
            raise InvalidDamageScalingError("普通直伤 flat_base_damage 不能为负数")
        if not query.request.scaling_terms and query.request.flat_base_damage == 0:
            raise InvalidDamageScalingError("普通直伤必须包含 scaling term 或固定基础伤害")
        terms = context.modifiers.applied_terms
        source_trace: list[AttributeResolution] = []

        scaling, scaling_trace = self.scaling_policy.resolve(query, context.session, terms)
        source_trace.extend(scaling_trace)

        damage_bonus, damage_bonus_trace = self.damage_bonus_policy.resolve(
            query,
            context.session,
            terms,
        )
        source_trace.append(damage_bonus_trace)

        critical, critical_trace = self.critical_policy.resolve(query, context.session, terms)
        source_trace.extend(critical_trace)

        reaction = self.reaction_policy.resolve(query)
        defense = self.defense_policy.resolve(
            query.request.source_level,
            query.request.target_level,
            _sum_terms(terms, DamageModifierStage.DEFENSE_REDUCTION),
            _sum_terms(terms, DamageModifierStage.DEFENSE_IGNORE),
        )

        resistance_resolution = context.session.resolve_target(
            ELEMENT_TO_RESISTANCE_KEY[query.request.element.value]
        )
        resistance = self.resistance_policy.resolve(resistance_resolution.final_value)

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
        )


def create_default_damage_formula_registry() -> DamageFormulaRegistry:
    """创建生产默认公式注册表，第一轮只注册通用公式。"""

    return DamageFormulaRegistry((GeneralDamageFormula(),))


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
