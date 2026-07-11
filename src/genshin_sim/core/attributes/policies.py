from __future__ import annotations

import math
from dataclasses import dataclass

from genshin_sim.core.attributes.definitions import AttributeDefinition, MissingValuePolicy
from genshin_sim.core.attributes.errors import (
    ConflictingOverrideError,
    MissingAttributeValueError,
)
from genshin_sim.core.attributes.models import (
    AttributeResolution,
    BaseAttributeContribution,
    ModifierStage,
    ModifierTerm,
    normalize_zero,
    validate_finite_float,
)


@dataclass(frozen=True, slots=True)
class ResolutionPolicy:
    policy_key: str
    allowed_stages: frozenset[ModifierStage]

    def resolve(
        self,
        definition: AttributeDefinition,
        base_contributions: tuple[BaseAttributeContribution, ...],
        terms: tuple[ModifierTerm, ...],
        dependencies: tuple[AttributeResolution, ...],
    ) -> tuple[float, float]:
        raise NotImplementedError

    def apply_bounds(self, definition: AttributeDefinition, value: float) -> float:
        value = validate_finite_float(value, "resolved value")
        if definition.lower_bound is not None:
            value = max(value, definition.lower_bound)
        if definition.upper_bound is not None:
            value = min(value, definition.upper_bound)
        return normalize_zero(validate_finite_float(value, "bounded value"))


class BaseSumPolicy(ResolutionPolicy):
    def __init__(self) -> None:
        super().__init__("base_sum", frozenset({ModifierStage.BASE_ADD}))

    def resolve(
        self,
        definition: AttributeDefinition,
        base_contributions: tuple[BaseAttributeContribution, ...],
        terms: tuple[ModifierTerm, ...],
        dependencies: tuple[AttributeResolution, ...],
    ) -> tuple[float, float]:
        del dependencies
        base_value = _resolve_base_value(definition, base_contributions)
        result = math.fsum((base_value, *(term.value for term in terms)))
        return base_value, self.apply_bounds(definition, result)


class TotalStatPolicy(ResolutionPolicy):
    def __init__(self) -> None:
        super().__init__(
            "total_stat",
            frozenset(
                {
                    ModifierStage.PERCENT_ADD,
                    ModifierStage.FLAT_ADD,
                    ModifierStage.FINAL_MULTIPLIER,
                }
            ),
        )

    def resolve(
        self,
        definition: AttributeDefinition,
        base_contributions: tuple[BaseAttributeContribution, ...],
        terms: tuple[ModifierTerm, ...],
        dependencies: tuple[AttributeResolution, ...],
    ) -> tuple[float, float]:
        del base_contributions
        if len(dependencies) != 1:
            raise ValueError(f"total_stat 属性 {definition.key} 必须有且只有一个依赖")
        dependency = dependencies[0]
        base_value = float(dependency.final_value)
        percent = math.fsum(
            term.value for term in terms if term.stage is ModifierStage.PERCENT_ADD
        )
        flat = math.fsum(term.value for term in terms if term.stage is ModifierStage.FLAT_ADD)
        result = math.fsum((base_value * (1.0 + percent), flat))
        for term in terms:
            if term.stage is ModifierStage.FINAL_MULTIPLIER:
                result *= 1.0 + term.value
        return base_value, self.apply_bounds(definition, result)


class AdditivePolicy(ResolutionPolicy):
    def __init__(self) -> None:
        super().__init__("additive", frozenset({ModifierStage.FLAT_ADD}))

    def resolve(
        self,
        definition: AttributeDefinition,
        base_contributions: tuple[BaseAttributeContribution, ...],
        terms: tuple[ModifierTerm, ...],
        dependencies: tuple[AttributeResolution, ...],
    ) -> tuple[float, float]:
        del dependencies
        base_value = _resolve_base_value(definition, base_contributions)
        result = math.fsum((base_value, *(term.value for term in terms)))
        return base_value, self.apply_bounds(definition, result)


POLICIES = {
    "base_sum": BaseSumPolicy(),
    "total_stat": TotalStatPolicy(),
    "additive": AdditivePolicy(),
}


def apply_override_terms(value: float, terms: tuple[ModifierTerm, ...]) -> float:
    overrides = [term for term in terms if term.stage is ModifierStage.OVERRIDE]
    if not overrides:
        return value
    if len(overrides) > 1:
        raise ConflictingOverrideError("同一属性查询存在多个有效 override term")
    return overrides[0].value


def _resolve_base_value(
    definition: AttributeDefinition,
    contributions: tuple[BaseAttributeContribution, ...],
) -> float:
    if contributions:
        return math.fsum(contribution.value for contribution in contributions)
    if definition.missing_value_policy is MissingValuePolicy.ERROR:
        raise MissingAttributeValueError(f"属性 {definition.key} 缺少基础值")
    return definition.default_value
