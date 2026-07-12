"""伤害结算中可替换的暴击、防御和抗性策略。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from genshin_sim.core.attributes import (
    ELEMENT_TO_DAMAGE_BONUS_KEY,
    STAT_CRIT_DAMAGE,
    STAT_CRIT_RATE,
    AttributeResolution,
)
from genshin_sim.core.systems.damage.enums import CritOutcome, DamageModifierStage
from genshin_sim.core.systems.damage.errors import CriticalDecisionError, DamageResolutionError
from genshin_sim.core.systems.damage.models import (
    BaseDamageAddition,
    CriticalZoneResolution,
    DamageBonusZoneResolution,
    DamageComponentResult,
    DamageModifierTerm,
    DamageQuery,
    DefenseResolution,
    GeneralReactionZoneResolution,
    ResistanceResolution,
    ScalingZoneResolution,
    validate_damage_float,
)

if TYPE_CHECKING:
    from genshin_sim.core.systems.damage.resolver import DamageResolutionSession


class CriticalDecisionProvider(Protocol):
    """根据有效暴击率决定一次伤害的暴击结果。"""

    def decide(self, query: DamageQuery, effective_crit_rate: float) -> CritOutcome:
        """返回当前伤害查询的暴击、未暴击或非法外的确定结果。"""

        ...


@dataclass(frozen=True, slots=True)
class FixedCriticalDecisionProvider:
    """测试和确定性运行使用的固定暴击决策。"""

    outcome: CritOutcome = CritOutcome.NON_CRITICAL

    def __post_init__(self) -> None:
        """拒绝把不可暴击占位结果作为固定决策。"""

        if self.outcome is CritOutcome.NOT_APPLICABLE:
            raise CriticalDecisionError("固定暴击决策不能使用 not_applicable")

    def decide(self, query: DamageQuery, effective_crit_rate: float) -> CritOutcome:
        """忽略查询和有效暴击率，返回构造时指定的结果。"""

        del query, effective_crit_rate
        return self.outcome


class ScalingZonePolicy(Protocol):
    """计算通用公式倍率区的局部公式族协议。"""

    def resolve(
        self,
        query: DamageQuery,
        session: DamageResolutionSession,
        terms: tuple[DamageModifierTerm, ...],
    ) -> tuple[ScalingZoneResolution, tuple[AttributeResolution, ...]]:
        """返回倍率区结果和本区读取的来源属性 trace。"""

        ...


class StandardScalingZonePolicy:
    """按多属性倍率和统一固定基础伤害加值计算倍率区。"""

    def resolve(
        self,
        query: DamageQuery,
        session: DamageResolutionSession,
        terms: tuple[DamageModifierTerm, ...],
    ) -> tuple[ScalingZoneResolution, tuple[AttributeResolution, ...]]:
        """返回倍率区组件、加值和合计基础伤害。"""

        source_trace: list[AttributeResolution] = []
        component_results: list[DamageComponentResult] = []
        for scaling in query.request.scaling_terms:
            attribute = session.resolve_source(scaling.attribute_key)
            source_trace.append(attribute)
            percent_add = _sum_terms(
                terms,
                DamageModifierStage.COMPONENT_COEFFICIENT_PERCENT_ADD,
                component_key=scaling.component_key,
            )
            flat_add = _sum_terms(
                terms,
                DamageModifierStage.COMPONENT_COEFFICIENT_FLAT_ADD,
                component_key=scaling.component_key,
            )
            final_coefficient = scaling.coefficient * (1 + percent_add) + flat_add
            if final_coefficient < 0:
                raise DamageResolutionError(
                    f"component {scaling.component_key} 的最终倍率不能为负数"
                )
            component_damage = attribute.final_value * final_coefficient
            component_results.append(
                DamageComponentResult(
                    component_key=scaling.component_key,
                    attribute_key=scaling.attribute_key,
                    attribute_value=attribute.final_value,
                    original_coefficient=scaling.coefficient,
                    final_coefficient=final_coefficient,
                    damage=component_damage,
                )
            )

        additions = _base_damage_additions(query, terms)
        value = math.fsum(
            (
                *(component.damage for component in component_results),
                *(addition.value for addition in additions),
            )
        )
        if value < 0:
            raise DamageResolutionError("基础伤害不能为负数")
        return (
            ScalingZoneResolution(
                component_results=tuple(component_results),
                additions=additions,
                value=value,
            ),
            tuple(source_trace),
        )


class DamageBonusZonePolicy(Protocol):
    """计算通用公式增伤区的局部公式族协议。"""

    def resolve(
        self,
        query: DamageQuery,
        session: DamageResolutionSession,
        terms: tuple[DamageModifierTerm, ...],
    ) -> tuple[DamageBonusZoneResolution, AttributeResolution]:
        """返回增伤区结果和读取的元素增伤属性 trace。"""

        ...


class StandardDamageBonusZonePolicy:
    """元素伤害加成与伤害专用加成相加形成增伤乘数。"""

    def resolve(
        self,
        query: DamageQuery,
        session: DamageResolutionSession,
        terms: tuple[DamageModifierTerm, ...],
    ) -> tuple[DamageBonusZoneResolution, AttributeResolution]:
        """返回第一轮通用公式增伤区结果。"""

        bonus_resolution = session.resolve_source(
            ELEMENT_TO_DAMAGE_BONUS_KEY[query.request.element.value]
        )
        modifier_bonus = _sum_terms(terms, DamageModifierStage.DAMAGE_BONUS_ADD)
        multiplier = 1 + bonus_resolution.final_value + modifier_bonus
        if multiplier < 0:
            raise DamageResolutionError("增伤区乘数不能为负数")
        return (
            DamageBonusZoneResolution(
                element_bonus=bonus_resolution.final_value,
                modifier_bonus=modifier_bonus,
                multiplier=multiplier,
            ),
            bonus_resolution,
        )


class CriticalZonePolicy(Protocol):
    """计算通用公式暴击区的局部公式族协议。"""

    def resolve(
        self,
        query: DamageQuery,
        session: DamageResolutionSession,
        terms: tuple[DamageModifierTerm, ...],
    ) -> tuple[CriticalZoneResolution, tuple[AttributeResolution, ...]]:
        """返回暴击区结果和读取的来源属性 trace。"""

        ...


@dataclass(frozen=True, slots=True)
class StandardCriticalZonePolicy:
    """复用注入式暴击决策 provider 的标准暴击区。"""

    decision_provider: CriticalDecisionProvider = FixedCriticalDecisionProvider()

    def resolve(
        self,
        query: DamageQuery,
        session: DamageResolutionSession,
        terms: tuple[DamageModifierTerm, ...],
    ) -> tuple[CriticalZoneResolution, tuple[AttributeResolution, ...]]:
        """返回暴击率、暴击伤害、决策结果和乘数。"""

        if query.request.can_crit:
            crit_rate_resolution = session.resolve_source(STAT_CRIT_RATE)
            crit_damage_resolution = session.resolve_source(STAT_CRIT_DAMAGE)
            crit_rate = crit_rate_resolution.final_value + _sum_terms(
                terms,
                DamageModifierStage.CRIT_RATE_ADD,
            )
            crit_damage = crit_damage_resolution.final_value + _sum_terms(
                terms,
                DamageModifierStage.CRIT_DAMAGE_ADD,
            )
            effective_crit_rate = min(max(crit_rate, 0.0), 1.0)
            outcome = self.decision_provider.decide(query, effective_crit_rate)
            if outcome is CritOutcome.NOT_APPLICABLE:
                raise CriticalDecisionError("可暴击伤害不能返回 not_applicable")
            source_trace = (crit_rate_resolution, crit_damage_resolution)
        else:
            crit_rate = 0.0
            crit_damage = 0.0
            effective_crit_rate = 0.0
            outcome = CritOutcome.NOT_APPLICABLE
            source_trace = ()
        multiplier = 1 + crit_damage if outcome is CritOutcome.CRITICAL else 1.0
        if multiplier < 0:
            raise DamageResolutionError("暴击乘数不能为负数")
        return (
            CriticalZoneResolution(
                can_crit=query.request.can_crit,
                crit_rate=crit_rate,
                effective_crit_rate=effective_crit_rate,
                crit_damage=crit_damage,
                outcome=outcome,
                multiplier=multiplier,
            ),
            source_trace,
        )


class GeneralReactionZonePolicy(Protocol):
    """通用公式反应区协议。"""

    def resolve(self, query: DamageQuery) -> GeneralReactionZoneResolution:
        """返回通用公式反应区乘数。"""

        ...


class IdentityGeneralReactionZonePolicy:
    """第一轮通用公式无增幅反应时使用的单位反应区。"""

    def resolve(self, query: DamageQuery) -> GeneralReactionZoneResolution:
        """忽略查询，返回单位乘数。"""

        del query
        return GeneralReactionZoneResolution(1.0)


class StandardDefensePolicy:
    """按等级、防御降低和无视防御计算普通直伤防御乘区。"""

    def resolve(
        self,
        source_level: int,
        target_level: int,
        defense_reduction: float,
        defense_ignore: float,
    ) -> DefenseResolution:
        """返回第一版确认公式下的防御区审计结果。"""

        reduction = validate_damage_float(defense_reduction, "defense_reduction")
        ignore = validate_damage_float(defense_ignore, "defense_ignore")
        if reduction < 0:
            raise DamageResolutionError("defense_reduction 不能为负数")
        if ignore < 0:
            raise DamageResolutionError("defense_ignore 不能为负数")
        source_factor = source_level + 100.0
        target_factor = (target_level + 100.0) * (1 - ignore) * (1 - reduction)
        denominator = source_factor + target_factor
        if denominator <= 0:
            raise DamageResolutionError("防御区分母必须大于 0")
        return DefenseResolution(
            source_level=source_level,
            target_level=target_level,
            defense_reduction=reduction,
            defense_ignore=ignore,
            multiplier=source_factor / denominator,
        )


class StandardResistancePolicy:
    """按旧项目迁移基线的分段函数计算抗性乘区。"""

    def resolve(self, resistance: float) -> ResistanceResolution:
        """返回给定抗性值对应的抗性区审计结果。"""

        value = validate_damage_float(resistance, "resistance")
        if value < 0:
            multiplier = 1 - value / 2
        elif value > 0.75:
            multiplier = 1 / (1 + 4 * value)
        else:
            multiplier = 1 - value
        return ResistanceResolution(value, multiplier)


def _base_damage_additions(
    query: DamageQuery,
    terms: tuple[DamageModifierTerm, ...],
) -> tuple[BaseDamageAddition, ...]:
    """把请求固定基础伤害和 modifier 加值统一为倍率区 addition 审计。"""

    additions: list[BaseDamageAddition] = []
    if query.request.flat_base_damage:
        additions.append(
            BaseDamageAddition(
                addition_key="request.flat_base_damage",
                value=query.request.flat_base_damage,
                source_ref=query.request.source_context,
                audit_tags=("request",),
            )
        )
    additions.extend(
        BaseDamageAddition(
            addition_key=f"{term.provider_key}.base_damage_flat_add",
            value=term.value,
            source_ref=term.source_ref,
            audit_tags=term.audit_tags,
        )
        for term in _terms_for_stage(terms, DamageModifierStage.BASE_DAMAGE_FLAT_ADD)
    )
    return tuple(additions)


def _terms_for_stage(
    terms: tuple[DamageModifierTerm, ...],
    stage: DamageModifierStage,
    *,
    component_key: str | None = None,
) -> tuple[DamageModifierTerm, ...]:
    """筛选指定阶段和可选 component 的伤害修饰项。"""

    return tuple(
        term for term in terms if term.stage is stage and term.component_key == component_key
    )


def _sum_terms(
    terms: tuple[DamageModifierTerm, ...],
    stage: DamageModifierStage,
    *,
    component_key: str | None = None,
) -> float:
    """使用 ``math.fsum`` 汇总指定阶段的修饰项数值。"""

    return math.fsum(
        term.value for term in _terms_for_stage(terms, stage, component_key=component_key)
    )
