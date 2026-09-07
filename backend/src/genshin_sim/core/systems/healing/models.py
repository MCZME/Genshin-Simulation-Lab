"""治疗系统的不可变请求、结果和审计值对象。"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from genshin_sim.core.attributes import (
    AttributeKey,
    AttributeSubjectKind,
    AttributeSubjectRef,
    RuntimeSourceRef,
    is_public_attribute_key,
)
from genshin_sim.core.systems.healing.errors import (
    HealingValidationError,
    InvalidHealingAttributeError,
    InvalidHealingResultError,
    UnsupportedHealingSubjectError,
)


def validate_healing_float(value: float | int, field_name: str) -> float:
    """校验治疗流水线中的数值字段，并返回标准 ``float``。"""

    if isinstance(value, bool) or not isinstance(value, int | float):
        raise HealingValidationError(f"{field_name} 必须是数字")
    try:
        result = float(value)
    except OverflowError as exc:
        raise HealingValidationError(f"{field_name} 必须是有限数字") from exc
    if not math.isfinite(result):
        raise HealingValidationError(f"{field_name} 必须是有限数字")
    if result == 0.0:
        return 0.0
    return result


def validate_non_negative_healing_float(value: float | int, field_name: str) -> float:
    """校验治疗请求中必须为非负的数值字段。"""

    result = validate_healing_float(value, field_name)
    if result < 0:
        raise HealingValidationError(f"{field_name} 不能为负数")
    return result


def normalize_healing_zero(value: float) -> float:
    """把 ``-0.0`` 规范为 ``0.0``，保留其他有限数值。"""

    if value == 0.0:
        return 0.0
    return value


def _validate_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise HealingValidationError(f"{field_name} 必须是非空字符串")


def _validate_frame(frame: int) -> None:
    if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
        raise HealingValidationError("frame 必须是非负整数")


def _validate_character_ref(ref: AttributeSubjectRef, field_name: str) -> None:
    if not isinstance(ref, AttributeSubjectRef):
        raise HealingValidationError(f"{field_name} 必须是 AttributeSubjectRef")
    if ref.kind is not AttributeSubjectKind.CHARACTER:
        raise UnsupportedHealingSubjectError("治疗来源和目标第一版必须是角色主体")


def _normalize_tags(tags: frozenset[str]) -> frozenset[str]:
    normalized = frozenset(tags)
    for tag in normalized:
        _validate_non_empty_text(tag, "healing tag")
    return normalized


@dataclass(frozen=True, slots=True)
class HealingScalingTerm:
    """一次治疗中单个属性缩放组件的契约。"""

    component_key: str
    attribute_key: AttributeKey
    coefficient: float

    def __post_init__(self) -> None:
        """规范化缩放倍率，并拒绝非公共属性或负倍率。"""

        _validate_non_empty_text(self.component_key, "component_key")
        if not isinstance(self.attribute_key, AttributeKey):
            raise InvalidHealingAttributeError("attribute_key 必须是 AttributeKey")
        if not is_public_attribute_key(self.attribute_key):
            raise InvalidHealingAttributeError(f"治疗缩放属性必须是公共属性：{self.attribute_key}")
        coefficient = validate_non_negative_healing_float(self.coefficient, "coefficient")
        object.__setattr__(self, "coefficient", coefficient)


@dataclass(frozen=True, slots=True)
class HealingRequest:
    """进入治疗结算器前已经明确来源、目标和公式参数的请求。"""

    healing_id: str
    frame: int
    source_ref: AttributeSubjectRef
    target_ref: AttributeSubjectRef
    scaling_terms: tuple[HealingScalingTerm, ...] = ()
    flat_healing: float = 0.0
    source_context: RuntimeSourceRef | None = None
    tags: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        """冻结集合字段，并校验第一版治疗请求的边界条件。"""

        _validate_non_empty_text(self.healing_id, "healing_id")
        _validate_frame(self.frame)
        _validate_character_ref(self.source_ref, "source_ref")
        _validate_character_ref(self.target_ref, "target_ref")
        if self.source_context is not None and not isinstance(
            self.source_context,
            RuntimeSourceRef,
        ):
            raise HealingValidationError("source_context 必须是 RuntimeSourceRef 或 None")
        terms = tuple(self.scaling_terms)
        for term in terms:
            if not isinstance(term, HealingScalingTerm):
                raise HealingValidationError("scaling_terms 必须全部是 HealingScalingTerm")
        component_keys = [term.component_key for term in terms]
        if len(component_keys) != len(set(component_keys)):
            raise HealingValidationError("HealingRequest component_key 不能重复")
        flat_healing = validate_non_negative_healing_float(self.flat_healing, "flat_healing")
        object.__setattr__(self, "scaling_terms", terms)
        object.__setattr__(self, "flat_healing", flat_healing)
        object.__setattr__(self, "tags", _normalize_tags(self.tags))


@dataclass(frozen=True, slots=True)
class HealingComponentResult:
    """治疗缩放组件在结算后的属性值、倍率和贡献值。"""

    component_key: str
    attribute_key: AttributeKey
    scaling_value: float
    coefficient: float
    value: float

    def __post_init__(self) -> None:
        """规范化组件审计字段。"""

        _validate_non_empty_text(self.component_key, "component_key")
        if not isinstance(self.attribute_key, AttributeKey):
            raise InvalidHealingAttributeError("attribute_key 必须是 AttributeKey")
        for field_name in ("scaling_value", "coefficient", "value"):
            object.__setattr__(
                self,
                field_name,
                validate_healing_float(getattr(self, field_name), field_name),
            )

    def to_dict(self) -> dict[str, object]:
        """返回可持久化的 component 审计字段。"""

        return {
            "component_key": self.component_key,
            "attribute_key": str(self.attribute_key),
            "scaling_value": self.scaling_value,
            "coefficient": self.coefficient,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class HealingResult:
    """一次治疗完成理论结算后的不可变结果和审计数据。"""

    healing_id: str
    frame: int
    source_ref: AttributeSubjectRef
    target_ref: AttributeSubjectRef
    component_results: tuple[HealingComponentResult, ...]
    flat_healing: float
    base_healing: float
    outgoing_healing_bonus: float
    incoming_healing_bonus: float
    healing_bonus_multiplier: float
    final_healing: float
    source_context: RuntimeSourceRef | None = None
    tags: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        """冻结审计集合，并保证治疗输出是有限非负数。"""

        _validate_non_empty_text(self.healing_id, "healing_id")
        _validate_frame(self.frame)
        _validate_character_ref(self.source_ref, "source_ref")
        _validate_character_ref(self.target_ref, "target_ref")
        if self.source_context is not None and not isinstance(
            self.source_context,
            RuntimeSourceRef,
        ):
            raise HealingValidationError("source_context 必须是 RuntimeSourceRef 或 None")
        component_results = tuple(self.component_results)
        for component in component_results:
            if not isinstance(component, HealingComponentResult):
                raise HealingValidationError("component_results 必须全部是 HealingComponentResult")
        object.__setattr__(self, "component_results", component_results)
        for field_name in (
            "flat_healing",
            "base_healing",
            "outgoing_healing_bonus",
            "incoming_healing_bonus",
            "healing_bonus_multiplier",
            "final_healing",
        ):
            object.__setattr__(
                self,
                field_name,
                validate_healing_float(getattr(self, field_name), field_name),
            )
        if self.base_healing < 0:
            raise InvalidHealingResultError("base_healing 不能为负数")
        if self.healing_bonus_multiplier < 0:
            raise InvalidHealingResultError("healing_bonus_multiplier 不能为负数")
        if self.final_healing < 0:
            raise InvalidHealingResultError("final_healing 不能为负数")
        object.__setattr__(self, "tags", _normalize_tags(self.tags))

    def to_dict(self) -> dict[str, object]:
        """返回适合事件和结果投影使用的可序列化字典。"""

        source_context = None
        if self.source_context is not None:
            source_context = _runtime_source_ref_to_dict(self.source_context)
        return {
            "healing_id": self.healing_id,
            "frame": self.frame,
            "source_ref": _subject_ref_to_dict(self.source_ref),
            "target_ref": _subject_ref_to_dict(self.target_ref),
            "component_results": tuple(component.to_dict() for component in self.component_results),
            "flat_healing": self.flat_healing,
            "base_healing": self.base_healing,
            "outgoing_healing_bonus": self.outgoing_healing_bonus,
            "incoming_healing_bonus": self.incoming_healing_bonus,
            "healing_bonus_multiplier": self.healing_bonus_multiplier,
            "final_healing": self.final_healing,
            "source_context": source_context,
            "tags": tuple(sorted(self.tags)),
        }


def _subject_ref_to_dict(ref: AttributeSubjectRef) -> dict[str, str]:
    return {"kind": ref.kind.value, "entity_id": ref.entity_id}


def _runtime_source_ref_to_dict(ref: RuntimeSourceRef) -> dict[str, str | None]:
    return {
        "kind": ref.kind.value,
        "source_key": ref.source_key,
        "instance_id": ref.instance_id,
    }
