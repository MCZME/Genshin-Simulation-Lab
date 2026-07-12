"""伤害系统的请求、查询、结果和审计值对象。"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from genshin_sim.core.attributes import (
    AttributeKey,
    AttributeQueryContext,
    AttributeResolution,
    AttributeSubjectKind,
    AttributeSubjectRef,
    RuntimeSourceRef,
    TraceLevel,
)
from genshin_sim.core.systems.damage.enums import (
    CritOutcome,
    DamageElement,
    DamageModifierStage,
    DamageType,
)
from genshin_sim.core.systems.damage.errors import (
    DamageValidationError,
    InvalidDamageScalingError,
)


def validate_damage_float(value: float | int, field_name: str) -> float:
    """校验伤害流水线中的数值字段，并返回标准 ``float``。"""

    if isinstance(value, bool) or not isinstance(value, int | float):
        raise DamageValidationError(f"{field_name} 必须是数字")
    result = float(value)
    if not math.isfinite(result):
        raise DamageValidationError(f"{field_name} 必须是有限数字")
    if result == 0.0:
        return 0.0
    return result


def _validate_non_empty_text(value: str, field_name: str) -> None:
    """校验稳定标识字段必须是非空文本。"""

    if not isinstance(value, str) or not value.strip():
        raise DamageValidationError(f"{field_name} 必须是非空字符串")


@dataclass(frozen=True, slots=True)
class DamageScalingTerm:
    """一次伤害中单个属性倍率组件的契约。"""

    component_key: str
    attribute_key: AttributeKey
    coefficient: float

    def __post_init__(self) -> None:
        """规范化倍率并拒绝普通直伤不支持的负倍率。"""

        _validate_non_empty_text(self.component_key, "component_key")
        coefficient = validate_damage_float(self.coefficient, "coefficient")
        if coefficient < 0:
            raise InvalidDamageScalingError("普通直伤 coefficient 不能为负数")
        object.__setattr__(self, "coefficient", coefficient)


@dataclass(frozen=True, slots=True)
class DamageRequest:
    """进入伤害结算器前已经解析出来源、目标和倍率的类型化请求。"""

    request_id: str
    frame: int
    damage_type: DamageType
    impact_key: str
    source_ref: AttributeSubjectRef
    target_ref: AttributeSubjectRef
    source_level: int
    target_level: int
    element: DamageElement
    source_context: RuntimeSourceRef
    scaling_terms: tuple[DamageScalingTerm, ...] = ()
    flat_base_damage: float = 0.0
    tags: frozenset[str] = frozenset()
    can_crit: bool = True

    def __post_init__(self) -> None:
        """冻结集合字段，并校验第一版直接伤害的边界条件。"""

        _validate_non_empty_text(self.request_id, "request_id")
        _validate_non_empty_text(self.impact_key, "impact_key")
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise DamageValidationError("frame 必须是非负整数")
        if not isinstance(self.damage_type, DamageType):
            raise DamageValidationError("damage_type 不受支持")
        if self.source_ref.kind is not AttributeSubjectKind.CHARACTER:
            raise DamageValidationError("伤害来源第一版必须是角色主体")
        if self.target_ref.kind is not AttributeSubjectKind.TARGET:
            raise DamageValidationError("伤害目标第一版必须是目标主体")
        for field_name, value in (
            ("source_level", self.source_level),
            ("target_level", self.target_level),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise DamageValidationError(f"{field_name} 必须是正整数")
        if not isinstance(self.element, DamageElement):
            raise DamageValidationError("element 不受支持")
        if not isinstance(self.source_context, RuntimeSourceRef):
            raise DamageValidationError("source_context 必须是 RuntimeSourceRef")
        terms = tuple(self.scaling_terms)
        component_keys = [term.component_key for term in terms]
        if len(component_keys) != len(set(component_keys)):
            raise InvalidDamageScalingError("DamageRequest component_key 不能重复")
        flat_base_damage = validate_damage_float(self.flat_base_damage, "flat_base_damage")

        tags = frozenset(self.tags)
        for tag in tags:
            _validate_non_empty_text(tag, "damage tag")
        if not isinstance(self.can_crit, bool):
            raise DamageValidationError("can_crit 必须是布尔值")
        object.__setattr__(self, "scaling_terms", terms)
        object.__setattr__(self, "flat_base_damage", flat_base_damage)
        object.__setattr__(self, "tags", tags)


@dataclass(frozen=True, slots=True)
class DamageQuery:
    """伤害 provider 与 resolver 共享的一次结算查询上下文。"""

    request: DamageRequest
    source_attribute_context: AttributeQueryContext
    target_attribute_context: AttributeQueryContext


@dataclass(frozen=True, slots=True)
class DamageModifierTerm:
    """伤害专用 modifier provider 返回的单个乘区修饰项。"""

    stage: DamageModifierStage
    value: float
    provider_key: str
    source_ref: RuntimeSourceRef
    component_key: str | None = None
    stacking_group: str | None = None
    audit_tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """校验修饰阶段、component 绑定和审计标签。"""

        if not isinstance(self.stage, DamageModifierStage):
            raise DamageValidationError("damage modifier stage 不受支持")
        object.__setattr__(self, "value", validate_damage_float(self.value, "modifier value"))
        _validate_non_empty_text(self.provider_key, "provider_key")
        component_stage = self.stage in {
            DamageModifierStage.COMPONENT_COEFFICIENT_PERCENT_ADD,
            DamageModifierStage.COMPONENT_COEFFICIENT_FLAT_ADD,
        }
        if component_stage:
            if self.component_key is None:
                raise DamageValidationError("component modifier 必须提供 component_key")
            _validate_non_empty_text(self.component_key, "component_key")
        elif self.component_key is not None:
            raise DamageValidationError("非 component modifier 不能提供 component_key")
        if self.stacking_group is not None:
            _validate_non_empty_text(self.stacking_group, "stacking_group")
        for tag in self.audit_tags:
            _validate_non_empty_text(tag, "audit_tag")
        object.__setattr__(self, "audit_tags", tuple(self.audit_tags))


@dataclass(frozen=True, slots=True)
class DamageComponentResult:
    """倍率组件在结算后的属性值、最终倍率和基础伤害贡献。"""

    component_key: str
    attribute_key: AttributeKey
    attribute_value: float
    original_coefficient: float
    final_coefficient: float
    damage: float

    def __post_init__(self) -> None:
        """规范化组件结果中的数值字段。"""

        _validate_non_empty_text(self.component_key, "component_key")
        for field_name in (
            "attribute_value",
            "original_coefficient",
            "final_coefficient",
            "damage",
        ):
            object.__setattr__(
                self,
                field_name,
                validate_damage_float(getattr(self, field_name), field_name),
            )


@dataclass(frozen=True, slots=True)
class BaseDamageAddition:
    """倍率区中的固定基础伤害加值审计项。"""

    addition_key: str
    value: float
    source_ref: RuntimeSourceRef
    audit_tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """校验加值身份、数值和来源。"""

        _validate_non_empty_text(self.addition_key, "addition_key")
        object.__setattr__(self, "value", validate_damage_float(self.value, "addition value"))
        if not isinstance(self.source_ref, RuntimeSourceRef):
            raise DamageValidationError("base damage addition source_ref 必须是 RuntimeSourceRef")
        for tag in self.audit_tags:
            _validate_non_empty_text(tag, "audit_tag")
        object.__setattr__(self, "audit_tags", tuple(self.audit_tags))


@dataclass(frozen=True, slots=True)
class ScalingZoneResolution:
    """通用公式倍率区的组件贡献、固定加值和区结果。"""

    component_results: tuple[DamageComponentResult, ...]
    additions: tuple[BaseDamageAddition, ...]
    value: float

    def __post_init__(self) -> None:
        """冻结审计集合并校验倍率区结果。"""

        object.__setattr__(self, "component_results", tuple(self.component_results))
        object.__setattr__(self, "additions", tuple(self.additions))
        object.__setattr__(self, "value", validate_damage_float(self.value, "scaling value"))


@dataclass(frozen=True, slots=True)
class DamageBonusZoneResolution:
    """通用公式增伤区的元素增伤、修饰增伤和最终乘数。"""

    element_bonus: float
    modifier_bonus: float
    multiplier: float

    def __post_init__(self) -> None:
        """规范化增伤区审计数值。"""

        for field_name in ("element_bonus", "modifier_bonus", "multiplier"):
            object.__setattr__(
                self,
                field_name,
                validate_damage_float(getattr(self, field_name), field_name),
            )


@dataclass(frozen=True, slots=True)
class CriticalZoneResolution:
    """通用公式暴击区的输入、决策和最终乘数。"""

    can_crit: bool
    crit_rate: float
    effective_crit_rate: float
    crit_damage: float
    outcome: CritOutcome
    multiplier: float

    def __post_init__(self) -> None:
        """规范化暴击区审计数值。"""

        if not isinstance(self.can_crit, bool):
            raise DamageValidationError("can_crit 必须是布尔值")
        if not isinstance(self.outcome, CritOutcome):
            raise DamageValidationError("crit outcome 不受支持")
        for field_name in ("crit_rate", "effective_crit_rate", "crit_damage", "multiplier"):
            object.__setattr__(
                self,
                field_name,
                validate_damage_float(getattr(self, field_name), field_name),
            )


@dataclass(frozen=True, slots=True)
class GeneralReactionZoneResolution:
    """通用公式反应区审计。第一轮无反应时固定为 1.0。"""

    multiplier: float = 1.0

    def __post_init__(self) -> None:
        """校验反应区乘数。"""

        object.__setattr__(self, "multiplier", validate_damage_float(self.multiplier, "multiplier"))


@dataclass(frozen=True, slots=True)
class DefenseResolution:
    """防御区 policy 的输入和最终乘数。"""

    source_level: int
    target_level: int
    defense_reduction: float
    defense_ignore: float
    multiplier: float

    def __post_init__(self) -> None:
        """规范化防御区审计数值。"""

        for field_name in (
            "defense_reduction",
            "defense_ignore",
            "multiplier",
        ):
            object.__setattr__(
                self,
                field_name,
                validate_damage_float(getattr(self, field_name), field_name),
            )


@dataclass(frozen=True, slots=True)
class ResistanceResolution:
    """抗性区 policy 的输入抗性和最终乘数。"""

    resistance: float
    multiplier: float

    def __post_init__(self) -> None:
        """规范化抗性区审计数值。"""

        object.__setattr__(self, "resistance", validate_damage_float(self.resistance, "resistance"))
        object.__setattr__(self, "multiplier", validate_damage_float(self.multiplier, "multiplier"))


@dataclass(frozen=True, slots=True)
class DebugDamageAdjustment:
    """正式伤害公式之外的显式调试倍率。"""

    multiplier: float = 1.0

    def __post_init__(self) -> None:
        """调试倍率只能是有限非负值。"""

        multiplier = validate_damage_float(self.multiplier, "debug_multiplier")
        if multiplier < 0:
            raise DamageValidationError("debug_multiplier 不能为负数")
        object.__setattr__(self, "multiplier", multiplier)


@dataclass(frozen=True, slots=True)
class GeneralDamageResolution:
    """通用完整公式的各区审计与输出结果。"""

    scaling: ScalingZoneResolution
    damage_bonus: DamageBonusZoneResolution
    critical: CriticalZoneResolution
    reaction: GeneralReactionZoneResolution
    defense: DefenseResolution
    resistance: ResistanceResolution
    official_damage: float
    debug_multiplier: float
    final_damage: float
    source_attribute_trace: tuple[AttributeResolution, ...] = ()
    target_attribute_trace: tuple[AttributeResolution, ...] = ()

    def __post_init__(self) -> None:
        """校验通用公式输出为有限非负数。"""

        for field_name in ("official_damage", "debug_multiplier", "final_damage"):
            value = validate_damage_float(getattr(self, field_name), field_name)
            if value < 0:
                raise DamageValidationError(f"{field_name} 不能为负数")
            object.__setattr__(self, field_name, value)
        object.__setattr__(self, "source_attribute_trace", tuple(self.source_attribute_trace))
        object.__setattr__(self, "target_attribute_trace", tuple(self.target_attribute_trace))


type DamageFormulaResolution = GeneralDamageResolution


@dataclass(frozen=True, slots=True)
class DamageResult:
    """一次直接伤害完成结算后的不可变结果和审计数据。"""

    request_id: str
    frame: int
    damage_type: DamageType
    source_ref: AttributeSubjectRef
    target_ref: AttributeSubjectRef
    element: DamageElement
    base_damage: float
    base_damage_additions: tuple[BaseDamageAddition, ...]
    damage_bonus_multiplier: float
    crit_outcome: CritOutcome
    crit_rate: float
    crit_damage: float
    crit_multiplier: float
    reaction_multiplier: float
    defense: DefenseResolution
    resistance: ResistanceResolution
    official_damage: float
    debug_multiplier: float
    final_damage: float
    component_results: tuple[DamageComponentResult, ...] = ()
    source_attribute_trace: tuple[AttributeResolution, ...] = ()
    target_attribute_trace: tuple[AttributeResolution, ...] = ()
    applied_terms: tuple[DamageModifierTerm, ...] = ()
    rejected_terms: tuple[DamageModifierTerm, ...] = ()
    trace_level: TraceLevel = TraceLevel.FULL
    trace_metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """规范化结果集合，保证最终伤害是有限非负值。"""

        _validate_non_empty_text(self.request_id, "request_id")
        if not isinstance(self.damage_type, DamageType):
            raise DamageValidationError("damage_type 不受支持")
        if not isinstance(self.crit_outcome, CritOutcome):
            raise DamageValidationError("crit_outcome 不受支持")
        if not isinstance(self.trace_level, TraceLevel):
            raise DamageValidationError("trace_level 不受支持")
        for field_name in (
            "base_damage",
            "damage_bonus_multiplier",
            "crit_rate",
            "crit_damage",
            "crit_multiplier",
            "reaction_multiplier",
            "official_damage",
            "debug_multiplier",
            "final_damage",
        ):
            object.__setattr__(
                self,
                field_name,
                validate_damage_float(getattr(self, field_name), field_name),
            )
        if self.final_damage < 0:
            raise DamageValidationError("final_damage 不能为负数")
        if self.official_damage < 0:
            raise DamageValidationError("official_damage 不能为负数")
        if self.debug_multiplier < 0:
            raise DamageValidationError("debug_multiplier 不能为负数")
        object.__setattr__(self, "base_damage_additions", tuple(self.base_damage_additions))
        object.__setattr__(self, "component_results", tuple(self.component_results))
        object.__setattr__(self, "source_attribute_trace", tuple(self.source_attribute_trace))
        object.__setattr__(self, "target_attribute_trace", tuple(self.target_attribute_trace))
        object.__setattr__(self, "applied_terms", tuple(self.applied_terms))
        object.__setattr__(self, "rejected_terms", tuple(self.rejected_terms))
        object.__setattr__(self, "trace_metadata", MappingProxyType(dict(self.trace_metadata)))

    @property
    def final_multiplier(self) -> float:
        """兼容旧审计命名，当前等同于正式公式之外的调试倍率。"""

        return self.debug_multiplier

    def to_dict(self) -> dict[str, object]:
        """返回适合事件和结果投影使用的扁平摘要字典。"""

        return {
            "request_id": self.request_id,
            "frame": self.frame,
            "damage_type": self.damage_type.value,
            "source_ref": self.source_ref.entity_id,
            "target_ref": self.target_ref.entity_id,
            "element": self.element.value,
            "base_damage": self.base_damage,
            "damage_bonus_multiplier": self.damage_bonus_multiplier,
            "crit_outcome": self.crit_outcome.value,
            "crit_rate": self.crit_rate,
            "crit_damage": self.crit_damage,
            "crit_multiplier": self.crit_multiplier,
            "reaction_multiplier": self.reaction_multiplier,
            "defense_multiplier": self.defense.multiplier,
            "resistance_multiplier": self.resistance.multiplier,
            "final_multiplier": self.final_multiplier,
            "official_damage": self.official_damage,
            "debug_multiplier": self.debug_multiplier,
            "final_damage": self.final_damage,
        }
