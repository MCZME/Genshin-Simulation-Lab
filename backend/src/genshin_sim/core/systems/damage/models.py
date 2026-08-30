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
from genshin_sim.core.elements import Element, TransformativeReactionSourceKind
from genshin_sim.core.systems.damage.enums import (
    CritOutcome,
    DamageModifierStage,
    DamageReactionCapability,
    DamageType,
    LunarReactionDamageMode,
)
from genshin_sim.core.systems.damage.errors import (
    DamageValidationError,
    InvalidDamageScalingError,
)

_CHARACTER_TARGET_DAMAGE_PROFILE_KEYS = frozenset(
    {
        "damage_profile.reaction.bloom_explosion",
        "damage_profile.reaction.hyperbloom",
        "damage_profile.reaction.burgeon",
        "damage_profile.reaction.lunar_bloom",
    }
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
class DamageProfile:
    """主攻击标签映射到完整伤害公式的稳定定义。"""

    profile_key: str
    damage_type: DamageType
    main_attack_tags: frozenset[str]
    reaction_capabilities: frozenset[DamageReactionCapability] = frozenset()

    def __post_init__(self) -> None:
        _validate_non_empty_text(self.profile_key, "profile_key")
        if not isinstance(self.damage_type, DamageType):
            raise DamageValidationError("DamageProfile 的 damage_type 不受支持")
        tags = frozenset(self.main_attack_tags)
        if not tags:
            raise DamageValidationError("DamageProfile 至少需要一个主攻击标签")
        for tag in tags:
            _validate_non_empty_text(tag, "main_attack_tag")
        object.__setattr__(self, "main_attack_tags", tags)
        capabilities = frozenset(self.reaction_capabilities)
        if any(not isinstance(capability, DamageReactionCapability) for capability in capabilities):
            raise DamageValidationError("DamageProfile 包含不支持的 reaction capability")
        object.__setattr__(self, "reaction_capabilities", capabilities)


@dataclass(frozen=True, slots=True)
class AmplifyingReactionInput:
    """Damage 接收的强类型增幅反应输入。"""

    occurrence_ref: str
    reaction_profile_key: str
    trigger_element: Element
    base_multiplier: float
    reaction_bonus: float = 0.0

    def __post_init__(self) -> None:
        _validate_non_empty_text(self.occurrence_ref, "occurrence_ref")
        _validate_non_empty_text(self.reaction_profile_key, "reaction_profile_key")
        if not isinstance(self.trigger_element, Element):
            raise DamageValidationError("trigger_element 不受支持")
        base_multiplier = validate_damage_float(self.base_multiplier, "base_multiplier")
        if base_multiplier <= 0:
            raise DamageValidationError("base_multiplier 必须为正数")
        reaction_bonus = validate_damage_float(self.reaction_bonus, "reaction_bonus")
        if 1 + reaction_bonus <= 0:
            raise DamageValidationError("reaction_bonus 不能使反应乘数为非正数")
        object.__setattr__(self, "base_multiplier", base_multiplier)
        object.__setattr__(self, "reaction_bonus", reaction_bonus)


@dataclass(frozen=True, slots=True)
class SecondaryAmplifyingReactionInput:
    """扩散剧变伤害作为 Base Hit 时使用的捕获式增幅输入。"""

    target_impact_ref: str
    occurrence_ref: str
    reaction_profile_key: str
    trigger_element: Element
    base_multiplier: float
    captured_elemental_mastery: float
    reaction_bonus: float = 0.0

    def __post_init__(self) -> None:
        for value, name in (
            (self.target_impact_ref, "target_impact_ref"),
            (self.occurrence_ref, "occurrence_ref"),
            (self.reaction_profile_key, "reaction_profile_key"),
        ):
            _validate_non_empty_text(value, name)
        if not isinstance(self.trigger_element, Element):
            raise DamageValidationError("trigger_element 不受支持")
        base_multiplier = validate_damage_float(self.base_multiplier, "base_multiplier")
        if base_multiplier <= 0:
            raise DamageValidationError("base_multiplier 必须为正数")
        captured_mastery = validate_damage_float(
            self.captured_elemental_mastery,
            "captured_elemental_mastery",
        )
        if captured_mastery < 0:
            raise DamageValidationError("captured_elemental_mastery 不能为负数")
        reaction_bonus = validate_damage_float(self.reaction_bonus, "reaction_bonus")
        if 1 + reaction_bonus <= 0:
            raise DamageValidationError("reaction_bonus 不能使反应乘数为非正数")
        object.__setattr__(self, "base_multiplier", base_multiplier)
        object.__setattr__(self, "captured_elemental_mastery", captured_mastery)
        object.__setattr__(self, "reaction_bonus", reaction_bonus)


@dataclass(frozen=True, slots=True)
class SecondaryAmplifyingReactionResolution:
    """二次蒸发或融化乘区的不可变审计结果。"""

    reaction: SecondaryAmplifyingReactionInput
    mastery_bonus: float
    multiplier: float

    def __post_init__(self) -> None:
        if not isinstance(self.reaction, SecondaryAmplifyingReactionInput):
            raise DamageValidationError("二次增幅审计必须引用 SecondaryAmplifyingReactionInput")
        mastery_bonus = validate_damage_float(self.mastery_bonus, "mastery_bonus")
        expected_mastery_bonus = (
            2.78
            * self.reaction.captured_elemental_mastery
            / (self.reaction.captured_elemental_mastery + 1400)
        )
        if not math.isclose(mastery_bonus, expected_mastery_bonus, rel_tol=0.0, abs_tol=1e-12):
            raise DamageValidationError("二次增幅 mastery_bonus 必须匹配捕获元素精通")
        multiplier = validate_damage_float(self.multiplier, "multiplier")
        expected_multiplier = self.reaction.base_multiplier * (
            1 + mastery_bonus + self.reaction.reaction_bonus
        )
        if not math.isclose(multiplier, expected_multiplier, rel_tol=0.0, abs_tol=1e-12):
            raise DamageValidationError("二次增幅 multiplier 必须匹配捕获式公式")
        if multiplier <= 0:
            raise DamageValidationError("二次增幅 multiplier 必须为正数")
        object.__setattr__(self, "mastery_bonus", mastery_bonus)
        object.__setattr__(self, "multiplier", multiplier)


@dataclass(frozen=True, slots=True)
class CatalyzeReactionInput:
    """Damage 接收的强类型激化基础伤害增加输入。"""

    target_impact_ref: str
    occurrence_ref: str
    reaction_profile_key: str
    trigger_element: Element
    reaction_multiplier: float
    reaction_bonus: float = 0.0

    def __post_init__(self) -> None:
        for value, name in (
            (self.target_impact_ref, "target_impact_ref"),
            (self.occurrence_ref, "occurrence_ref"),
            (self.reaction_profile_key, "reaction_profile_key"),
        ):
            _validate_non_empty_text(value, name)
        if not isinstance(self.trigger_element, Element):
            raise DamageValidationError("trigger_element 不受支持")
        reaction_multiplier = validate_damage_float(
            self.reaction_multiplier,
            "reaction_multiplier",
        )
        if reaction_multiplier <= 0:
            raise DamageValidationError("reaction_multiplier 必须为正数")
        reaction_bonus = validate_damage_float(self.reaction_bonus, "reaction_bonus")
        object.__setattr__(self, "reaction_multiplier", reaction_multiplier)
        object.__setattr__(self, "reaction_bonus", reaction_bonus)


@dataclass(frozen=True, slots=True)
class TransformativeReactionInput:
    """剧变派生伤害在 occurrence 时冻结的完整公式输入。"""

    occurrence_ref: str | None
    reaction_profile_key: str
    source_kind: TransformativeReactionSourceKind
    source_level: int
    level_multiplier_table_key: str
    level_multiplier: float
    elemental_mastery: float
    mastery_bonus: float
    reaction_bonus: float
    base_multiplier: float
    defense_policy: str = "approximate_unity"
    cause_ref: str | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.reaction_profile_key, "reaction_profile_key"),
            (self.level_multiplier_table_key, "level_multiplier_table_key"),
            (self.defense_policy, "defense_policy"),
        ):
            _validate_non_empty_text(value, name)
        if self.occurrence_ref is None and self.cause_ref is None:
            raise DamageValidationError("剧变输入必须具有 occurrence_ref 或 cause_ref")
        if self.occurrence_ref is not None:
            _validate_non_empty_text(self.occurrence_ref, "occurrence_ref")
        if self.cause_ref is None:
            object.__setattr__(self, "cause_ref", self.occurrence_ref)
        else:
            _validate_non_empty_text(self.cause_ref, "cause_ref")
        if not isinstance(self.source_kind, TransformativeReactionSourceKind):
            raise DamageValidationError("剧变反应来源分类不受支持")
        if isinstance(self.source_level, bool) or not isinstance(self.source_level, int):
            raise DamageValidationError("剧变反应来源等级必须是整数")
        for field_name in (
            "level_multiplier",
            "elemental_mastery",
            "mastery_bonus",
            "reaction_bonus",
            "base_multiplier",
        ):
            object.__setattr__(
                self,
                field_name,
                validate_damage_float(getattr(self, field_name), field_name),
            )
        if self.level_multiplier <= 0 or self.base_multiplier <= 0:
            raise DamageValidationError("剧变等级系数和基础倍率必须为正数")
        if self.elemental_mastery < 0:
            raise DamageValidationError("剧变元素精通不能为负数")
        if self.defense_policy != "approximate_unity":
            raise DamageValidationError("剧变反应只支持 approximate_unity 防御策略")
        expected_mastery_bonus = 16 * self.elemental_mastery / (self.elemental_mastery + 2000)
        if not math.isclose(self.mastery_bonus, expected_mastery_bonus, rel_tol=0.0, abs_tol=1e-12):
            raise DamageValidationError("剧变 mastery_bonus 必须匹配已冻结元素精通")
        if 1 + self.mastery_bonus + self.reaction_bonus <= 0:
            raise DamageValidationError("剧变反应乘数必须为正数")


@dataclass(frozen=True, slots=True)
class LunarReactionParticipantInput:
    """月曜伤害中一个角色参与者的 Damage 侧输入。"""

    participant_ref: AttributeSubjectRef
    source_level: int
    scaling_terms: tuple[DamageScalingTerm, ...] = ()
    flat_base_damage: float = 0.0
    additional_base_damage: float = 0.0
    can_crit: bool = True
    ascension_multiplier: float = 1.0

    def __post_init__(self) -> None:
        if self.participant_ref.kind is not AttributeSubjectKind.CHARACTER:
            raise DamageValidationError("月曜伤害参与者必须是角色主体")
        if (
            isinstance(self.source_level, bool)
            or not isinstance(self.source_level, int)
            or self.source_level <= 0
        ):
            raise DamageValidationError("月曜伤害参与者等级必须是正整数")
        terms = tuple(self.scaling_terms)
        if any(not isinstance(term, DamageScalingTerm) for term in terms):
            raise DamageValidationError("月曜伤害参与者 scaling_terms 不受支持")
        component_keys = [term.component_key for term in terms]
        if len(component_keys) != len(set(component_keys)):
            raise InvalidDamageScalingError("月曜伤害参与者 component_key 不能重复")
        flat_base_damage = validate_damage_float(
            self.flat_base_damage,
            "lunar participant flat_base_damage",
        )
        additional_base_damage = validate_damage_float(
            self.additional_base_damage,
            "lunar participant additional_base_damage",
        )
        if additional_base_damage < 0:
            raise DamageValidationError("月曜伤害参与者 additional_base_damage 不能为负数")
        if not isinstance(self.can_crit, bool):
            raise DamageValidationError("月曜伤害参与者 can_crit 必须是布尔值")
        ascension_multiplier = validate_damage_float(
            self.ascension_multiplier,
            "lunar participant ascension_multiplier",
        )
        if ascension_multiplier <= 0:
            raise DamageValidationError("月曜伤害参与者 ascension_multiplier 必须为正数")
        object.__setattr__(self, "scaling_terms", terms)
        object.__setattr__(self, "flat_base_damage", flat_base_damage)
        object.__setattr__(self, "additional_base_damage", additional_base_damage)
        object.__setattr__(self, "ascension_multiplier", ascension_multiplier)


@dataclass(frozen=True, slots=True)
class LunarReactionDamageInput:
    """月曜完整公式使用的单来源或多来源输入。"""

    reaction_profile_key: str
    mode: LunarReactionDamageMode
    participants: tuple[LunarReactionParticipantInput, ...]
    reaction_multiplier: float
    base_damage_bonus: float = 0.0
    reaction_bonus: float = 0.0
    occurrence_ref: str | None = None

    def __post_init__(self) -> None:
        _validate_non_empty_text(self.reaction_profile_key, "reaction_profile_key")
        if not isinstance(self.mode, LunarReactionDamageMode):
            raise DamageValidationError("月曜伤害 mode 不受支持")
        participants = tuple(self.participants)
        if not participants:
            raise DamageValidationError("月曜伤害至少需要一个参与者")
        if any(not isinstance(item, LunarReactionParticipantInput) for item in participants):
            raise DamageValidationError("月曜伤害 participants 不受支持")
        participant_ids = [item.participant_ref.entity_id for item in participants]
        if len(participant_ids) != len(set(participant_ids)):
            raise DamageValidationError("月曜伤害 participants 不能重复角色")
        if self.mode is LunarReactionDamageMode.CHARACTER_DIRECT and len(participants) != 1:
            raise DamageValidationError("角色直接月曜伤害必须只有一个参与者")
        participants = tuple(sorted(participants, key=lambda item: item.participant_ref.entity_id))
        reaction_multiplier = validate_damage_float(
            self.reaction_multiplier,
            "lunar reaction_multiplier",
        )
        if reaction_multiplier <= 0:
            raise DamageValidationError("月曜 reaction_multiplier 必须为正数")
        base_damage_bonus = validate_damage_float(
            self.base_damage_bonus,
            "lunar base_damage_bonus",
        )
        reaction_bonus = validate_damage_float(self.reaction_bonus, "lunar reaction_bonus")
        if 1 + base_damage_bonus <= 0:
            raise DamageValidationError("月曜 base_damage_bonus 不能使基础倍率为非正数")
        object.__setattr__(self, "participants", participants)
        object.__setattr__(self, "reaction_multiplier", reaction_multiplier)
        object.__setattr__(self, "base_damage_bonus", base_damage_bonus)
        object.__setattr__(self, "reaction_bonus", reaction_bonus)
        if self.occurrence_ref is not None:
            _validate_non_empty_text(self.occurrence_ref, "occurrence_ref")

    @property
    def participant_refs(self) -> tuple[AttributeSubjectRef, ...]:
        """返回本次月曜伤害实际使用的角色引用。"""

        return tuple(item.participant_ref for item in self.participants)

    def to_dict(self) -> dict[str, object]:
        """返回稳定的月曜输入摘要。"""

        return {
            "reaction_profile_key": self.reaction_profile_key,
            "mode": self.mode.value,
            "participant_refs": tuple(item.participant_ref.entity_id for item in self.participants),
            "reaction_multiplier": self.reaction_multiplier,
            "base_damage_bonus": self.base_damage_bonus,
            "reaction_bonus": self.reaction_bonus,
            "occurrence_ref": self.occurrence_ref,
        }


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
    element: Element
    source_context: RuntimeSourceRef
    scaling_terms: tuple[DamageScalingTerm, ...] = ()
    flat_base_damage: float = 0.0
    tags: frozenset[str] = frozenset()
    can_crit: bool = True
    profile_key: str | None = None
    # 这一次伤害的显示名称，来自 DamageImpactSpec.display_name；缺失时审计回退 action_key。
    damage_name: str | None = None
    reaction_capabilities: frozenset[DamageReactionCapability] = frozenset()
    amplifying_reaction: AmplifyingReactionInput | None = None
    secondary_amplifying_reaction: SecondaryAmplifyingReactionInput | None = None
    transformative_reaction: TransformativeReactionInput | None = None
    catalyze_reaction: CatalyzeReactionInput | None = None
    lunar_reaction: LunarReactionDamageInput | None = None

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
        if self.target_ref.kind not in {
            AttributeSubjectKind.TARGET,
            AttributeSubjectKind.CHARACTER,
        }:
            raise DamageValidationError("伤害目标必须是目标或角色主体")
        for field_name, value in (
            ("source_level", self.source_level),
            ("target_level", self.target_level),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise DamageValidationError(f"{field_name} 必须是正整数")
        if not isinstance(self.element, Element):
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
        if self.profile_key is not None:
            _validate_non_empty_text(self.profile_key, "profile_key")
        if (
            self.target_ref.kind is AttributeSubjectKind.CHARACTER
            and self.profile_key not in _CHARACTER_TARGET_DAMAGE_PROFILE_KEYS
        ):
            raise DamageValidationError("只有绽放系列 DamageProfile 可以指定角色受方")
        capabilities = frozenset(self.reaction_capabilities)
        if any(not isinstance(capability, DamageReactionCapability) for capability in capabilities):
            raise DamageValidationError("DamageRequest 包含不支持的 reaction capability")
        if self.secondary_amplifying_reaction is not None and not isinstance(
            self.secondary_amplifying_reaction,
            SecondaryAmplifyingReactionInput,
        ):
            raise DamageValidationError("secondary_amplifying_reaction 不受支持")
        if self.lunar_reaction is not None and not isinstance(
            self.lunar_reaction,
            LunarReactionDamageInput,
        ):
            raise DamageValidationError("lunar_reaction 不受支持")
        if self.damage_type is DamageType.LUNAR_REACTION:
            if self.lunar_reaction is None:
                raise DamageValidationError("月曜伤害必须提供 LunarReactionDamageInput")
            if self.transformative_reaction is not None:
                raise DamageValidationError("月曜伤害不能同时提供剧变反应输入")
            if self.secondary_amplifying_reaction is not None:
                raise DamageValidationError("月曜伤害不能同时提供二次增幅输入")
            if self.amplifying_reaction is not None:
                raise DamageValidationError("月曜伤害不能同时提供增幅反应输入")
            if self.catalyze_reaction is not None:
                raise DamageValidationError("月曜伤害不能同时提供激化输入")
            if terms or flat_base_damage != 0:
                raise DamageValidationError("月曜伤害不能携带普通倍率或 flat base")
        elif self.damage_type is DamageType.TRANSFORMATIVE_REACTION:
            if self.transformative_reaction is None:
                raise DamageValidationError("剧变伤害必须提供 TransformativeReactionInput")
            if self.lunar_reaction is not None:
                raise DamageValidationError("剧变伤害不能同时提供月曜反应输入")
            if self.amplifying_reaction is not None:
                raise DamageValidationError("剧变伤害不能同时提供增幅反应输入")
            if self.secondary_amplifying_reaction is not None:
                if self.profile_key is None:
                    raise DamageValidationError("二次增幅剧变伤害必须提供 DamageProfile")
                if DamageReactionCapability.SECONDARY_AMPLIFYING not in capabilities:
                    raise DamageValidationError("DamageProfile 未声明二次增幅 capability")
            if terms or flat_base_damage != 0 or self.can_crit:
                raise DamageValidationError("剧变伤害不能携带普通倍率、flat base 或暴击能力")
        else:
            if self.lunar_reaction is not None:
                raise DamageValidationError("非月曜伤害不能提供 LunarReactionDamageInput")
            if self.transformative_reaction is not None:
                raise DamageValidationError("非剧变伤害不能提供 TransformativeReactionInput")
            if self.secondary_amplifying_reaction is not None:
                raise DamageValidationError("非剧变伤害不能提供二次增幅反应输入")
        if self.catalyze_reaction is not None:
            if not isinstance(self.catalyze_reaction, CatalyzeReactionInput):
                raise DamageValidationError("catalyze_reaction 不受支持")
            if self.damage_type is not DamageType.CATALYZE_REACTION:
                raise DamageValidationError("只有激化完整公式可以接收 CatalyzeReactionInput")
            if self.amplifying_reaction is not None:
                raise DamageValidationError("激化伤害不能同时提供增幅反应输入")
            if self.catalyze_reaction.trigger_element.value != self.element.value:
                raise DamageValidationError("激化 trigger_element 必须匹配当前伤害元素")
        elif (
            self.damage_type is DamageType.CATALYZE_REACTION
            and self.amplifying_reaction is not None
        ):
            raise DamageValidationError("激化伤害不能同时提供增幅反应输入")
        object.__setattr__(self, "scaling_terms", terms)
        object.__setattr__(self, "flat_base_damage", flat_base_damage)
        object.__setattr__(self, "tags", tags)
        object.__setattr__(self, "reaction_capabilities", capabilities)


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
    # provider 显示名：由收集器从 ProviderSpec.display_name 注入，内容未提供时为 None。
    provider_display_name: str | None = None

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

    def to_dict(self) -> dict[str, object]:
        """返回伤害修饰项的稳定审计序列化。"""

        return {
            "stage": self.stage.value,
            "value": self.value,
            "provider_key": self.provider_key,
            "provider_display_name": self.provider_display_name,
            "source_ref": self.source_ref.to_dict(),
            "component_key": self.component_key,
            "stacking_group": self.stacking_group,
            "audit_tags": tuple(self.audit_tags),
        }


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

    def to_dict(self) -> dict[str, object]:
        """返回倍率组件的审计序列化。"""

        return {
            "component_key": self.component_key,
            "attribute_key": self.attribute_key.value,
            "attribute_value": self.attribute_value,
            "original_coefficient": self.original_coefficient,
            "final_coefficient": self.final_coefficient,
            "damage": self.damage,
        }


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

    def to_dict(self) -> dict[str, object]:
        """返回固定基础伤害加值的审计序列化。"""

        return {
            "addition_key": self.addition_key,
            "value": self.value,
            "source_ref": self.source_ref.to_dict(),
            "audit_tags": tuple(self.audit_tags),
        }


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

    def to_dict(self) -> dict[str, object]:
        """返回增伤区的审计序列化。"""

        return {
            "element_bonus": self.element_bonus,
            "modifier_bonus": self.modifier_bonus,
            "multiplier": self.multiplier,
        }


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

    def to_dict(self) -> dict[str, object]:
        """返回暴击区的审计序列化。"""

        return {
            "can_crit": self.can_crit,
            "crit_rate": self.crit_rate,
            "effective_crit_rate": self.effective_crit_rate,
            "crit_damage": self.crit_damage,
            "outcome": self.outcome.value,
            "multiplier": self.multiplier,
        }


@dataclass(frozen=True, slots=True)
class GeneralReactionZoneResolution:
    """通用公式反应区审计，保存增幅反应的全部中间量。"""

    multiplier: float = 1.0
    occurrence_ref: str | None = None
    reaction_profile_key: str | None = None
    base_multiplier: float = 1.0
    elemental_mastery: float = 0.0
    mastery_bonus: float = 0.0
    reaction_bonus: float = 0.0
    elemental_mastery_trace: AttributeResolution | None = None

    def __post_init__(self) -> None:
        """校验反应区乘数。"""

        for field_name in (
            "multiplier",
            "base_multiplier",
            "elemental_mastery",
            "mastery_bonus",
            "reaction_bonus",
        ):
            object.__setattr__(
                self,
                field_name,
                validate_damage_float(getattr(self, field_name), field_name),
            )
        if self.multiplier <= 0 or self.base_multiplier <= 0:
            raise DamageValidationError("反应区乘数必须为正数")
        if self.elemental_mastery < 0:
            raise DamageValidationError("元素精通不能为负数")
        if self.occurrence_ref is not None:
            _validate_non_empty_text(self.occurrence_ref, "occurrence_ref")
        if self.reaction_profile_key is not None:
            _validate_non_empty_text(self.reaction_profile_key, "reaction_profile_key")


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

    def to_dict(self) -> dict[str, object]:
        """返回防御区的审计序列化。"""

        return {
            "source_level": self.source_level,
            "target_level": self.target_level,
            "defense_reduction": self.defense_reduction,
            "defense_ignore": self.defense_ignore,
            "multiplier": self.multiplier,
        }


@dataclass(frozen=True, slots=True)
class ResistanceResolution:
    """抗性区 policy 的输入抗性和最终乘数。"""

    resistance: float
    multiplier: float

    def __post_init__(self) -> None:
        """规范化抗性区审计数值。"""

        object.__setattr__(self, "resistance", validate_damage_float(self.resistance, "resistance"))
        object.__setattr__(self, "multiplier", validate_damage_float(self.multiplier, "multiplier"))

    def to_dict(self) -> dict[str, object]:
        """返回抗性区的审计序列化。"""

        return {
            "resistance": self.resistance,
            "multiplier": self.multiplier,
        }


@dataclass(frozen=True, slots=True)
class LunarReactionComponentResolution:
    """月曜伤害中一个角色组分完成公式后的审计结果。"""

    participant_ref: AttributeSubjectRef
    source_level: int
    base_damage_source: str
    scaling: ScalingZoneResolution | None
    core_base_damage: float
    reaction_multiplier: float
    base_damage_bonus: float
    elemental_mastery: float
    mastery_bonus: float
    reaction_bonus: float
    reaction_uplift_multiplier: float
    base_damage_after_reaction: float
    additional_base_damage: float
    critical: CriticalZoneResolution
    ascension_multiplier: float
    resistance: ResistanceResolution
    component_damage: float
    weight: float
    weighted_damage: float
    source_attribute_trace: tuple[AttributeResolution, ...] = ()
    target_attribute_trace: tuple[AttributeResolution, ...] = ()
    applied_terms: tuple[DamageModifierTerm, ...] = ()
    rejected_terms: tuple[DamageModifierTerm, ...] = ()

    def __post_init__(self) -> None:
        if self.participant_ref.kind is not AttributeSubjectKind.CHARACTER:
            raise DamageValidationError("月曜伤害组分参与者必须是角色主体")
        if (
            isinstance(self.source_level, bool)
            or not isinstance(self.source_level, int)
            or self.source_level <= 0
        ):
            raise DamageValidationError("月曜伤害组分 source_level 必须是正整数")
        _validate_non_empty_text(self.base_damage_source, "base_damage_source")
        if self.scaling is not None and not isinstance(self.scaling, ScalingZoneResolution):
            raise DamageValidationError("月曜伤害组分 scaling 不受支持")
        if not isinstance(self.critical, CriticalZoneResolution):
            raise DamageValidationError("月曜伤害组分 critical 不受支持")
        if not isinstance(self.resistance, ResistanceResolution):
            raise DamageValidationError("月曜伤害组分 resistance 不受支持")
        for field_name in (
            "core_base_damage",
            "reaction_multiplier",
            "base_damage_bonus",
            "elemental_mastery",
            "mastery_bonus",
            "reaction_bonus",
            "reaction_uplift_multiplier",
            "base_damage_after_reaction",
            "additional_base_damage",
            "ascension_multiplier",
            "component_damage",
            "weight",
            "weighted_damage",
        ):
            object.__setattr__(
                self,
                field_name,
                validate_damage_float(getattr(self, field_name), field_name),
            )
        if self.elemental_mastery < 0:
            raise DamageValidationError("月曜伤害组分元素精通不能为负数")
        if self.reaction_multiplier <= 0 or self.reaction_uplift_multiplier <= 0:
            raise DamageValidationError("月曜伤害组分反应乘数必须为正数")
        if self.additional_base_damage < 0 or self.ascension_multiplier <= 0:
            raise DamageValidationError("月曜伤害组分基础加值和擢升倍率必须合法")
        if self.component_damage < 0 or self.weight < 0 or self.weighted_damage < 0:
            raise DamageValidationError("月曜伤害组分结果不能为负数")
        expected_weighted_damage = self.component_damage * self.weight
        if not math.isclose(
            self.weighted_damage,
            expected_weighted_damage,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise DamageValidationError("月曜伤害组分 weighted_damage 必须匹配权重")
        object.__setattr__(self, "source_attribute_trace", tuple(self.source_attribute_trace))
        object.__setattr__(self, "target_attribute_trace", tuple(self.target_attribute_trace))
        object.__setattr__(self, "applied_terms", tuple(self.applied_terms))
        object.__setattr__(self, "rejected_terms", tuple(self.rejected_terms))

    def to_dict(self) -> dict[str, object]:
        """返回组分的完整数值审计摘要。"""

        return {
            "participant_ref": self.participant_ref.entity_id,
            "source_level": self.source_level,
            "base_damage_source": self.base_damage_source,
            "core_base_damage": self.core_base_damage,
            "reaction_multiplier": self.reaction_multiplier,
            "base_damage_bonus": self.base_damage_bonus,
            "elemental_mastery": self.elemental_mastery,
            "mastery_bonus": self.mastery_bonus,
            "reaction_bonus": self.reaction_bonus,
            "reaction_uplift_multiplier": self.reaction_uplift_multiplier,
            "base_damage_after_reaction": self.base_damage_after_reaction,
            "additional_base_damage": self.additional_base_damage,
            "crit_outcome": self.critical.outcome.value,
            "crit_rate": self.critical.crit_rate,
            "crit_damage": self.critical.crit_damage,
            "crit_multiplier": self.critical.multiplier,
            "ascension_multiplier": self.ascension_multiplier,
            "resistance_multiplier": self.resistance.multiplier,
            "component_damage": self.component_damage,
            "weight": self.weight,
            "weighted_damage": self.weighted_damage,
        }


@dataclass(frozen=True, slots=True)
class LunarReactionDamageResolution:
    """月曜伤害完成所有组分结算、排序和加权后的结果。"""

    reaction: LunarReactionDamageInput
    components: tuple[LunarReactionComponentResolution, ...]
    weighted_base_damage: float
    resistance: ResistanceResolution
    official_damage: float
    debug_multiplier: float
    final_damage: float
    source_attribute_trace: tuple[AttributeResolution, ...] = ()
    target_attribute_trace: tuple[AttributeResolution, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.reaction, LunarReactionDamageInput):
            raise DamageValidationError("月曜伤害 reaction 必须是 LunarReactionDamageInput")
        components = tuple(self.components)
        if not components:
            raise DamageValidationError("月曜伤害 resolution 至少需要一个组分")
        if any(not isinstance(item, LunarReactionComponentResolution) for item in components):
            raise DamageValidationError("月曜伤害 components 不受支持")
        if not isinstance(self.resistance, ResistanceResolution):
            raise DamageValidationError("月曜伤害 resistance 不受支持")
        for field_name in (
            "weighted_base_damage",
            "official_damage",
            "debug_multiplier",
            "final_damage",
        ):
            object.__setattr__(
                self,
                field_name,
                validate_damage_float(getattr(self, field_name), field_name),
            )
        if self.weighted_base_damage < 0 or self.official_damage < 0 or self.final_damage < 0:
            raise DamageValidationError("月曜伤害 resolution 不能为负数")
        if self.debug_multiplier < 0:
            raise DamageValidationError("月曜 debug_multiplier 不能为负数")
        expected_participants = {item.participant_ref for item in self.reaction.participants}
        actual_participants = {item.participant_ref for item in components}
        if actual_participants != expected_participants:
            raise DamageValidationError("月曜伤害 components 必须覆盖且仅覆盖参与者")
        expected_weighted_base_damage = math.fsum(
            item.base_damage_after_reaction * item.weight for item in components
        )
        if not math.isclose(
            self.weighted_base_damage,
            expected_weighted_base_damage,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise DamageValidationError("月曜 weighted_base_damage 必须匹配组分权重")
        expected_official_damage = math.fsum(item.weighted_damage for item in components)
        if not math.isclose(
            self.official_damage,
            expected_official_damage,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise DamageValidationError("月曜伤害 official_damage 必须匹配组分加权合计")
        expected_final_damage = self.official_damage * self.debug_multiplier
        if not math.isclose(
            self.final_damage,
            expected_final_damage,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise DamageValidationError("月曜伤害 final_damage 必须匹配 debug_multiplier")
        object.__setattr__(self, "components", components)
        object.__setattr__(self, "source_attribute_trace", tuple(self.source_attribute_trace))
        object.__setattr__(self, "target_attribute_trace", tuple(self.target_attribute_trace))

    def to_dict(self) -> dict[str, object]:
        """返回月曜伤害的完整聚合审计摘要。"""

        return {
            "reaction": self.reaction.to_dict(),
            "participant_refs": tuple(
                item.participant_ref.entity_id for item in self.reaction.participants
            ),
            "components": tuple(item.to_dict() for item in self.components),
            "weighted_base_damage": self.weighted_base_damage,
            "resistance_multiplier": self.resistance.multiplier,
            "official_damage": self.official_damage,
            "debug_multiplier": self.debug_multiplier,
            "final_damage": self.final_damage,
        }


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


@dataclass(frozen=True, slots=True)
class TransformativeReactionResolution:
    """剧变公式的不可变审计结果。"""

    reaction: TransformativeReactionInput
    defense: DefenseResolution
    resistance: ResistanceResolution
    official_damage: float
    debug_multiplier: float
    final_damage: float
    target_attribute_trace: tuple[AttributeResolution, ...] = ()
    secondary_amplifying_resolution: SecondaryAmplifyingReactionResolution | None = None

    def __post_init__(self) -> None:
        for field_name in ("official_damage", "debug_multiplier", "final_damage"):
            value = validate_damage_float(getattr(self, field_name), field_name)
            if value < 0:
                raise DamageValidationError(f"{field_name} 不能为负数")
            object.__setattr__(self, field_name, value)
        if self.secondary_amplifying_resolution is not None and not isinstance(
            self.secondary_amplifying_resolution,
            SecondaryAmplifyingReactionResolution,
        ):
            raise DamageValidationError("secondary_amplifying_resolution 不受支持")
        object.__setattr__(self, "target_attribute_trace", tuple(self.target_attribute_trace))


@dataclass(frozen=True, slots=True)
class CatalyzeReactionResolution:
    """激化基础伤害增加区的不可变审计结果。"""

    target_impact_ref: str
    occurrence_ref: str
    reaction_profile_key: str
    trigger_element: Element
    source_level: int
    level_multiplier_table_key: str
    level_multiplier: float
    elemental_mastery: float
    mastery_bonus: float
    reaction_multiplier: float
    reaction_bonus: float
    base_damage_addition: BaseDamageAddition
    elemental_mastery_trace: AttributeResolution | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.target_impact_ref, "target_impact_ref"),
            (self.occurrence_ref, "occurrence_ref"),
            (self.reaction_profile_key, "reaction_profile_key"),
            (self.level_multiplier_table_key, "level_multiplier_table_key"),
        ):
            _validate_non_empty_text(value, name)
        if not isinstance(self.trigger_element, Element):
            raise DamageValidationError("trigger_element 不受支持")
        if isinstance(self.source_level, bool) or not isinstance(self.source_level, int):
            raise DamageValidationError("source_level 必须是整数")
        if self.source_level <= 0:
            raise DamageValidationError("source_level 必须是正整数")
        if not isinstance(self.base_damage_addition, BaseDamageAddition):
            raise DamageValidationError("base_damage_addition 必须是 BaseDamageAddition")
        for field_name in (
            "level_multiplier",
            "elemental_mastery",
            "mastery_bonus",
            "reaction_multiplier",
            "reaction_bonus",
        ):
            object.__setattr__(
                self,
                field_name,
                validate_damage_float(getattr(self, field_name), field_name),
            )
        if self.level_multiplier <= 0 or self.reaction_multiplier <= 0:
            raise DamageValidationError("激化等级系数和反应倍率必须为正数")
        if self.elemental_mastery < 0:
            raise DamageValidationError("元素精通不能为负数")
        expected_mastery_bonus = 5 * self.elemental_mastery / (1200 + self.elemental_mastery)
        if not math.isclose(self.mastery_bonus, expected_mastery_bonus, rel_tol=0.0, abs_tol=1e-12):
            raise DamageValidationError("激化 mastery_bonus 必须匹配实时元素精通")
        expected_addition = (
            self.level_multiplier
            * self.reaction_multiplier
            * (1 + self.mastery_bonus + self.reaction_bonus)
        )
        if not math.isclose(
            self.base_damage_addition.value,
            expected_addition,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise DamageValidationError("激化 base_damage_addition 必须匹配已确认公式")
        if expected_addition < 0:
            raise DamageValidationError("激化基础伤害附加值不能为负数")


@dataclass(frozen=True, slots=True)
class CatalyzeReactionDamageResolution:
    """激化完整公式的各区审计与输出结果。"""

    scaling: ScalingZoneResolution
    damage_bonus: DamageBonusZoneResolution
    critical: CriticalZoneResolution
    reaction: GeneralReactionZoneResolution
    defense: DefenseResolution
    resistance: ResistanceResolution
    official_damage: float
    debug_multiplier: float
    final_damage: float
    catalyze: CatalyzeReactionResolution | None = None
    source_attribute_trace: tuple[AttributeResolution, ...] = ()
    target_attribute_trace: tuple[AttributeResolution, ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("official_damage", "debug_multiplier", "final_damage"):
            value = validate_damage_float(getattr(self, field_name), field_name)
            if value < 0:
                raise DamageValidationError(f"{field_name} 不能为负数")
            object.__setattr__(self, field_name, value)
        if self.catalyze is not None and not isinstance(self.catalyze, CatalyzeReactionResolution):
            raise DamageValidationError("catalyze 必须是 CatalyzeReactionResolution")
        object.__setattr__(self, "source_attribute_trace", tuple(self.source_attribute_trace))
        object.__setattr__(self, "target_attribute_trace", tuple(self.target_attribute_trace))


type DamageFormulaResolution = (
    GeneralDamageResolution
    | CatalyzeReactionDamageResolution
    | TransformativeReactionResolution
    | LunarReactionDamageResolution
)


@dataclass(frozen=True, slots=True)
class DamageResult:
    """一次直接伤害完成结算后的不可变结果和审计数据。"""

    request_id: str
    frame: int
    damage_type: DamageType
    source_ref: AttributeSubjectRef
    target_ref: AttributeSubjectRef
    element: Element
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
    damage_name: str | None = None
    reaction_details: GeneralReactionZoneResolution | TransformativeReactionInput | None = None
    secondary_amplifying_resolution: SecondaryAmplifyingReactionResolution | None = None
    catalyze_reaction_resolution: CatalyzeReactionResolution | None = None
    lunar_reaction_resolution: LunarReactionDamageResolution | None = None
    component_results: tuple[DamageComponentResult, ...] = ()
    source_attribute_trace: tuple[AttributeResolution, ...] = ()
    target_attribute_trace: tuple[AttributeResolution, ...] = ()
    applied_terms: tuple[DamageModifierTerm, ...] = ()
    rejected_terms: tuple[DamageModifierTerm, ...] = ()
    trace_level: TraceLevel = TraceLevel.FULL
    trace_metadata: Mapping[str, object] = field(default_factory=dict)
    damage_bonus_zone: DamageBonusZoneResolution | None = None
    critical_zone: CriticalZoneResolution | None = None

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
        if self.secondary_amplifying_resolution is not None and not isinstance(
            self.secondary_amplifying_resolution,
            SecondaryAmplifyingReactionResolution,
        ):
            raise DamageValidationError("secondary_amplifying_resolution 不受支持")
        if self.catalyze_reaction_resolution is not None and not isinstance(
            self.catalyze_reaction_resolution,
            CatalyzeReactionResolution,
        ):
            raise DamageValidationError("catalyze_reaction_resolution 不受支持")
        if self.lunar_reaction_resolution is not None and not isinstance(
            self.lunar_reaction_resolution,
            LunarReactionDamageResolution,
        ):
            raise DamageValidationError("lunar_reaction_resolution 不受支持")
        if self.damage_bonus_zone is not None and not isinstance(
            self.damage_bonus_zone,
            DamageBonusZoneResolution,
        ):
            raise DamageValidationError("damage_bonus_zone 不受支持")
        if self.critical_zone is not None and not isinstance(
            self.critical_zone,
            CriticalZoneResolution,
        ):
            raise DamageValidationError("critical_zone 不受支持")
        if (
            self.lunar_reaction_resolution is not None
            and self.damage_type is not DamageType.LUNAR_REACTION
        ):
            raise DamageValidationError("只有月曜伤害可以携带 lunar_reaction_resolution")
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
            "damage_name": self.damage_name,
            "base_damage": self.base_damage,
            "damage_bonus_multiplier": self.damage_bonus_multiplier,
            "crit_outcome": self.crit_outcome.value,
            "crit_rate": self.crit_rate,
            "crit_damage": self.crit_damage,
            "crit_multiplier": self.crit_multiplier,
            "reaction_multiplier": self.reaction_multiplier,
            "reaction": _reaction_details_to_dict(self.reaction_details),
            "secondary_amplifying_reaction": _secondary_amplifying_to_dict(
                self.secondary_amplifying_resolution
            ),
            "catalyze_reaction": _catalyze_reaction_to_dict(self.catalyze_reaction_resolution),
            "lunar_reaction": _lunar_reaction_to_dict(self.lunar_reaction_resolution),
            "defense_multiplier": self.defense.multiplier,
            "resistance_multiplier": self.resistance.multiplier,
            "final_multiplier": self.final_multiplier,
            "official_damage": self.official_damage,
            "debug_multiplier": self.debug_multiplier,
            "final_damage": self.final_damage,
        }

    def to_audit_dict(self) -> dict[str, object]:
        """返回完整伤害公式审计；字段只增不改，供 DAMAGE_RESOLVED 的 audit 载荷使用。"""

        return {
            "component_results": tuple(item.to_dict() for item in self.component_results),
            "base_damage_additions": tuple(item.to_dict() for item in self.base_damage_additions),
            "damage_bonus": _damage_bonus_audit_to_dict(self),
            "critical": _critical_audit_to_dict(self),
            "defense": self.defense.to_dict(),
            "resistance": self.resistance.to_dict(),
            "reaction": _audit_reaction_to_dict(self),
            "applied_terms": tuple(item.to_dict() for item in self.applied_terms),
            "rejected_terms": tuple(item.to_dict() for item in self.rejected_terms),
            "source_attribute_trace": tuple(item.to_dict() for item in self.source_attribute_trace),
            "target_attribute_trace": tuple(item.to_dict() for item in self.target_attribute_trace),
            "trace_metadata": dict(self.trace_metadata),
        }


def _damage_bonus_audit_to_dict(result: DamageResult) -> dict[str, object]:
    zone = result.damage_bonus_zone
    if zone is not None:
        return zone.to_dict()
    return {
        "element_bonus": 0.0,
        "modifier_bonus": 0.0,
        "multiplier": result.damage_bonus_multiplier,
    }


def _critical_audit_to_dict(result: DamageResult) -> dict[str, object]:
    zone = result.critical_zone
    if zone is not None:
        return zone.to_dict()
    effective_crit_rate = result.trace_metadata.get("effective_crit_rate", 0.0)
    if isinstance(effective_crit_rate, bool) or not isinstance(effective_crit_rate, int | float):
        effective_crit_rate = 0.0
    return {
        "can_crit": result.crit_outcome is not CritOutcome.NOT_APPLICABLE,
        "crit_rate": result.crit_rate,
        "effective_crit_rate": float(effective_crit_rate),
        "crit_damage": result.crit_damage,
        "outcome": result.crit_outcome.value,
        "multiplier": result.crit_multiplier,
    }


def _audit_reaction_to_dict(result: DamageResult) -> dict[str, object] | None:
    if (
        result.damage_type is DamageType.LUNAR_REACTION
        and result.lunar_reaction_resolution is not None
    ):
        lunar_payload = _lunar_reaction_to_dict(result.lunar_reaction_resolution)
        if lunar_payload is not None:
            return {"kind": "lunar", **lunar_payload}
        return None
    if result.catalyze_reaction_resolution is not None:
        catalyze_payload = _catalyze_reaction_to_dict(result.catalyze_reaction_resolution)
        if catalyze_payload is not None:
            return {"kind": "catalyze", **catalyze_payload}
        return None
    if isinstance(result.reaction_details, TransformativeReactionInput):
        payload = _reaction_details_to_dict(result.reaction_details)
        if payload is not None and result.secondary_amplifying_resolution is not None:
            payload["secondary_amplifying"] = _secondary_amplifying_to_dict(
                result.secondary_amplifying_resolution
            )
        return payload
    if isinstance(result.reaction_details, GeneralReactionZoneResolution):
        if result.reaction_details.occurrence_ref is None:
            return None
        payload = _reaction_details_to_dict(result.reaction_details)
        if payload is not None and result.secondary_amplifying_resolution is not None:
            payload["secondary_amplifying"] = _secondary_amplifying_to_dict(
                result.secondary_amplifying_resolution
            )
        return payload
    return None


def _reaction_details_to_dict(
    details: GeneralReactionZoneResolution | TransformativeReactionInput | None,
) -> dict[str, object] | None:
    if details is None:
        return None
    if isinstance(details, TransformativeReactionInput):
        payload = {
            "kind": "transformative",
            "occurrence_ref": details.occurrence_ref,
            "reaction_profile_key": details.reaction_profile_key,
            "source_kind": details.source_kind.value,
            "source_level": details.source_level,
            "level_multiplier_table_key": details.level_multiplier_table_key,
            "level_multiplier": details.level_multiplier,
            "base_multiplier": details.base_multiplier,
            "elemental_mastery": details.elemental_mastery,
            "mastery_bonus": details.mastery_bonus,
            "reaction_bonus": details.reaction_bonus,
            "defense_policy": details.defense_policy,
        }
        if details.cause_ref != details.occurrence_ref:
            payload["cause_ref"] = details.cause_ref
        return payload
    return {
        "kind": "amplifying",
        "occurrence_ref": details.occurrence_ref,
        "reaction_profile_key": details.reaction_profile_key,
        "base_multiplier": details.base_multiplier,
        "elemental_mastery": details.elemental_mastery,
        "mastery_bonus": details.mastery_bonus,
        "reaction_bonus": details.reaction_bonus,
        "multiplier": details.multiplier,
    }


def _secondary_amplifying_to_dict(
    resolution: SecondaryAmplifyingReactionResolution | None,
) -> dict[str, object] | None:
    if resolution is None:
        return None
    reaction = resolution.reaction
    return {
        "target_impact_ref": reaction.target_impact_ref,
        "occurrence_ref": reaction.occurrence_ref,
        "reaction_profile_key": reaction.reaction_profile_key,
        "trigger_element": reaction.trigger_element.value,
        "base_multiplier": reaction.base_multiplier,
        "captured_elemental_mastery": reaction.captured_elemental_mastery,
        "mastery_bonus": resolution.mastery_bonus,
        "reaction_bonus": reaction.reaction_bonus,
        "multiplier": resolution.multiplier,
    }


def _catalyze_reaction_to_dict(
    resolution: CatalyzeReactionResolution | None,
) -> dict[str, object] | None:
    if resolution is None:
        return None
    return {
        "target_impact_ref": resolution.target_impact_ref,
        "occurrence_ref": resolution.occurrence_ref,
        "reaction_profile_key": resolution.reaction_profile_key,
        "trigger_element": resolution.trigger_element.value,
        "source_level": resolution.source_level,
        "level_multiplier_table_key": resolution.level_multiplier_table_key,
        "level_multiplier": resolution.level_multiplier,
        "elemental_mastery": resolution.elemental_mastery,
        "mastery_bonus": resolution.mastery_bonus,
        "reaction_multiplier": resolution.reaction_multiplier,
        "reaction_bonus": resolution.reaction_bonus,
        "base_damage_addition": resolution.base_damage_addition.value,
        "addition_key": resolution.base_damage_addition.addition_key,
    }


def _lunar_reaction_to_dict(
    resolution: LunarReactionDamageResolution | None,
) -> dict[str, object] | None:
    if resolution is None:
        return None
    return resolution.to_dict()
