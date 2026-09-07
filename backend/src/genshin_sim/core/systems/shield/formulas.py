from __future__ import annotations

import math
from dataclasses import dataclass

from genshin_sim.core.attributes import AttributeKey, RuntimeSourceRef, is_public_attribute_key
from genshin_sim.core.systems.shield.errors import (
    ShieldCapacityError,
    ShieldValidationError,
)


def validate_shield_float(value: float | int, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ShieldValidationError(f"{field_name} 必须是数字")
    result = float(value)
    if not math.isfinite(result):
        raise ShieldValidationError(f"{field_name} 必须是有限数字")
    if result == 0.0:
        return 0.0
    return result


def validate_non_negative_shield_float(value: float | int, field_name: str) -> float:
    result = validate_shield_float(value, field_name)
    if result < 0:
        raise ShieldValidationError(f"{field_name} 不能为负数")
    return result


def normalize_shield_zero(value: float) -> float:
    if abs(value) <= 1e-12:
        return 0.0
    return value


def validate_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ShieldValidationError(f"{field_name} 必须是非空字符串")


@dataclass(frozen=True, slots=True)
class ShieldScalingTerm:
    component_key: str
    attribute_key: AttributeKey
    coefficient: float

    def __post_init__(self) -> None:
        validate_non_empty_text(self.component_key, "component_key")
        if not isinstance(self.attribute_key, AttributeKey):
            raise ShieldValidationError("attribute_key 必须是 AttributeKey")
        if not is_public_attribute_key(self.attribute_key):
            raise ShieldValidationError(f"护盾缩放属性必须是公共属性：{self.attribute_key}")
        object.__setattr__(
            self,
            "coefficient",
            validate_non_negative_shield_float(self.coefficient, "coefficient"),
        )


@dataclass(frozen=True, slots=True)
class ShieldNativeMultiplierTerm:
    multiplier_key: str
    multiplier: float
    source_context: RuntimeSourceRef

    def __post_init__(self) -> None:
        validate_non_empty_text(self.multiplier_key, "multiplier_key")
        object.__setattr__(
            self,
            "multiplier",
            validate_non_negative_shield_float(self.multiplier, "multiplier"),
        )
        if not isinstance(self.source_context, RuntimeSourceRef):
            raise ShieldValidationError("source_context 必须是 RuntimeSourceRef")


@dataclass(frozen=True, slots=True)
class ShieldCapacityFormula:
    scaling_terms: tuple[ShieldScalingTerm, ...] = ()
    flat_absorption: float = 0.0
    native_multipliers: tuple[ShieldNativeMultiplierTerm, ...] = ()

    def __post_init__(self) -> None:
        terms = tuple(sorted(self.scaling_terms, key=lambda term: term.component_key))
        for term in terms:
            if not isinstance(term, ShieldScalingTerm):
                raise ShieldValidationError("scaling_terms 必须全部是 ShieldScalingTerm")
        component_keys = [term.component_key for term in terms]
        if len(component_keys) != len(set(component_keys)):
            raise ShieldValidationError("ShieldCapacityFormula component_key 不能重复")
        multipliers = tuple(sorted(self.native_multipliers, key=lambda term: term.multiplier_key))
        for multiplier in multipliers:
            if not isinstance(multiplier, ShieldNativeMultiplierTerm):
                raise ShieldValidationError(
                    "native_multipliers 必须全部是 ShieldNativeMultiplierTerm"
                )
        multiplier_keys = [term.multiplier_key for term in multipliers]
        if len(multiplier_keys) != len(set(multiplier_keys)):
            raise ShieldValidationError("ShieldCapacityFormula multiplier_key 不能重复")
        object.__setattr__(self, "scaling_terms", terms)
        object.__setattr__(
            self,
            "flat_absorption",
            validate_non_negative_shield_float(self.flat_absorption, "flat_absorption"),
        )
        object.__setattr__(self, "native_multipliers", multipliers)


@dataclass(frozen=True, slots=True)
class ShieldCapacityComponentResult:
    component_key: str
    attribute_key: AttributeKey
    attribute_value: float
    coefficient: float
    value: float

    def __post_init__(self) -> None:
        validate_non_empty_text(self.component_key, "component_key")
        if not isinstance(self.attribute_key, AttributeKey):
            raise ShieldValidationError("attribute_key 必须是 AttributeKey")
        for field_name in ("attribute_value", "coefficient", "value"):
            object.__setattr__(
                self,
                field_name,
                validate_shield_float(getattr(self, field_name), field_name),
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "component_key": self.component_key,
            "attribute_key": str(self.attribute_key),
            "attribute_value": self.attribute_value,
            "coefficient": self.coefficient,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class ShieldNativeMultiplierResult:
    multiplier_key: str
    multiplier: float
    source_context: RuntimeSourceRef

    def __post_init__(self) -> None:
        validate_non_empty_text(self.multiplier_key, "multiplier_key")
        object.__setattr__(
            self,
            "multiplier",
            validate_non_negative_shield_float(self.multiplier, "multiplier"),
        )
        if not isinstance(self.source_context, RuntimeSourceRef):
            raise ShieldValidationError("source_context 必须是 RuntimeSourceRef")

    def to_dict(self) -> dict[str, object]:
        return {
            "multiplier_key": self.multiplier_key,
            "multiplier": self.multiplier,
            "source_context": _runtime_source_ref_to_dict(self.source_context),
        }


@dataclass(frozen=True, slots=True)
class ShieldCapacityFormulaResult:
    component_results: tuple[ShieldCapacityComponentResult, ...]
    flat_absorption: float
    base_absorption: float
    native_multiplier_results: tuple[ShieldNativeMultiplierResult, ...]
    native_multiplier: float
    native_absorption: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "component_results", tuple(self.component_results))
        object.__setattr__(
            self,
            "native_multiplier_results",
            tuple(self.native_multiplier_results),
        )
        for field_name in (
            "flat_absorption",
            "base_absorption",
            "native_multiplier",
            "native_absorption",
        ):
            object.__setattr__(
                self,
                field_name,
                validate_shield_float(getattr(self, field_name), field_name),
            )
        if self.native_absorption <= 0:
            raise ShieldCapacityError("护盾原生吸收量必须是正数")

    def to_dict(self) -> dict[str, object]:
        return {
            "component_results": tuple(component.to_dict() for component in self.component_results),
            "flat_absorption": self.flat_absorption,
            "base_absorption": self.base_absorption,
            "native_multiplier_results": tuple(
                multiplier.to_dict() for multiplier in self.native_multiplier_results
            ),
            "native_multiplier": self.native_multiplier,
            "native_absorption": self.native_absorption,
        }


def _runtime_source_ref_to_dict(ref: RuntimeSourceRef) -> dict[str, str | None]:
    return {
        "kind": ref.kind.value,
        "source_key": ref.source_key,
        "instance_id": ref.instance_id,
    }
