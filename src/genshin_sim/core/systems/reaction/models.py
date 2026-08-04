"""元素 Reaction 的稳定定义、occurrence 和 Effect 契约。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
    ElementalSourceRef,
    ElementalStateLinkRef,
    ElementalSubjectRef,
    TransformativeReactionSourceKind,
)
from genshin_sim.core.impacts import StrikeType
from genshin_sim.core.space import Vector3
from genshin_sim.core.systems.aura import AuraLossPolicy, AuraView
from genshin_sim.core.systems.damage.enums import DamageElement
from genshin_sim.core.systems.reaction.establishment_gates import (
    ReactionEstablishmentGateDecision,
    ReactionEstablishmentGateMutationPlan,
    ReactionEstablishmentGateResolution,
)
from genshin_sim.core.systems.reaction.states import (
    BurningState,
    ElectroChargedState,
    FrozenState,
    QuickenState,
    ReactionStateInstanceRef,
    ScheduledStateTickCause,
)


def _text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 必须是非空字符串")


def _finite_non_negative(value: float | int, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} 必须是数字")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name} 必须是有限非负数")
    return result


def _finite(value: float | int, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} 必须是数字")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} 必须是有限数字")
    return result


class ReactionEntryKind(StrEnum):
    ELEMENTAL_INTERACTION = "elemental_interaction"
    STATE_TRIGGER = "state_trigger"


class ReactionEffectExecutionScope(StrEnum):
    NEXT_SETTLEMENT_ROUND = "next_settlement_round"


@dataclass(frozen=True, slots=True)
class ReactionElementalApplication:
    """通过 Aura ICD 后可参与元素候选的入射元素观察。"""

    element: Element
    amount: AuraAmount

    def __post_init__(self) -> None:
        if not isinstance(self.element, Element):
            raise ValueError("Reaction 元素施加的 element 不受支持")
        if not isinstance(self.amount, AuraAmount) or self.amount.is_zero:
            raise ValueError("Reaction 元素施加的 amount 必须为正的 AuraAmount")


@dataclass(frozen=True, slots=True)
class ReactionTriggerContext:
    """目标级 Reaction 候选的强类型输入，不从 Damage 类型推导状态资格。"""

    elemental_application: ReactionElementalApplication | None = None
    strike_type: StrikeType | None = None

    def __post_init__(self) -> None:
        if self.elemental_application is not None and not isinstance(
            self.elemental_application,
            ReactionElementalApplication,
        ):
            raise ValueError("elemental_application 必须是 ReactionElementalApplication 或 None")
        if self.strike_type is not None and not isinstance(self.strike_type, StrikeType):
            raise ValueError("strike_type 必须是 StrikeType 或 None")
        if self.elemental_application is None and self.strike_type is None:
            raise ValueError("ReactionTriggerContext 至少需要元素施加或打击证据")


@dataclass(frozen=True, slots=True)
class FreezeResistanceObservation:
    """协调器读取的目标冻结抗性；值域和组装策略由属性契约另行冻结。"""

    subject_ref: ElementalSubjectRef
    frame: int
    value: float

    def __post_init__(self) -> None:
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise ValueError("冻结抗性观察 frame 必须是非负整数")
        if isinstance(self.value, bool) or not isinstance(self.value, int | float):
            raise ValueError("冻结抗性观察 value 必须是数字")
        value = float(self.value)
        if not math.isfinite(value):
            raise ValueError("冻结抗性观察 value 必须是有限数字")
        if not 0 <= value <= 1:
            raise ValueError("冻结抗性观察 value 必须在 0 到 1 之间")
        object.__setattr__(self, "value", value)

    @property
    def is_immune(self) -> bool:
        return self.value == 1.0


@dataclass(frozen=True, slots=True)
class CatalyzeImpactQualification:
    """协调器提供的当前 Impact 激化资格证据；Reaction 不重算伤害。"""

    target_impact_ref: str
    damage_element: Element
    has_positive_scaling_coefficient: bool

    def __post_init__(self) -> None:
        _text(self.target_impact_ref, "target_impact_ref")
        if not isinstance(self.damage_element, Element):
            raise ValueError("damage_element 必须是 Element")
        if not isinstance(self.has_positive_scaling_coefficient, bool):
            raise ValueError("has_positive_scaling_coefficient 必须是布尔值")


@dataclass(frozen=True, slots=True)
class ReactionTriggerSignature:
    incoming_element: Element
    observed_aura_kind: AuraKind
    direction_key: str

    def __post_init__(self) -> None:
        _text(self.direction_key, "direction_key")


@dataclass(frozen=True, slots=True)
class AmplifyingReactionProfile:
    profile_key: str
    reaction_key: str
    direction_key: str
    trigger_element: Element
    base_multiplier: float

    def __post_init__(self) -> None:
        for value, name in (
            (self.profile_key, "profile_key"),
            (self.reaction_key, "reaction_key"),
            (self.direction_key, "direction_key"),
        ):
            _text(value, name)
        if self.base_multiplier <= 0:
            raise ValueError("增幅反应基础倍率必须为正数")


# 保留兼容公共名，避免现有内容和测试出现不必要的迁移噪音。
ReactionProfile = AmplifyingReactionProfile


@dataclass(frozen=True, slots=True)
class TransformativeReactionProfile:
    profile_key: str
    reaction_key: str
    direction_key: str
    trigger_element: Element
    damage_profile_key: str
    damage_element: DamageElement
    base_multiplier: float
    gate_definition_key: str
    damage_kind_key: str

    def __post_init__(self) -> None:
        for value, name in (
            (self.profile_key, "profile_key"),
            (self.reaction_key, "reaction_key"),
            (self.direction_key, "direction_key"),
            (self.damage_profile_key, "damage_profile_key"),
            (self.gate_definition_key, "gate_definition_key"),
            (self.damage_kind_key, "damage_kind_key"),
        ):
            _text(value, name)
        if self.base_multiplier <= 0:
            raise ValueError("剧变反应基础倍率必须为正数")
        if not isinstance(self.damage_element, DamageElement):
            raise ValueError("剧变反应 damage_element 必须是 DamageElement")


@dataclass(frozen=True, slots=True)
class BloomReactionProfile:
    """普通绽放方向与草原核创建的冻结参数。"""

    profile_key: str
    reaction_key: str
    direction_key: str
    trigger_element: Element
    dendro_like_kind: AuraKind
    core_state_profile_key: str
    core_spatial_profile_key: str
    lifetime_frames: int = 360
    pool_capacity: int = 5

    def __post_init__(self) -> None:
        for value, name in (
            (self.profile_key, "profile_key"),
            (self.reaction_key, "reaction_key"),
            (self.direction_key, "direction_key"),
            (self.core_state_profile_key, "core_state_profile_key"),
            (self.core_spatial_profile_key, "core_spatial_profile_key"),
        ):
            _text(value, name)
        if self.trigger_element not in {Element.HYDRO, Element.DENDRO}:
            raise ValueError("普通绽放只能由水或草元素触发")
        expected_observed_kind = (
            {AuraKind.DENDRO, AuraKind.QUICKEN}
            if self.trigger_element is Element.HYDRO
            else {AuraKind.HYDRO}
        )
        if self.dendro_like_kind not in expected_observed_kind:
            raise ValueError("普通绽放方向的先手 AuraKind 与触发元素不一致")
        if self.lifetime_frames != 360:
            raise ValueError("普通绽放草原核生命周期必须固定为 360 帧")
        if self.pool_capacity != 5:
            raise ValueError("普通绽放草原核容量必须固定为 5")


@dataclass(frozen=True, slots=True)
class LunarBloomReactionProfile:
    """月绽放方向与草原核创建的冻结参数。"""

    profile_key: str
    reaction_key: str
    direction_key: str
    trigger_element: Element
    dendro_like_kind: AuraKind
    core_state_profile_key: str
    core_spatial_profile_key: str
    lifetime_frames: int = 360
    pool_capacity: int = 5

    def __post_init__(self) -> None:
        for value, name in (
            (self.profile_key, "profile_key"),
            (self.reaction_key, "reaction_key"),
            (self.direction_key, "direction_key"),
            (self.core_state_profile_key, "core_state_profile_key"),
            (self.core_spatial_profile_key, "core_spatial_profile_key"),
        ):
            _text(value, name)
        if self.trigger_element not in {Element.HYDRO, Element.DENDRO}:
            raise ValueError("月绽放只能由水或草元素触发")
        expected_observed_kind = (
            AuraKind.DENDRO if self.trigger_element is Element.HYDRO else AuraKind.HYDRO
        )
        if self.dendro_like_kind is not expected_observed_kind:
            raise ValueError("月绽放只允许严格水草方向")
        if self.lifetime_frames != 360:
            raise ValueError("月绽放草原核生命周期必须固定为 360 帧")
        if self.pool_capacity != 5:
            raise ValueError("月绽放草原核容量必须固定为 5")


@dataclass(frozen=True, slots=True)
class LunarElectroChargedReactionProfile:
    """月感电方向与雷暴云创建的冻结参数。"""

    profile_key: str
    reaction_key: str
    direction_key: str
    trigger_element: Element
    storm_cloud_state_key: str
    storm_cloud_spatial_profile_key: str
    lifetime_frames: int = 360
    first_attack_interval_frames: int = 15
    attack_interval_frames: int = 15

    def __post_init__(self) -> None:
        for value, name in (
            (self.profile_key, "profile_key"),
            (self.reaction_key, "reaction_key"),
            (self.direction_key, "direction_key"),
            (self.storm_cloud_state_key, "storm_cloud_state_key"),
            (self.storm_cloud_spatial_profile_key, "storm_cloud_spatial_profile_key"),
        ):
            _text(value, name)
        if self.trigger_element not in {Element.HYDRO, Element.ELECTRO}:
            raise ValueError("月感电只能由水或雷元素触发")
        for field_name in (
            "lifetime_frames",
            "first_attack_interval_frames",
            "attack_interval_frames",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} 必须是正整数")
        if self.lifetime_frames != 360:
            raise ValueError("雷暴云生命周期必须固定为 360 帧")
        if self.first_attack_interval_frames != 15:
            raise ValueError("雷暴云首次攻击间隔必须固定为 15 帧")
        if self.attack_interval_frames != 15:
            raise ValueError("雷暴云攻击间隔必须固定为 15 帧")


@dataclass(frozen=True, slots=True)
class LunarCrystallizeReactionProfile:
    """月结晶方向与月笼生命周期/飞行冷却的冻结参数。"""

    profile_key: str
    reaction_key: str
    direction_key: str
    trigger_element: Element
    cage_state_key: str
    cage_spatial_profile_key: str
    lifetime_frames: int = 540
    projectile_flight_frames: int = 21

    def __post_init__(self) -> None:
        for value, name in (
            (self.profile_key, "profile_key"),
            (self.reaction_key, "reaction_key"),
            (self.direction_key, "direction_key"),
            (self.cage_state_key, "cage_state_key"),
            (self.cage_spatial_profile_key, "cage_spatial_profile_key"),
        ):
            _text(value, name)
        if self.trigger_element is not Element.GEO:
            raise ValueError("月结晶只能由岩元素触发")
        for field_name in ("lifetime_frames", "projectile_flight_frames"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} 必须是正整数")
        if self.lifetime_frames != 540:
            raise ValueError("月笼生命周期必须固定为 540 帧")
        if self.projectile_flight_frames != 21:
            raise ValueError("月笼投射物飞行帧数必须固定为 21 帧")


@dataclass(frozen=True, slots=True)
class CrystallizeReactionProfile:
    """普通结晶方向、晶片语义与生命周期的静态定义。"""

    profile_key: str
    reaction_key: str
    direction_key: str
    trigger_element: Element
    shard_element: Element
    establishment_gate_definition_key: str
    state_key: str
    formula_key: str
    lifetime_frames: int = 900

    def __post_init__(self) -> None:
        for value, name in (
            (self.profile_key, "profile_key"),
            (self.reaction_key, "reaction_key"),
            (self.direction_key, "direction_key"),
            (self.establishment_gate_definition_key, "establishment_gate_definition_key"),
            (self.state_key, "state_key"),
            (self.formula_key, "formula_key"),
        ):
            _text(value, name)
        if self.trigger_element is not Element.GEO:
            raise ValueError("普通结晶只能由岩元素触发")
        if self.shard_element not in {Element.PYRO, Element.HYDRO, Element.ELECTRO, Element.CRYO}:
            raise ValueError("普通结晶晶片元素必须是火、水、雷或冰")
        if (
            isinstance(self.lifetime_frames, bool)
            or not isinstance(self.lifetime_frames, int)
            or self.lifetime_frames != 900
        ):
            raise ValueError("普通结晶 lifetime_frames 必须固定为 900")


@dataclass(frozen=True, slots=True)
class StateReactionProfile:
    """不直接修改当次伤害的持续状态反应方向 Profile。"""

    profile_key: str
    reaction_key: str
    direction_key: str
    trigger_element: Element

    def __post_init__(self) -> None:
        for value, name in (
            (self.profile_key, "profile_key"),
            (self.reaction_key, "reaction_key"),
            (self.direction_key, "direction_key"),
        ):
            _text(value, name)
        if not isinstance(self.trigger_element, Element):
            raise ValueError("状态反应 trigger_element 必须是 Element")


@dataclass(frozen=True, slots=True)
class AdditiveReactionProfile:
    """激化这类只为当前伤害提供基础增加值的 Reaction Profile。"""

    profile_key: str
    reaction_key: str
    direction_key: str
    trigger_element: Element
    reaction_multiplier: float

    def __post_init__(self) -> None:
        for value, name in (
            (self.profile_key, "profile_key"),
            (self.reaction_key, "reaction_key"),
            (self.direction_key, "direction_key"),
        ):
            _text(value, name)
        if not isinstance(self.trigger_element, Element):
            raise ValueError("附加反应 trigger_element 必须是 Element")
        multiplier = _finite_non_negative(self.reaction_multiplier, "reaction_multiplier")
        if multiplier <= 0:
            raise ValueError("附加反应 reaction_multiplier 必须为正数")
        object.__setattr__(self, "reaction_multiplier", multiplier)


type ReactionProfileVariant = (
    AmplifyingReactionProfile
    | AdditiveReactionProfile
    | CrystallizeReactionProfile
    | LunarBloomReactionProfile
    | LunarCrystallizeReactionProfile
    | LunarElectroChargedReactionProfile
    | BloomReactionProfile
    | StateReactionProfile
    | TransformativeReactionProfile
)


@dataclass(frozen=True, slots=True)
class ElementalTransitionEffect:
    aura_kind: AuraKind
    incoming_before: AuraAmount
    incoming_consumed: AuraAmount
    incoming_remaining: AuraAmount
    aura_before: AuraAmount
    aura_consumed: AuraAmount
    aura_remaining: AuraAmount


@dataclass(frozen=True, slots=True)
class ParallelAuraConsumption:
    """一个后手预算并行作用于普通火与燃元素的精确消费账本。"""

    shared_incoming_before: AuraAmount
    shared_incoming_consumed: AuraAmount
    shared_incoming_remaining: AuraAmount
    branches: tuple[ElementalTransitionEffect, ...]

    def __post_init__(self) -> None:
        for value, name in (
            (self.shared_incoming_before, "shared_incoming_before"),
            (self.shared_incoming_consumed, "shared_incoming_consumed"),
            (self.shared_incoming_remaining, "shared_incoming_remaining"),
        ):
            if not isinstance(value, AuraAmount):
                raise ValueError(f"{name} 必须是 AuraAmount")
        branches = tuple(self.branches)
        if not branches or any(
            not isinstance(item, ElementalTransitionEffect) for item in branches
        ):
            raise ValueError("parallel branches 必须是非空 ElementalTransitionEffect 序列")
        if len(branches) > 2:
            raise ValueError("平行消费最多支持普通火与燃元素两个分支")
        if {item.aura_kind for item in branches} - {AuraKind.PYRO, AuraKind.BURNING}:
            raise ValueError("平行消费只支持普通火与燃元素")
        if len({item.aura_kind for item in branches}) != len(branches):
            raise ValueError("parallel branches 的 AuraKind 不能重复")
        if any(item.incoming_before != self.shared_incoming_before for item in branches):
            raise ValueError("parallel branches 必须共享相同 incoming_before")
        if any(item.incoming_consumed > self.shared_incoming_before for item in branches):
            raise ValueError("parallel branch 不能消耗超出共享后手预算的元素量")
        expected_consumed = max(item.incoming_consumed for item in branches)
        if self.shared_incoming_consumed != expected_consumed:
            raise ValueError("共享后手消耗必须等于各平行分支消耗的最大值")
        if (
            self.shared_incoming_remaining
            != self.shared_incoming_before - self.shared_incoming_consumed
        ):
            raise ValueError("共享后手剩余必须与共享消耗一致")
        object.__setattr__(self, "branches", branches)


@dataclass(frozen=True, slots=True)
class CurrentImpactDamageAdjustment:
    target_impact_ref: str
    occurrence_ref: str
    reaction_profile_key: str
    trigger_element: Element
    base_multiplier: float
    reaction_bonus: float = 0.0

    def __post_init__(self) -> None:
        for value, name in (
            (self.target_impact_ref, "target_impact_ref"),
            (self.occurrence_ref, "occurrence_ref"),
            (self.reaction_profile_key, "reaction_profile_key"),
        ):
            _text(value, name)
        if self.base_multiplier <= 0:
            raise ValueError("增幅反应基础倍率必须为正数")


@dataclass(frozen=True, slots=True)
class CatalyzeCurrentImpactDamageAdjustment:
    """激化对当前 Impact 的基础伤害增加值输入，不复用增幅倍率模型。"""

    adjustment_ref: str
    target_impact_ref: str
    occurrence_ref: str
    reaction_profile_key: str
    trigger_element: Element
    reaction_multiplier: float
    reaction_bonus: float = 0.0

    def __post_init__(self) -> None:
        for value, name in (
            (self.adjustment_ref, "adjustment_ref"),
            (self.target_impact_ref, "target_impact_ref"),
            (self.occurrence_ref, "occurrence_ref"),
            (self.reaction_profile_key, "reaction_profile_key"),
        ):
            _text(value, name)
        if not isinstance(self.trigger_element, Element):
            raise ValueError("激化 trigger_element 必须是 Element")
        multiplier = _finite_non_negative(self.reaction_multiplier, "reaction_multiplier")
        if multiplier <= 0:
            raise ValueError("激化 reaction_multiplier 必须为正数")
        object.__setattr__(self, "reaction_multiplier", multiplier)
        object.__setattr__(
            self,
            "reaction_bonus",
            _finite_non_negative(self.reaction_bonus, "reaction_bonus"),
        )


@dataclass(frozen=True, slots=True)
class TransformativeSourceObservation:
    """协调器提供给 Reaction 的中立、已读取来源事实。"""

    source_ref: ElementalSourceRef
    source_kind: TransformativeReactionSourceKind
    source_level: int
    elemental_mastery: float
    level_multiplier_table_key: str
    level_multiplier: float
    source_observation_ref: str
    source_owner_slot: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_kind, TransformativeReactionSourceKind):
            raise ValueError("剧变来源分类不受支持")
        if isinstance(self.source_level, bool) or not isinstance(self.source_level, int):
            raise ValueError("剧变来源等级必须是整数")
        if self.source_owner_slot is not None and (
            isinstance(self.source_owner_slot, bool)
            or not isinstance(self.source_owner_slot, int)
            or self.source_owner_slot <= 0
        ):
            raise ValueError("source_owner_slot 必须是正整数或 None")
        for value, name in (
            (self.level_multiplier_table_key, "level_multiplier_table_key"),
            (self.source_observation_ref, "source_observation_ref"),
        ):
            _text(value, name)
        object.__setattr__(
            self,
            "elemental_mastery",
            _finite_non_negative(self.elemental_mastery, "elemental_mastery"),
        )
        level_multiplier = _finite_non_negative(self.level_multiplier, "level_multiplier")
        if level_multiplier <= 0:
            raise ValueError("level_multiplier 必须为正数")
        object.__setattr__(self, "level_multiplier", level_multiplier)


@dataclass(frozen=True, slots=True)
class CapturedTransformativeScalingBasis:
    basis_ref: str
    captured_frame: int
    source_ref: ElementalSourceRef
    source_kind: TransformativeReactionSourceKind
    source_level: int
    elemental_mastery: float
    reaction_bonus: float
    reaction_profile_key: str
    damage_profile_key: str
    level_multiplier_table_key: str
    level_multiplier: float
    source_observation_ref: str
    source_owner_slot: int | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.basis_ref, "basis_ref"),
            (self.reaction_profile_key, "reaction_profile_key"),
            (self.damage_profile_key, "damage_profile_key"),
            (self.level_multiplier_table_key, "level_multiplier_table_key"),
            (self.source_observation_ref, "source_observation_ref"),
        ):
            _text(value, name)
        if (
            isinstance(self.captured_frame, bool)
            or not isinstance(self.captured_frame, int)
            or self.captured_frame < 0
        ):
            raise ValueError("captured_frame 必须是非负整数")
        if not isinstance(self.source_kind, TransformativeReactionSourceKind):
            raise ValueError("剧变来源分类不受支持")
        if isinstance(self.source_level, bool) or not isinstance(self.source_level, int):
            raise ValueError("剧变来源等级必须是整数")
        if self.source_owner_slot is not None and (
            isinstance(self.source_owner_slot, bool)
            or not isinstance(self.source_owner_slot, int)
            or self.source_owner_slot <= 0
        ):
            raise ValueError("source_owner_slot 必须是正整数或 None")
        for field_name in ("elemental_mastery", "reaction_bonus", "level_multiplier"):
            object.__setattr__(
                self, field_name, _finite_non_negative(getattr(self, field_name), field_name)
            )
        if self.level_multiplier <= 0:
            raise ValueError("level_multiplier 必须为正数")


@dataclass(frozen=True, slots=True)
class DynamicTransformativeScalingBasis:
    """延迟到实际伤害准备时读取的剧变来源身份。"""

    basis_ref: str
    source_ref: ElementalSourceRef
    source_observation_profile_key: str
    reaction_profile_key: str
    damage_profile_key: str
    reaction_bonus: float = 0.0

    def __post_init__(self) -> None:
        _text(self.basis_ref, "basis_ref")
        for value, name in (
            (self.source_observation_profile_key, "source_observation_profile_key"),
            (self.reaction_profile_key, "reaction_profile_key"),
            (self.damage_profile_key, "damage_profile_key"),
        ):
            _text(value, name)
        if not isinstance(self.source_ref, ElementalSourceRef):
            raise ValueError("source_ref 必须是 ElementalSourceRef")
        object.__setattr__(
            self,
            "reaction_bonus",
            _finite_non_negative(self.reaction_bonus, "reaction_bonus"),
        )


@dataclass(frozen=True, slots=True)
class CrystallizeSourceObservation:
    """结晶成立时从来源读取的最小、专用缩放观察。"""

    source_ref: ElementalSourceRef
    source_level: int
    elemental_mastery: float

    def __post_init__(self) -> None:
        if isinstance(self.source_level, bool) or not isinstance(self.source_level, int):
            raise ValueError("结晶来源等级必须是整数")
        object.__setattr__(
            self,
            "elemental_mastery",
            _finite_non_negative(self.elemental_mastery, "elemental_mastery"),
        )


@dataclass(frozen=True, slots=True)
class CapturedCrystallizeShieldBasis:
    """晶片创建时冻结的独立结晶吸收量，不是 Damage 缩放输入。"""

    source_ref: ElementalSourceRef
    captured_frame: int
    source_level: int
    source_elemental_mastery: float
    crystallize_level_coefficient: float
    elemental_mastery_bonus: float
    native_absorption: float

    def __post_init__(self) -> None:
        if (
            isinstance(self.captured_frame, bool)
            or not isinstance(self.captured_frame, int)
            or self.captured_frame < 0
        ):
            raise ValueError("captured_frame 必须是非负整数")
        if isinstance(self.source_level, bool) or not isinstance(self.source_level, int):
            raise ValueError("source_level 必须是整数")
        for field_name in (
            "source_elemental_mastery",
            "crystallize_level_coefficient",
            "elemental_mastery_bonus",
            "native_absorption",
        ):
            object.__setattr__(
                self,
                field_name,
                _finite_non_negative(getattr(self, field_name), field_name),
            )
        if self.crystallize_level_coefficient <= 0:
            raise ValueError("crystallize_level_coefficient 必须为正数")
        if self.native_absorption <= 0:
            raise ValueError("native_absorption 必须为正数")


@dataclass(frozen=True, slots=True)
class AreaAroundSubjectSelection:
    selection_ref: str
    anchor_subject_ref: ElementalSubjectRef
    radius: float = 5.0
    geometry: str = "circle_xz"
    include_anchor: bool = True
    eligibility_policy_key: str = "reaction_target.hostile_effect"
    sort_policy_key: str = "distance_xz_then_subject_ref"

    def __post_init__(self) -> None:
        for value, name in (
            (self.selection_ref, "selection_ref"),
            (self.geometry, "geometry"),
            (self.eligibility_policy_key, "eligibility_policy_key"),
            (self.sort_policy_key, "sort_policy_key"),
        ):
            _text(value, name)
        if self.geometry != "circle_xz":
            raise ValueError("当前只支持 circle_xz 目标选择")
        if isinstance(self.radius, bool) or not isinstance(self.radius, int | float):
            raise ValueError("radius 必须是正数")
        if not math.isfinite(float(self.radius)) or self.radius <= 0:
            raise ValueError("radius 必须是正数")
        if not isinstance(self.include_anchor, bool):
            raise ValueError("include_anchor 必须是布尔值")


@dataclass(frozen=True, slots=True)
class AreaAroundPositionSelection:
    """使用已校验的不可变位置作为范围查询锚点。"""

    selection_ref: str
    center: Vector3
    radius: float
    eligibility_policy_key: str = "reaction_target.bloom_damage"
    sort_policy_key: str = "distance_xz_then_subject_ref"

    def __post_init__(self) -> None:
        for value, name in (
            (self.selection_ref, "selection_ref"),
            (self.eligibility_policy_key, "eligibility_policy_key"),
            (self.sort_policy_key, "sort_policy_key"),
        ):
            _text(value, name)
        if not isinstance(self.center, Vector3):
            raise ValueError("center 必须是 Vector3")
        if isinstance(self.radius, bool) or not isinstance(self.radius, int | float):
            raise ValueError("radius 必须是正数")
        radius = float(self.radius)
        if not math.isfinite(radius) or radius <= 0:
            raise ValueError("radius 必须是正数")
        object.__setattr__(self, "radius", radius)


@dataclass(frozen=True, slots=True)
class CurrentSubjectSelection:
    """派生 Effect 只作用于当前 occurrence 主体的限定用途目标选择。"""

    selection_ref: str
    subject_ref: ElementalSubjectRef
    eligibility_policy_key: str = "reaction_target.hostile_effect"
    center: Vector3 | None = None
    radius: float | None = None

    def __post_init__(self) -> None:
        _text(self.selection_ref, "selection_ref")
        _text(self.eligibility_policy_key, "eligibility_policy_key")
        if (self.center is None) != (self.radius is None):
            raise ValueError("CurrentSubjectSelection 的 center 与 radius 必须同时存在或同时缺失")
        if self.center is not None:
            if not isinstance(self.center, Vector3):
                raise ValueError("CurrentSubjectSelection.center 必须是 Vector3")
            if isinstance(self.radius, bool) or not isinstance(self.radius, int | float):
                raise ValueError("CurrentSubjectSelection.radius 必须是正数")
            radius = float(self.radius)
            if not math.isfinite(radius) or radius <= 0:
                raise ValueError("CurrentSubjectSelection.radius 必须是正数")
            object.__setattr__(self, "radius", radius)


@dataclass(frozen=True, slots=True)
class ElectroChargedPropagationSelection:
    """普通感电的主目标加水平 13 米水 Aura 传导目标选择。"""

    selection_ref: str
    primary_subject_ref: ElementalSubjectRef
    radius: float = 13.0
    geometry: str = "circle_xz"
    eligibility_policy_key: str = "reaction_target.electro_charged_propagation"
    sort_policy_key: str = "primary_then_subject_ref"

    def __post_init__(self) -> None:
        for value, name in (
            (self.selection_ref, "selection_ref"),
            (self.geometry, "geometry"),
            (self.eligibility_policy_key, "eligibility_policy_key"),
            (self.sort_policy_key, "sort_policy_key"),
        ):
            _text(value, name)
        if self.geometry != "circle_xz" or self.radius != 13.0:
            raise ValueError("普通感电传播只支持 X/Z 平面 13.0 米 Circle")


@dataclass(frozen=True, slots=True)
class SwirlEmissionSelection:
    """普通扩散派生元素 Impact 的固定 6 米目标选择声明。"""

    selection_ref: str
    anchor_subject_ref: ElementalSubjectRef
    radius: float = 6.0
    geometry: str = "circle_xz"
    exclude_anchor: bool = True
    eligibility_policy_key: str = "reaction_target.swirl_emission"
    sort_policy_key: str = "subject_ref"

    def __post_init__(self) -> None:
        for value, name in (
            (self.selection_ref, "selection_ref"),
            (self.geometry, "geometry"),
            (self.eligibility_policy_key, "eligibility_policy_key"),
            (self.sort_policy_key, "sort_policy_key"),
        ):
            _text(value, name)
        if self.geometry != "circle_xz" or self.radius != 6.0:
            raise ValueError("普通扩散传播只支持 X/Z 平面 6.0 米 Circle")
        if not self.exclude_anchor:
            raise ValueError("普通扩散传播必须排除中心主体")


type ReactionTargetSelection = (
    AreaAroundSubjectSelection
    | AreaAroundPositionSelection
    | CurrentSubjectSelection
    | ElectroChargedPropagationSelection
    | SwirlEmissionSelection
)


@dataclass(frozen=True, slots=True)
class GeneratedDamageImpactEffect:
    effect_ref: str
    effect_group_ref: str
    effect_order: int
    parent_occurrence_ref: str | None
    main_attack_tag: str
    damage_profile_key: str
    damage_element: DamageElement
    gate_definition_key: str
    damage_kind_key: str
    captured_scaling_basis: CapturedTransformativeScalingBasis | DynamicTransformativeScalingBasis
    transformative_base_multiplier: float
    character_transformative_base_multiplier: float | None = None
    elemental_amount: AuraAmount = AuraAmount.zero()
    can_crit: bool = False
    strike_type: StrikeType | None = None
    audit_tags: tuple[str, ...] = ()
    cause: ReactionEffectCause | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.effect_ref, "effect_ref"),
            (self.effect_group_ref, "effect_group_ref"),
            (self.main_attack_tag, "main_attack_tag"),
            (self.damage_profile_key, "damage_profile_key"),
            (self.gate_definition_key, "gate_definition_key"),
            (self.damage_kind_key, "damage_kind_key"),
        ):
            _text(value, name)
        if (
            isinstance(self.effect_order, bool)
            or not isinstance(self.effect_order, int)
            or self.effect_order < 0
        ):
            raise ValueError("effect_order 必须是非负整数")
        if not self.elemental_amount.is_zero or self.can_crit:
            raise ValueError("剧变派生 Damage Impact 必须为零元素量且不可暴击")
        if not isinstance(
            self.captured_scaling_basis,
            CapturedTransformativeScalingBasis | DynamicTransformativeScalingBasis,
        ):
            raise ValueError("captured_scaling_basis 必须是已捕获或动态剧变缩放基础")
        if not isinstance(self.damage_element, DamageElement):
            raise ValueError("剧变派生 Damage Impact 必须使用 DamageElement")
        if self.strike_type is not None and not isinstance(self.strike_type, StrikeType):
            raise ValueError("剧变派生 Damage Impact 的 strike_type 必须是 StrikeType 或 None")
        base_multiplier = _finite_non_negative(
            self.transformative_base_multiplier,
            "transformative_base_multiplier",
        )
        if base_multiplier <= 0:
            raise ValueError("transformative_base_multiplier 必须为正数")
        object.__setattr__(self, "transformative_base_multiplier", base_multiplier)
        if self.character_transformative_base_multiplier is not None:
            character_base_multiplier = _finite_non_negative(
                self.character_transformative_base_multiplier,
                "character_transformative_base_multiplier",
            )
            if character_base_multiplier <= 0:
                raise ValueError("character_transformative_base_multiplier 必须为正数")
            object.__setattr__(
                self,
                "character_transformative_base_multiplier",
                character_base_multiplier,
            )
        cause = self.cause or (
            OccurrenceCause(self.parent_occurrence_ref)
            if self.parent_occurrence_ref is not None
            else None
        )
        if not isinstance(cause, OccurrenceCause | ScheduledStateTickCause):
            raise ValueError("剧变派生 Damage Impact 必须具有 ReactionEffectCause")
        occurrence_ref = cause.occurrence_ref if isinstance(cause, OccurrenceCause) else None
        if self.parent_occurrence_ref is not None and self.parent_occurrence_ref != occurrence_ref:
            raise ValueError("Damage Impact 的 occurrence 投影必须与 cause 一致")
        object.__setattr__(self, "parent_occurrence_ref", occurrence_ref)
        object.__setattr__(self, "cause", cause)
        object.__setattr__(self, "audit_tags", tuple(self.audit_tags))


@dataclass(frozen=True, slots=True)
class LunarReactionDamageImpactEffect:
    """月曜反应声明的复合伤害 Effect，不泄漏 Damage 侧输入模型。"""

    effect_ref: str
    effect_group_ref: str
    effect_order: int
    parent_occurrence_ref: str | None
    main_attack_tag: str
    damage_profile_key: str
    damage_element: DamageElement
    damage_kind_key: str
    trigger_source_ref: ElementalSourceRef
    participant_refs: tuple[ElementalSourceRef, ...]
    reaction_profile_key: str
    reaction_multiplier: float = 1.0
    base_damage_bonus: float = 0.0
    reaction_bonus: float = 0.0
    can_crit: bool = True
    gate_definition_key: str | None = None
    audit_tags: tuple[str, ...] = ()
    cause: ReactionEffectCause | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.effect_ref, "effect_ref"),
            (self.effect_group_ref, "effect_group_ref"),
            (self.main_attack_tag, "main_attack_tag"),
            (self.damage_profile_key, "damage_profile_key"),
            (self.damage_kind_key, "damage_kind_key"),
            (self.reaction_profile_key, "reaction_profile_key"),
        ):
            _text(value, name)
        if (
            isinstance(self.effect_order, bool)
            or not isinstance(self.effect_order, int)
            or self.effect_order < 0
        ):
            raise ValueError("effect_order 必须是非负整数")
        if not isinstance(self.damage_element, DamageElement):
            raise ValueError("月曜 Damage Impact 必须使用 DamageElement")
        if not isinstance(self.trigger_source_ref, ElementalSourceRef):
            raise ValueError("月曜 Damage Impact 的 trigger_source_ref 必须是 ElementalSourceRef")

        raw_participants = tuple(self.participant_refs)
        if not raw_participants or any(
            not isinstance(item, ElementalSourceRef) for item in raw_participants
        ):
            raise ValueError("月曜 Damage Impact 必须具有非空角色参与者序列")
        if any(not item.source_key.startswith("character:") for item in raw_participants):
            raise ValueError("月曜 Damage Impact 的参与者必须来自角色 source_key")
        participant_source_keys = {item.source_key for item in raw_participants}
        if len(participant_source_keys) != len(raw_participants):
            raise ValueError("月曜 Damage Impact 的参与者不能重复角色")
        canonical_participants = tuple(
            sorted(ElementalSourceRef(item.source_key) for item in raw_participants)
        )

        reaction_multiplier = _finite_non_negative(
            self.reaction_multiplier,
            "reaction_multiplier",
        )
        if reaction_multiplier <= 0:
            raise ValueError("reaction_multiplier 必须为正数")
        base_damage_bonus = _finite(self.base_damage_bonus, "base_damage_bonus")
        if 1 + base_damage_bonus <= 0:
            raise ValueError("base_damage_bonus 不能使基础倍率为非正数")
        reaction_bonus = _finite(self.reaction_bonus, "reaction_bonus")
        if not isinstance(self.can_crit, bool):
            raise ValueError("月曜 Damage Impact 的 can_crit 必须是布尔值")
        if self.gate_definition_key is not None:
            _text(self.gate_definition_key, "gate_definition_key")

        cause = self.cause or (
            OccurrenceCause(self.parent_occurrence_ref)
            if self.parent_occurrence_ref is not None
            else None
        )
        if not isinstance(cause, OccurrenceCause | ScheduledStateTickCause):
            raise ValueError("月曜 Damage Impact 必须具有 ReactionEffectCause")
        occurrence_ref = cause.occurrence_ref if isinstance(cause, OccurrenceCause) else None
        if self.parent_occurrence_ref is not None and self.parent_occurrence_ref != occurrence_ref:
            raise ValueError("月曜 Damage Impact 的 occurrence 投影必须与 cause 一致")
        object.__setattr__(self, "participant_refs", canonical_participants)
        object.__setattr__(self, "reaction_multiplier", reaction_multiplier)
        object.__setattr__(self, "base_damage_bonus", base_damage_bonus)
        object.__setattr__(self, "reaction_bonus", reaction_bonus)
        object.__setattr__(self, "parent_occurrence_ref", occurrence_ref)
        object.__setattr__(self, "cause", cause)
        object.__setattr__(self, "audit_tags", tuple(self.audit_tags))


@dataclass(frozen=True, slots=True)
class LunarStormCloudAttackEffect:
    """雷暴云周期攻击声明；参与者在攻击结算时按目标 Aura 冻结。"""

    effect_ref: str
    effect_group_ref: str
    effect_order: int
    main_attack_tag: str
    damage_profile_key: str
    damage_element: DamageElement
    damage_kind_key: str
    trigger_source_ref: ElementalSourceRef
    reaction_profile_key: str
    reaction_multiplier: float
    gate_definition_key: str
    base_damage_bonus: float = 0.0
    reaction_bonus: float = 0.0
    can_crit: bool = True
    audit_tags: tuple[str, ...] = ()
    cause: ReactionEffectCause | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.effect_ref, "effect_ref"),
            (self.effect_group_ref, "effect_group_ref"),
            (self.main_attack_tag, "main_attack_tag"),
            (self.damage_profile_key, "damage_profile_key"),
            (self.damage_kind_key, "damage_kind_key"),
            (self.reaction_profile_key, "reaction_profile_key"),
            (self.gate_definition_key, "gate_definition_key"),
        ):
            _text(value, name)
        if (
            isinstance(self.effect_order, bool)
            or not isinstance(self.effect_order, int)
            or self.effect_order < 0
        ):
            raise ValueError("effect_order 必须是非负整数")
        if not isinstance(self.damage_element, DamageElement):
            raise ValueError("雷暴云攻击必须使用 DamageElement")
        if not isinstance(self.trigger_source_ref, ElementalSourceRef):
            raise ValueError("雷暴云攻击 trigger_source_ref 必须是 ElementalSourceRef")
        reaction_multiplier = _finite_non_negative(
            self.reaction_multiplier,
            "reaction_multiplier",
        )
        if reaction_multiplier <= 0:
            raise ValueError("reaction_multiplier 必须为正数")
        base_damage_bonus = _finite(self.base_damage_bonus, "base_damage_bonus")
        if 1 + base_damage_bonus <= 0:
            raise ValueError("base_damage_bonus 不能使基础倍率为非正数")
        reaction_bonus = _finite(self.reaction_bonus, "reaction_bonus")
        if not isinstance(self.can_crit, bool):
            raise ValueError("雷暴云攻击 can_crit 必须是布尔值")
        if self.cause is None or not isinstance(
            self.cause,
            OccurrenceCause | ScheduledStateTickCause,
        ):
            raise ValueError("雷暴云攻击必须具有 ReactionEffectCause")
        object.__setattr__(self, "reaction_multiplier", reaction_multiplier)
        object.__setattr__(self, "base_damage_bonus", base_damage_bonus)
        object.__setattr__(self, "reaction_bonus", reaction_bonus)
        object.__setattr__(self, "audit_tags", tuple(self.audit_tags))


@dataclass(frozen=True, slots=True)
class ReactionGeneratedImpactProvenance:
    """派生元素 Impact 保留其产生 occurrence 的稳定因果身份。"""

    provenance_ref: str
    parent_occurrence_ref: str | None
    reaction_profile_key: str
    cause: ReactionEffectCause | None = None

    def __post_init__(self) -> None:
        _text(self.provenance_ref, "provenance_ref")
        _text(self.reaction_profile_key, "reaction_profile_key")
        cause = self.cause or (
            OccurrenceCause(self.parent_occurrence_ref)
            if self.parent_occurrence_ref is not None
            else None
        )
        if not isinstance(cause, OccurrenceCause | ScheduledStateTickCause):
            raise ValueError("派生元素 Impact provenance 必须具有 ReactionEffectCause")
        occurrence_ref = cause.occurrence_ref if isinstance(cause, OccurrenceCause) else None
        if self.parent_occurrence_ref is not None and self.parent_occurrence_ref != occurrence_ref:
            raise ValueError("派生元素 Impact provenance 的 occurrence 投影必须与 cause 一致")
        object.__setattr__(self, "parent_occurrence_ref", occurrence_ref)
        object.__setattr__(self, "cause", cause)


@dataclass(frozen=True, slots=True)
class ReactionGeneratedImpactDamageComponent:
    """派生元素 Impact 可选的、与元素施加解耦的伤害组件。"""

    main_attack_tag: str
    damage_profile_key: str
    damage_element: DamageElement
    gate_definition_key: str
    damage_kind_key: str

    def __post_init__(self) -> None:
        for value, name in (
            (self.main_attack_tag, "main_attack_tag"),
            (self.damage_profile_key, "damage_profile_key"),
            (self.gate_definition_key, "gate_definition_key"),
            (self.damage_kind_key, "damage_kind_key"),
        ):
            _text(value, name)
        if not isinstance(self.damage_element, DamageElement):
            raise ValueError("派生元素 Impact 的 damage_element 必须是 DamageElement")


@dataclass(frozen=True, slots=True)
class ReactionGeneratedImpact:
    """Reaction 声明的正元素量派生 Impact，不泄漏 Aura 或 Damage Runtime。"""

    generated_impact_ref: str
    emission_order: int
    element: Element
    elemental_amount: AuraAmount
    aura_application_profile_key: str
    provenance: ReactionGeneratedImpactProvenance
    damage_component: ReactionGeneratedImpactDamageComponent | None = None

    def __post_init__(self) -> None:
        _text(self.generated_impact_ref, "generated_impact_ref")
        _text(self.aura_application_profile_key, "aura_application_profile_key")
        if (
            isinstance(self.emission_order, bool)
            or not isinstance(self.emission_order, int)
            or self.emission_order < 0
        ):
            raise ValueError("emission_order 必须是非负整数")
        if not isinstance(self.element, Element):
            raise ValueError("派生元素 Impact 的 element 必须是 Element")
        if not isinstance(self.elemental_amount, AuraAmount) or self.elemental_amount.is_zero:
            raise ValueError("派生元素 Impact 的 elemental_amount 必须为正的 AuraAmount")
        if not isinstance(self.provenance, ReactionGeneratedImpactProvenance):
            raise ValueError("provenance 必须是 ReactionGeneratedImpactProvenance")
        if self.damage_component is not None and not isinstance(
            self.damage_component,
            ReactionGeneratedImpactDamageComponent,
        ):
            raise ValueError("damage_component 必须是强类型派生伤害组件或 None")


@dataclass(frozen=True, slots=True)
class ReactionGeneratedImpactBatch:
    """一个 emission 对全部冻结目标原子准备的派生元素 Impact 声明。"""

    emission_batch_ref: str
    parent_root_work_ref: str
    parent_occurrence_refs: tuple[str, ...]
    settlement_round: int
    target_selection: SwirlEmissionSelection | CurrentSubjectSelection
    source_ref: ElementalSourceRef
    captured_source_observation: (
        TransformativeSourceObservation | CapturedTransformativeScalingBasis
    )
    impacts: tuple[ReactionGeneratedImpact, ...]
    causes: tuple[ReactionEffectCause, ...] = ()

    def __post_init__(self) -> None:
        for value, name in (
            (self.emission_batch_ref, "emission_batch_ref"),
            (self.parent_root_work_ref, "parent_root_work_ref"),
        ):
            _text(value, name)
        if (
            isinstance(self.settlement_round, bool)
            or not isinstance(self.settlement_round, int)
            or self.settlement_round <= 0
        ):
            raise ValueError("派生元素 Impact batch 的 settlement_round 必须是正整数")
        if not isinstance(self.target_selection, SwirlEmissionSelection | CurrentSubjectSelection):
            raise ValueError("派生元素 Impact batch 的 target_selection 不受支持")
        if not isinstance(
            self.captured_source_observation,
            TransformativeSourceObservation | CapturedTransformativeScalingBasis,
        ):
            raise ValueError(
                "captured_source_observation 必须是 TransformativeSourceObservation "
                "或 CapturedTransformativeScalingBasis"
            )
        if self.captured_source_observation.source_ref != self.source_ref:
            raise ValueError("派生元素 Impact batch 的来源观察必须匹配 source_ref")
        occurrence_refs = tuple(self.parent_occurrence_refs)
        if any(not isinstance(item, str) or not item.strip() for item in occurrence_refs):
            raise ValueError("parent_occurrence_refs 必须是字符串序列")
        if len(set(occurrence_refs)) != len(occurrence_refs):
            raise ValueError("parent_occurrence_refs 不能重复")
        impacts = tuple(self.impacts)
        if not impacts or any(not isinstance(item, ReactionGeneratedImpact) for item in impacts):
            raise ValueError("impacts 必须是非空 ReactionGeneratedImpact 序列")
        ordered_impacts = tuple(sorted(impacts, key=lambda item: item.emission_order))
        if tuple(item.emission_order for item in ordered_impacts) != tuple(range(len(impacts))):
            raise ValueError("派生元素 Impact 的 emission_order 必须从 0 连续编号")
        if len({item.generated_impact_ref for item in impacts}) != len(impacts):
            raise ValueError("派生元素 Impact 的 generated_impact_ref 不能重复")
        causes = tuple(self.causes) or tuple(OccurrenceCause(item) for item in occurrence_refs)
        if not causes or any(
            not isinstance(item, OccurrenceCause | ScheduledStateTickCause) for item in causes
        ):
            raise ValueError("派生元素 Impact batch 必须具有非空 ReactionEffectCause 序列")
        if len(set(causes)) != len(causes):
            raise ValueError("派生元素 Impact batch 的 cause 不能重复")
        cause_occurrence_refs = tuple(
            item.occurrence_ref for item in causes if isinstance(item, OccurrenceCause)
        )
        if occurrence_refs and occurrence_refs != cause_occurrence_refs:
            raise ValueError("parent_occurrence_refs 必须是 cause 的 occurrence 投影")
        if any(item.provenance.cause not in causes for item in impacts):
            if all(isinstance(cause, OccurrenceCause) for cause in causes):
                raise ValueError("派生元素 Impact 的 provenance 必须引用父 occurrence")
            raise ValueError("派生元素 Impact 的 provenance 必须引用 batch cause")
        object.__setattr__(self, "parent_occurrence_refs", cause_occurrence_refs)
        object.__setattr__(self, "causes", causes)
        object.__setattr__(self, "impacts", ordered_impacts)


@dataclass(frozen=True, slots=True)
class ReactionStatusEffect:
    effect_ref: str
    effect_group_ref: str
    effect_order: int
    parent_occurrence_ref: str | None
    status_profile_key: str
    duration_frames: int
    value: float
    audit_tags: tuple[str, ...] = ()
    cause: ReactionEffectCause | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.effect_ref, "effect_ref"),
            (self.effect_group_ref, "effect_group_ref"),
            (self.status_profile_key, "status_profile_key"),
        ):
            _text(value, name)
        if (
            isinstance(self.effect_order, bool)
            or not isinstance(self.effect_order, int)
            or self.effect_order < 0
        ):
            raise ValueError("effect_order 必须是非负整数")
        if (
            isinstance(self.duration_frames, bool)
            or not isinstance(self.duration_frames, int)
            or self.duration_frames <= 0
        ):
            raise ValueError("duration_frames 必须是正整数")
        if isinstance(self.value, bool) or not isinstance(self.value, int | float):
            raise ValueError("status value 必须是数字")
        value = float(self.value)
        if not math.isfinite(value):
            raise ValueError("status value 必须是有限数字")
        cause = self.cause or (
            OccurrenceCause(self.parent_occurrence_ref)
            if self.parent_occurrence_ref is not None
            else None
        )
        if not isinstance(cause, OccurrenceCause | ScheduledStateTickCause):
            raise ValueError("Reaction Status Effect 必须具有 ReactionEffectCause")
        occurrence_ref = cause.occurrence_ref if isinstance(cause, OccurrenceCause) else None
        if self.parent_occurrence_ref is not None and self.parent_occurrence_ref != occurrence_ref:
            raise ValueError("Reaction Status Effect 的 occurrence 投影必须与 cause 一致")
        object.__setattr__(self, "parent_occurrence_ref", occurrence_ref)
        object.__setattr__(self, "cause", cause)
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "audit_tags", tuple(self.audit_tags))


type ReactionEffect = (
    GeneratedDamageImpactEffect
    | LunarReactionDamageImpactEffect
    | LunarStormCloudAttackEffect
    | ReactionStatusEffect
)


@dataclass(frozen=True, slots=True)
class PersistentIncomingAuraApplicationEffect:
    """反应成立后让本次后手以普通损耗形成持久 Aura 的强类型语义。"""

    effect_ref: str
    loss_policy: AuraLossPolicy = AuraLossPolicy.STANDARD_20_PERCENT

    def __post_init__(self) -> None:
        _text(self.effect_ref, "effect_ref")
        if not isinstance(self.loss_policy, AuraLossPolicy):
            raise ValueError("loss_policy 必须是 AuraLossPolicy")


@dataclass(frozen=True, slots=True)
class ElectroChargedStateApplicationEffect:
    """普通感电成立或再附着时要创建/刷新来源快照的强类型状态语义。"""

    effect_ref: str
    captured_scaling_basis: CapturedTransformativeScalingBasis

    def __post_init__(self) -> None:
        _text(self.effect_ref, "effect_ref")
        if not isinstance(self.captured_scaling_basis, CapturedTransformativeScalingBasis):
            raise ValueError("captured_scaling_basis 必须是 CapturedTransformativeScalingBasis")


@dataclass(frozen=True, slots=True)
class DendroCoreStateCreationIntent:
    """普通绽放为 ReactionState 和 Space 共同声明的草原核创建意图。"""

    intent_ref: str
    parent_occurrence_ref: str
    instance_ref: ReactionStateInstanceRef
    subject_ref: ElementalSubjectRef
    space_entity_ref: str
    core_creator_ref: ElementalSourceRef
    dynamic_scaling_basis: DynamicTransformativeScalingBasis
    pool_scope: str
    created_frame: int
    expires_at_frame: int
    creation_sequence: int

    def __post_init__(self) -> None:
        for value, name in (
            (self.intent_ref, "intent_ref"),
            (self.parent_occurrence_ref, "parent_occurrence_ref"),
            (self.space_entity_ref, "space_entity_ref"),
            (self.pool_scope, "pool_scope"),
        ):
            _text(value, name)
        if not isinstance(self.instance_ref, ReactionStateInstanceRef):
            raise ValueError("instance_ref 必须是 ReactionStateInstanceRef")
        expected_instance_ref = f"reaction-state:dendro-core:{self.parent_occurrence_ref}"
        if self.instance_ref.value != expected_instance_ref:
            raise ValueError("草原核 instance_ref 必须由 occurrence_ref 确定性派生")
        expected_space_entity_ref = f"reaction_object:dendro_core:{self.parent_occurrence_ref}"
        if self.space_entity_ref != expected_space_entity_ref:
            raise ValueError("草原核 space_entity_ref 必须由 occurrence_ref 确定性派生")
        if not isinstance(self.core_creator_ref, ElementalSourceRef):
            raise ValueError("core_creator_ref 必须是 ElementalSourceRef")
        if not isinstance(self.dynamic_scaling_basis, DynamicTransformativeScalingBasis):
            raise ValueError("dynamic_scaling_basis 必须是 DynamicTransformativeScalingBasis")
        if self.dynamic_scaling_basis.source_ref != self.core_creator_ref:
            raise ValueError("草原核动态缩放来源必须与创建者一致")
        for value, name in (
            (self.created_frame, "created_frame"),
            (self.expires_at_frame, "expires_at_frame"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} 必须是非负整数")
        if self.expires_at_frame != self.created_frame + 360:
            raise ValueError("草原核生命周期必须固定为 360 帧")
        if (
            isinstance(self.creation_sequence, bool)
            or not isinstance(self.creation_sequence, int)
            or self.creation_sequence < 0
        ):
            raise ValueError("creation_sequence 必须是非负整数")


@dataclass(frozen=True, slots=True)
class CrystallizeShardStateCreationIntent:
    """普通结晶为 ReactionState 预先声明的单晶片创建意图。"""

    intent_ref: str
    parent_occurrence_ref: str
    instance_ref: ReactionStateInstanceRef
    subject_ref: ElementalSubjectRef
    space_entity_ref: str
    element: Element
    trigger_source: ElementalSourceRef
    captured_shield_basis: CapturedCrystallizeShieldBasis
    created_frame: int
    expires_at_frame: int

    def __post_init__(self) -> None:
        for value, name in (
            (self.intent_ref, "intent_ref"),
            (self.parent_occurrence_ref, "parent_occurrence_ref"),
            (self.space_entity_ref, "space_entity_ref"),
        ):
            _text(value, name)
        if not isinstance(self.instance_ref, ReactionStateInstanceRef):
            raise ValueError("instance_ref 必须是 ReactionStateInstanceRef")
        expected_instance_ref = f"reaction-state:crystallize-shard:{self.parent_occurrence_ref}"
        if self.instance_ref.value != expected_instance_ref:
            raise ValueError("结晶晶片 instance_ref 必须由 occurrence_ref 确定性派生")
        expected_space_entity_ref = (
            f"reaction_object:crystallize_shard:{self.parent_occurrence_ref}"
        )
        if self.space_entity_ref != expected_space_entity_ref:
            raise ValueError("结晶晶片 space_entity_ref 必须由 occurrence_ref 确定性派生")
        if self.element not in {Element.PYRO, Element.HYDRO, Element.ELECTRO, Element.CRYO}:
            raise ValueError("晶片元素必须是火、水、雷或冰")
        if not isinstance(self.captured_shield_basis, CapturedCrystallizeShieldBasis):
            raise ValueError("captured_shield_basis 必须是 CapturedCrystallizeShieldBasis")
        for field_name in ("created_frame", "expires_at_frame"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} 必须是非负整数")
        if self.expires_at_frame <= self.created_frame:
            raise ValueError("expires_at_frame 必须晚于 created_frame")
        if self.captured_shield_basis.captured_frame != self.created_frame:
            raise ValueError("结晶捕获帧必须与晶片创建帧一致")


@dataclass(frozen=True, slots=True)
class SpatialEntityCreationEffect:
    """Reaction 声明的 CURRENT_TRANSACTION 空间实体创建需求。"""

    effect_ref: str
    parent_occurrence_ref: str
    space_entity_ref: str
    owner_key: str
    source_key: str
    tags: tuple[str, ...]
    created_frame: int
    expires_at_frame: int

    def __post_init__(self) -> None:
        for value, name in (
            (self.effect_ref, "effect_ref"),
            (self.parent_occurrence_ref, "parent_occurrence_ref"),
            (self.space_entity_ref, "space_entity_ref"),
            (self.owner_key, "owner_key"),
            (self.source_key, "source_key"),
        ):
            _text(value, name)
        tags = tuple(self.tags)
        if not tags or any(not isinstance(tag, str) or not tag.strip() for tag in tags):
            raise ValueError("tags 必须是非空字符串序列")
        if len(set(tags)) != len(tags):
            raise ValueError("tags 不能重复")
        for field_name in ("created_frame", "expires_at_frame"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} 必须是非负整数")
        if self.expires_at_frame <= self.created_frame:
            raise ValueError("expires_at_frame 必须晚于 created_frame")
        object.__setattr__(self, "tags", tags)


@dataclass(frozen=True, slots=True)
class ReactionStateTransitionEffect:
    """Reaction 决策步骤对强类型 State 的完整替换或移除审计。"""

    transition_ref: str
    state_slot_key: str
    operation: str
    before_instance_ref: str | None = None
    after_instance_ref: str | None = None

    def __post_init__(self) -> None:
        _text(self.transition_ref, "transition_ref")
        _text(self.state_slot_key, "state_slot_key")
        if self.operation not in {"create", "replace", "remove"}:
            raise ValueError("ReactionStateTransitionEffect operation 不受支持")
        if self.operation == "create" and self.after_instance_ref is None:
            raise ValueError("ReactionState create 必须提供 after_instance_ref")
        if self.operation == "replace" and (
            self.before_instance_ref is None or self.after_instance_ref is None
        ):
            raise ValueError("ReactionState replace 必须提供完整实例前后值")
        if self.operation == "remove" and self.before_instance_ref is None:
            raise ValueError("ReactionState remove 必须提供 before_instance_ref")


class BurningStateTerminationReason(StrEnum):
    DENDRO_DEPLETED = "dendro_depleted"
    BURNING_DEPLETED = "burning_depleted"
    SUBJECT_UNAVAILABLE = "subject_unavailable"


@dataclass(frozen=True, slots=True)
class ReactionSubjectUnavailableNotice:
    """由上游生命周期能力提交的主体失效通知。"""

    notice_ref: str
    subject_ref: ElementalSubjectRef
    frame: int

    def __post_init__(self) -> None:
        _text(self.notice_ref, "notice_ref")
        if not isinstance(self.subject_ref, ElementalSubjectRef):
            raise ValueError("subject_ref 必须是 ElementalSubjectRef")
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise ValueError("frame 必须是非负整数")


@dataclass(frozen=True, slots=True)
class ReactionSourceUnavailableNotice:
    """由上游生命周期能力提交的来源失效通知。"""

    notice_ref: str
    source_ref: ElementalSourceRef
    frame: int

    def __post_init__(self) -> None:
        _text(self.notice_ref, "notice_ref")
        if not isinstance(self.source_ref, ElementalSourceRef):
            raise ValueError("source_ref 必须是 ElementalSourceRef")
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise ValueError("frame 必须是非负整数")


type ReactionLifecycleNotice = ReactionSubjectUnavailableNotice | ReactionSourceUnavailableNotice


@dataclass(frozen=True, slots=True)
class BurningStateEstablishmentIntent:
    intent_ref: str
    subject_ref: ElementalSubjectRef
    occurrence_ref: str
    frame: int
    burning_aura_link_ref: ElementalStateLinkRef
    dendro_like_link_refs: tuple[ElementalStateLinkRef, ...]
    effect_owner_ref: ElementalSourceRef
    captured_scaling_basis: CapturedTransformativeScalingBasis

    def __post_init__(self) -> None:
        _text(self.intent_ref, "intent_ref")
        _text(self.occurrence_ref, "occurrence_ref")
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise ValueError("frame 必须是非负整数")
        if not isinstance(self.burning_aura_link_ref, ElementalStateLinkRef):
            raise ValueError("burning_aura_link_ref 必须是 ElementalStateLinkRef")
        links = tuple(self.dendro_like_link_refs)
        if not links or any(not isinstance(item, ElementalStateLinkRef) for item in links):
            raise ValueError("dendro_like_link_refs 必须包含 ElementalStateLinkRef")
        if self.burning_aura_link_ref not in links:
            raise ValueError("类草 Link 必须包含 Burning Link")
        if not isinstance(self.effect_owner_ref, ElementalSourceRef):
            raise ValueError("effect_owner_ref 必须是 ElementalSourceRef")
        if not isinstance(self.captured_scaling_basis, CapturedTransformativeScalingBasis):
            raise ValueError("captured_scaling_basis 必须是 CapturedTransformativeScalingBasis")
        if self.captured_scaling_basis.source_ref != self.effect_owner_ref:
            raise ValueError("燃烧来源与捕获缩放来源必须一致")
        object.__setattr__(self, "dendro_like_link_refs", links)


@dataclass(frozen=True, slots=True)
class BurningStateMaintenanceIntent:
    intent_ref: str
    subject_ref: ElementalSubjectRef
    frame: int
    expected_state_instance_ref: ReactionStateInstanceRef
    expected_state_revision: int
    application_ref: str
    effect_owner_ref: ElementalSourceRef
    captured_scaling_basis: CapturedTransformativeScalingBasis

    def __post_init__(self) -> None:
        for value, name in (
            (self.intent_ref, "intent_ref"),
            (self.application_ref, "application_ref"),
        ):
            _text(value, name)
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise ValueError("frame 必须是非负整数")
        if not isinstance(self.expected_state_instance_ref, ReactionStateInstanceRef):
            raise ValueError("expected_state_instance_ref 必须是 ReactionStateInstanceRef")
        if (
            isinstance(self.expected_state_revision, bool)
            or not isinstance(self.expected_state_revision, int)
            or self.expected_state_revision <= 0
        ):
            raise ValueError("expected_state_revision 必须是正整数")
        if not isinstance(self.effect_owner_ref, ElementalSourceRef):
            raise ValueError("effect_owner_ref 必须是 ElementalSourceRef")
        if not isinstance(self.captured_scaling_basis, CapturedTransformativeScalingBasis):
            raise ValueError("captured_scaling_basis 必须是 CapturedTransformativeScalingBasis")
        if self.captured_scaling_basis.source_ref != self.effect_owner_ref:
            raise ValueError("燃烧来源与捕获缩放来源必须一致")


@dataclass(frozen=True, slots=True)
class BurningStateTerminationIntent:
    intent_ref: str
    subject_ref: ElementalSubjectRef
    frame: int
    expected_state_instance_ref: ReactionStateInstanceRef
    expected_state_revision: int
    reason: BurningStateTerminationReason

    def __post_init__(self) -> None:
        _text(self.intent_ref, "intent_ref")
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise ValueError("frame 必须是非负整数")
        if not isinstance(self.expected_state_instance_ref, ReactionStateInstanceRef):
            raise ValueError("expected_state_instance_ref 必须是 ReactionStateInstanceRef")
        if (
            isinstance(self.expected_state_revision, bool)
            or not isinstance(self.expected_state_revision, int)
            or self.expected_state_revision <= 0
        ):
            raise ValueError("expected_state_revision 必须是正整数")
        if not isinstance(self.reason, BurningStateTerminationReason):
            raise ValueError("reason 必须是 BurningStateTerminationReason")


class QuickenStateTerminationReason(StrEnum):
    QUICKEN_DEPLETED = "quicken_depleted"
    SUBJECT_UNAVAILABLE = "subject_unavailable"


@dataclass(frozen=True, slots=True)
class QuickenStateEstablishmentIntent:
    intent_ref: str
    subject_ref: ElementalSubjectRef
    occurrence_ref: str
    frame: int
    quicken_aura_link_ref: ElementalStateLinkRef

    def __post_init__(self) -> None:
        _text(self.intent_ref, "intent_ref")
        _text(self.occurrence_ref, "occurrence_ref")
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise ValueError("frame 必须是非负整数")
        if not isinstance(self.quicken_aura_link_ref, ElementalStateLinkRef):
            raise ValueError("quicken_aura_link_ref 必须是 ElementalStateLinkRef")


@dataclass(frozen=True, slots=True)
class QuickenStateCoverageIntent:
    intent_ref: str
    subject_ref: ElementalSubjectRef
    occurrence_ref: str
    frame: int
    expected_state_instance_ref: ReactionStateInstanceRef
    expected_state_revision: int
    quicken_aura_link_ref: ElementalStateLinkRef

    def __post_init__(self) -> None:
        _text(self.intent_ref, "intent_ref")
        _text(self.occurrence_ref, "occurrence_ref")
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise ValueError("frame 必须是非负整数")
        if not isinstance(self.expected_state_instance_ref, ReactionStateInstanceRef):
            raise ValueError("expected_state_instance_ref 必须是 ReactionStateInstanceRef")
        if (
            isinstance(self.expected_state_revision, bool)
            or not isinstance(self.expected_state_revision, int)
            or self.expected_state_revision <= 0
        ):
            raise ValueError("expected_state_revision 必须是正整数")
        if not isinstance(self.quicken_aura_link_ref, ElementalStateLinkRef):
            raise ValueError("quicken_aura_link_ref 必须是 ElementalStateLinkRef")


@dataclass(frozen=True, slots=True)
class QuickenStateTerminationIntent:
    intent_ref: str
    subject_ref: ElementalSubjectRef
    frame: int
    expected_state_instance_ref: ReactionStateInstanceRef
    expected_state_revision: int
    reason: QuickenStateTerminationReason

    def __post_init__(self) -> None:
        _text(self.intent_ref, "intent_ref")
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise ValueError("frame 必须是非负整数")
        if not isinstance(self.expected_state_instance_ref, ReactionStateInstanceRef):
            raise ValueError("expected_state_instance_ref 必须是 ReactionStateInstanceRef")
        if (
            isinstance(self.expected_state_revision, bool)
            or not isinstance(self.expected_state_revision, int)
            or self.expected_state_revision <= 0
        ):
            raise ValueError("expected_state_revision 必须是正整数")
        if not isinstance(self.reason, QuickenStateTerminationReason):
            raise ValueError("reason 必须是 QuickenStateTerminationReason")


@dataclass(frozen=True, slots=True)
class LunarStormCloudStatePlanningIntent:
    """月感电 occurrence 对雷暴云创建/刷新的确定性候选意图。"""

    intent_ref: str
    parent_occurrence_ref: str
    instance_ref: ReactionStateInstanceRef
    subject_ref: ElementalSubjectRef
    space_entity_ref: str
    trigger_source_ref: ElementalSourceRef
    team_ref: str
    created_frame: int
    expires_at_frame: int
    first_attack_frame: int
    attack_interval_frames: int

    def __post_init__(self) -> None:
        for value, name in (
            (self.intent_ref, "intent_ref"),
            (self.parent_occurrence_ref, "parent_occurrence_ref"),
            (self.space_entity_ref, "space_entity_ref"),
            (self.team_ref, "team_ref"),
        ):
            _text(value, name)
        if not isinstance(self.instance_ref, ReactionStateInstanceRef):
            raise ValueError("instance_ref 必须是 ReactionStateInstanceRef")
        expected_instance_ref = f"reaction-state:lunar-storm-cloud:{self.parent_occurrence_ref}"
        if self.instance_ref.value != expected_instance_ref:
            raise ValueError("雷暴云 instance_ref 必须由 occurrence_ref 确定性派生")
        expected_space_entity_ref = (
            f"reaction_object:lunar_storm_cloud:{self.parent_occurrence_ref}"
        )
        if self.space_entity_ref != expected_space_entity_ref:
            raise ValueError("雷暴云 space_entity_ref 必须由 occurrence_ref 确定性派生")
        if not isinstance(self.subject_ref, ElementalSubjectRef):
            raise ValueError("subject_ref 必须是 ElementalSubjectRef")
        if not isinstance(self.trigger_source_ref, ElementalSourceRef):
            raise ValueError("trigger_source_ref 必须是 ElementalSourceRef")
        for field_name in ("created_frame", "expires_at_frame", "first_attack_frame"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} 必须是非负整数")
        if self.expires_at_frame != self.created_frame + 360:
            raise ValueError("雷暴云生命周期必须固定为 360 帧")
        if self.first_attack_frame != self.created_frame + 15:
            raise ValueError("雷暴云首次攻击必须固定为创建后 15 帧")
        if self.attack_interval_frames != 15:
            raise ValueError("雷暴云攻击间隔必须固定为 15 帧")


@dataclass(frozen=True, slots=True)
class LunarCrystallizeStatePlanningIntent:
    """月结晶 occurrence 对月笼集合与共享累计器的确定性候选意图。"""

    intent_ref: str
    parent_occurrence_ref: str
    subject_ref: ElementalSubjectRef
    team_ref: str
    trigger_source_ref: ElementalSourceRef
    participant_refs: tuple[ElementalSourceRef, ...]
    created_frame: int
    order: int
    cage_instance_refs: tuple[ReactionStateInstanceRef, ...]
    cage_space_entity_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for value, name in (
            (self.intent_ref, "intent_ref"),
            (self.parent_occurrence_ref, "parent_occurrence_ref"),
            (self.team_ref, "team_ref"),
        ):
            _text(value, name)
        if not isinstance(self.subject_ref, ElementalSubjectRef):
            raise ValueError("subject_ref 必须是 ElementalSubjectRef")
        if not isinstance(self.trigger_source_ref, ElementalSourceRef):
            raise ValueError("trigger_source_ref 必须是 ElementalSourceRef")
        if (
            isinstance(self.created_frame, bool)
            or not isinstance(self.created_frame, int)
            or self.created_frame < 0
        ):
            raise ValueError("created_frame 必须是非负整数")
        if isinstance(self.order, bool) or not isinstance(self.order, int) or self.order < 0:
            raise ValueError("order 必须是非负整数")
        participant_refs = tuple(self.participant_refs)
        if any(not isinstance(item, ElementalSourceRef) for item in participant_refs):
            raise ValueError("participant_refs 必须是 ElementalSourceRef 序列")
        if len(set(participant_refs)) != len(participant_refs):
            raise ValueError("participant_refs 不能重复")
        object.__setattr__(self, "participant_refs", tuple(sorted(participant_refs)))
        instance_refs = tuple(self.cage_instance_refs)
        space_entity_refs = tuple(self.cage_space_entity_refs)
        if len(instance_refs) != 3 or len(space_entity_refs) != 3:
            raise ValueError("月结晶意图必须声明恰好三枚月笼")
        for index, (instance_ref, space_entity_ref) in enumerate(
            zip(instance_refs, space_entity_refs, strict=True)
        ):
            if not isinstance(instance_ref, ReactionStateInstanceRef):
                raise ValueError("cage_instance_refs 必须是 ReactionStateInstanceRef 序列")
            expected_instance = f"reaction-state:lunar-cage:{self.parent_occurrence_ref}:{index}"
            expected_space = f"reaction_object:lunar_cage:{self.parent_occurrence_ref}:{index}"
            if instance_ref.value != expected_instance:
                raise ValueError("月笼 instance_ref 必须由 occurrence_ref 和序号确定性派生")
            if not isinstance(space_entity_ref, str) or space_entity_ref != expected_space:
                raise ValueError("月笼 space_entity_ref 必须由 occurrence_ref 和序号确定性派生")
        object.__setattr__(self, "cage_instance_refs", instance_refs)
        object.__setattr__(self, "cage_space_entity_refs", space_entity_refs)


type ReactionStatePlanningIntent = (
    BurningStateEstablishmentIntent
    | BurningStateMaintenanceIntent
    | BurningStateTerminationIntent
    | QuickenStateCoverageIntent
    | QuickenStateEstablishmentIntent
    | QuickenStateTerminationIntent
)


@dataclass(frozen=True, slots=True)
class OccurrenceCause:
    occurrence_ref: str

    def __post_init__(self) -> None:
        _text(self.occurrence_ref, "occurrence_ref")


type ReactionEffectCause = OccurrenceCause | ScheduledStateTickCause


@dataclass(frozen=True, slots=True)
class ReactionEffectGroup:
    effect_group_ref: str
    parent_occurrence_ref: str | None
    execution_scope: ReactionEffectExecutionScope
    emission_order: int
    target_selection: ReactionTargetSelection
    effects: tuple[ReactionEffect, ...]
    cause: ReactionEffectCause | None = None
    suppressed_effect_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.effect_group_ref, "effect_group_ref")
        if self.execution_scope is not ReactionEffectExecutionScope.NEXT_SETTLEMENT_ROUND:
            raise ValueError("当前只支持 next_settlement_round Effect group")
        if not isinstance(
            self.target_selection,
            AreaAroundPositionSelection
            | AreaAroundSubjectSelection
            | CurrentSubjectSelection
            | ElectroChargedPropagationSelection
            | SwirlEmissionSelection,
        ):
            raise ValueError("Reaction Effect group 的 target_selection 不受支持")
        if (
            isinstance(self.emission_order, bool)
            or not isinstance(self.emission_order, int)
            or self.emission_order < 0
        ):
            raise ValueError("emission_order 必须是非负整数")
        effects = tuple(sorted(self.effects, key=lambda item: item.effect_order))
        if not effects or tuple(item.effect_order for item in effects) != tuple(
            range(len(effects))
        ):
            raise ValueError("Effect group 的 effect_order 必须从 0 连续编号")
        if any(item.effect_group_ref != self.effect_group_ref for item in effects):
            raise ValueError("Effect 必须引用所属 effect_group_ref")
        cause = self.cause or (
            OccurrenceCause(self.parent_occurrence_ref)
            if self.parent_occurrence_ref is not None
            else None
        )
        if not isinstance(cause, OccurrenceCause | ScheduledStateTickCause):
            raise ValueError("Reaction Effect group 的 cause 不受支持")
        occurrence_ref = cause.occurrence_ref if isinstance(cause, OccurrenceCause) else None
        if self.parent_occurrence_ref is not None and occurrence_ref != self.parent_occurrence_ref:
            raise ValueError("OccurrenceCause 必须与 parent_occurrence_ref 一致")
        if any(effect.cause != cause for effect in effects):
            raise ValueError("Effect 必须与所属 Effect group 使用同一 cause")
        suppressed_effect_refs = tuple(self.suppressed_effect_refs)
        if any(not isinstance(ref, str) or not ref.strip() for ref in suppressed_effect_refs):
            raise ValueError("suppressed_effect_refs 必须是非空字符串序列")
        if set(suppressed_effect_refs) & {effect.effect_ref for effect in effects}:
            raise ValueError("已抑制 Effect 不能同时保留在 Effect group")
        object.__setattr__(self, "effects", effects)
        object.__setattr__(self, "parent_occurrence_ref", occurrence_ref)
        object.__setattr__(self, "cause", cause)
        object.__setattr__(self, "suppressed_effect_refs", suppressed_effect_refs)


@dataclass(frozen=True, slots=True)
class ReactionOccurrence:
    occurrence_ref: str
    interaction_id: str
    reaction_key: str
    direction_key: str
    profile_key: str
    source_ref: ElementalSourceRef
    subject_ref: ElementalSubjectRef
    transition: ElementalTransitionEffect
    participant_refs: tuple[ElementalSourceRef, ...] = ()
    effect_groups: tuple[ReactionEffectGroup, ...] = ()
    persistent_incoming_aura_application: PersistentIncomingAuraApplicationEffect | None = None
    electro_charged_state_application: ElectroChargedStateApplicationEffect | None = None
    crystallize_shard_state_creation: CrystallizeShardStateCreationIntent | None = None
    dendro_core_state_creation: DendroCoreStateCreationIntent | None = None
    lunar_storm_cloud_state_planning: LunarStormCloudStatePlanningIntent | None = None
    lunar_crystallize_planning: LunarCrystallizeStatePlanningIntent | None = None
    spatial_entity_creation: SpatialEntityCreationEffect | None = None
    parallel_aura_consumption: ParallelAuraConsumption | None = None
    parent_occurrence_ref: str | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.occurrence_ref, "occurrence_ref"),
            (self.interaction_id, "interaction_id"),
            (self.reaction_key, "reaction_key"),
            (self.direction_key, "direction_key"),
            (self.profile_key, "profile_key"),
        ):
            _text(value, name)
        if self.parent_occurrence_ref is not None:
            _text(self.parent_occurrence_ref, "parent_occurrence_ref")
            if self.parent_occurrence_ref == self.occurrence_ref:
                raise ValueError("occurrence 不能引用自身作为 parent_occurrence_ref")
        participant_refs = tuple(self.participant_refs)
        if any(not isinstance(item, ElementalSourceRef) for item in participant_refs):
            raise ValueError("participant_refs 必须是 ElementalSourceRef 序列")
        if len(set(participant_refs)) != len(participant_refs):
            raise ValueError("participant_refs 不能重复")
        object.__setattr__(self, "participant_refs", tuple(sorted(participant_refs)))
        groups = tuple(sorted(self.effect_groups, key=lambda item: item.emission_order))
        if groups and tuple(group.emission_order for group in groups) != tuple(range(len(groups))):
            raise ValueError("occurrence 的 emission_order 必须从 0 连续编号")
        if any(group.parent_occurrence_ref != self.occurrence_ref for group in groups):
            raise ValueError("Effect group 必须引用所属 occurrence_ref")
        if self.persistent_incoming_aura_application is not None and not isinstance(
            self.persistent_incoming_aura_application,
            PersistentIncomingAuraApplicationEffect,
        ):
            raise ValueError("persistent_incoming_aura_application 必须是强类型 Aura Effect")
        if self.electro_charged_state_application is not None and not isinstance(
            self.electro_charged_state_application,
            ElectroChargedStateApplicationEffect,
        ):
            raise ValueError("electro_charged_state_application 必须是强类型 State Effect")
        parallel = self.parallel_aura_consumption
        if parallel is not None:
            if not isinstance(parallel, ParallelAuraConsumption):
                raise ValueError("parallel_aura_consumption 必须是 ParallelAuraConsumption")
            summary = next(
                (item for item in parallel.branches if item.aura_kind is self.transition.aura_kind),
                None,
            )
            if summary is None:
                raise ValueError("parallel occurrence transition 必须投影一个分支 Aura")
            if (
                self.transition.incoming_before != parallel.shared_incoming_before
                or self.transition.incoming_consumed != parallel.shared_incoming_consumed
                or self.transition.incoming_remaining != parallel.shared_incoming_remaining
                or self.transition.aura_before != summary.aura_before
                or self.transition.aura_consumed != summary.aura_consumed
                or self.transition.aura_remaining != summary.aura_remaining
            ):
                raise ValueError("parallel occurrence transition 必须与共享账本和分支投影一致")
        shard_creation = self.crystallize_shard_state_creation
        core_creation = self.dendro_core_state_creation
        cloud_planning = self.lunar_storm_cloud_state_planning
        lunar_crystallize_planning = self.lunar_crystallize_planning
        spatial_creation = self.spatial_entity_creation
        if shard_creation is not None and core_creation is not None:
            raise ValueError("一个 occurrence 不能同时创建晶片和草原核")
        if cloud_planning is not None and (shard_creation is not None or core_creation is not None):
            raise ValueError("一个 occurrence 不能同时创建晶片、草原核和雷暴云")
        if lunar_crystallize_planning is not None and (
            shard_creation is not None or core_creation is not None or cloud_planning is not None
        ):
            raise ValueError("一个 occurrence 不能同时创建晶片、草原核、雷暴云和月结晶月笼")
        if lunar_crystallize_planning is not None and spatial_creation is not None:
            raise ValueError("月结晶月笼使用多实体空间创建，不使用单实体空间创建声明")
        state_creation_count = sum(
            item is not None for item in (shard_creation, core_creation, cloud_planning)
        )
        if (state_creation_count == 0) != (spatial_creation is None):
            raise ValueError("Reaction State 与空间创建声明必须同时存在或同时缺失")
        if shard_creation is not None:
            if not isinstance(shard_creation, CrystallizeShardStateCreationIntent):
                raise ValueError("crystallize_shard_state_creation 必须是强类型创建意图")
            if not isinstance(spatial_creation, SpatialEntityCreationEffect):
                raise ValueError("spatial_entity_creation 必须是强类型空间创建声明")
            assert spatial_creation is not None
            if shard_creation.parent_occurrence_ref != self.occurrence_ref:
                raise ValueError("晶片 State 创建意图必须引用所属 occurrence_ref")
            if spatial_creation.parent_occurrence_ref != self.occurrence_ref:
                raise ValueError("晶片空间创建声明必须引用所属 occurrence_ref")
            if shard_creation.space_entity_ref != spatial_creation.space_entity_ref:
                raise ValueError("晶片 State 与空间创建声明必须使用相同 entity ref")
            if shard_creation.instance_ref.value != spatial_creation.source_key:
                raise ValueError("晶片空间创建声明必须反向引用 State instance ref")
            if shard_creation.created_frame != spatial_creation.created_frame or (
                shard_creation.expires_at_frame != spatial_creation.expires_at_frame
            ):
                raise ValueError("晶片 State 与空间创建声明的生命周期必须一致")
        if core_creation is not None:
            if not isinstance(core_creation, DendroCoreStateCreationIntent):
                raise ValueError("dendro_core_state_creation 必须是强类型创建意图")
            if not isinstance(spatial_creation, SpatialEntityCreationEffect):
                raise ValueError("spatial_entity_creation 必须是强类型空间创建声明")
            assert spatial_creation is not None
            if core_creation.parent_occurrence_ref != self.occurrence_ref:
                raise ValueError("草原核 State 创建意图必须引用所属 occurrence_ref")
            if spatial_creation.parent_occurrence_ref != self.occurrence_ref:
                raise ValueError("草原核空间创建声明必须引用所属 occurrence_ref")
            if core_creation.space_entity_ref != spatial_creation.space_entity_ref:
                raise ValueError("草原核 State 与空间创建声明必须使用相同 entity ref")
            if core_creation.instance_ref.value != spatial_creation.source_key:
                raise ValueError("草原核空间创建声明必须反向引用 State instance ref")
            if (
                core_creation.created_frame != spatial_creation.created_frame
                or core_creation.expires_at_frame != spatial_creation.expires_at_frame
            ):
                raise ValueError("草原核 State 与空间创建声明的生命周期必须一致")
        if cloud_planning is not None:
            if not isinstance(cloud_planning, LunarStormCloudStatePlanningIntent):
                raise ValueError("lunar_storm_cloud_state_planning 必须是强类型规划意图")
            if not isinstance(spatial_creation, SpatialEntityCreationEffect):
                raise ValueError("spatial_entity_creation 必须是强类型空间创建声明")
            assert spatial_creation is not None
            if cloud_planning.parent_occurrence_ref != self.occurrence_ref:
                raise ValueError("雷暴云规划意图必须引用所属 occurrence_ref")
            if spatial_creation.parent_occurrence_ref != self.occurrence_ref:
                raise ValueError("雷暴云空间创建声明必须引用所属 occurrence_ref")
            if cloud_planning.space_entity_ref != spatial_creation.space_entity_ref:
                raise ValueError("雷暴云 State 与空间创建声明必须使用相同 entity ref")
            if cloud_planning.instance_ref.value != spatial_creation.source_key:
                raise ValueError("雷暴云空间创建声明必须反向引用 State instance ref")
            if (
                cloud_planning.created_frame != spatial_creation.created_frame
                or cloud_planning.expires_at_frame != spatial_creation.expires_at_frame
            ):
                raise ValueError("雷暴云 State 与空间创建声明的生命周期必须一致")
        if lunar_crystallize_planning is not None:
            if not isinstance(lunar_crystallize_planning, LunarCrystallizeStatePlanningIntent):
                raise ValueError("lunar_crystallize_planning 必须是强类型规划意图")
            if lunar_crystallize_planning.parent_occurrence_ref != self.occurrence_ref:
                raise ValueError("月结晶规划意图必须引用所属 occurrence_ref")
            if lunar_crystallize_planning.subject_ref != self.subject_ref:
                raise ValueError("月结晶规划意图主体必须与 occurrence 一致")
            if lunar_crystallize_planning.trigger_source_ref != self.source_ref:
                raise ValueError("月结晶规划意图触发来源必须与 occurrence 一致")
            if lunar_crystallize_planning.participant_refs != self.participant_refs:
                raise ValueError("月结晶规划意图参与者必须与 occurrence 一致")
        object.__setattr__(self, "effect_groups", groups)


@dataclass(frozen=True, slots=True)
class ReactionDecisionStep:
    step_ordinal: int
    selected_candidate_keys: tuple[str, ...]
    elemental_transition_effects: tuple[ElementalTransitionEffect, ...]
    state_transition_effects: tuple[ReactionStateTransitionEffect, ...]
    occurrences: tuple[ReactionOccurrence, ...]
    state_planning_intents: tuple[ReactionStatePlanningIntent, ...] = ()

    def __post_init__(self) -> None:
        if (
            isinstance(self.step_ordinal, bool)
            or not isinstance(self.step_ordinal, int)
            or self.step_ordinal < 0
        ):
            raise ValueError("step_ordinal 必须是非负整数")
        candidate_keys = tuple(self.selected_candidate_keys)
        if not candidate_keys or any(
            not isinstance(item, str) or not item.strip() for item in candidate_keys
        ):
            raise ValueError("决策步骤至少需要一个非空候选 key")
        if len(set(candidate_keys)) != len(candidate_keys):
            raise ValueError("决策步骤的候选 key 不能重复")
        transitions = tuple(self.elemental_transition_effects)
        if any(not isinstance(item, ElementalTransitionEffect) for item in transitions):
            raise ValueError("elemental_transition_effects 必须是 ElementalTransitionEffect 序列")
        state_transitions = tuple(self.state_transition_effects)
        if any(not isinstance(item, ReactionStateTransitionEffect) for item in state_transitions):
            raise ValueError("state_transition_effects 必须是强类型状态迁移序列")
        occurrences = tuple(self.occurrences)
        if any(not isinstance(item, ReactionOccurrence) for item in occurrences):
            raise ValueError("occurrences 必须是 ReactionOccurrence 序列")
        intents = tuple(self.state_planning_intents)
        if any(
            not isinstance(
                item,
                (
                    BurningStateEstablishmentIntent,
                    BurningStateMaintenanceIntent,
                    BurningStateTerminationIntent,
                    QuickenStateCoverageIntent,
                    QuickenStateEstablishmentIntent,
                    QuickenStateTerminationIntent,
                ),
            )
            for item in intents
        ):
            raise ValueError("state_planning_intents 必须是强类型状态规划意图序列")
        ordered_intents = tuple(sorted(intents, key=lambda item: item.intent_ref))
        if len({item.intent_ref for item in ordered_intents}) != len(ordered_intents):
            raise ValueError("state_planning_intents 的 intent_ref 不能重复")
        object.__setattr__(self, "selected_candidate_keys", candidate_keys)
        object.__setattr__(self, "elemental_transition_effects", transitions)
        object.__setattr__(self, "state_transition_effects", state_transitions)
        object.__setattr__(self, "occurrences", occurrences)
        object.__setattr__(self, "state_planning_intents", ordered_intents)


@dataclass(frozen=True, slots=True)
class ReactionDecisionSequence:
    steps: tuple[ReactionDecisionStep, ...] = ()

    def __post_init__(self) -> None:
        steps = tuple(self.steps)
        if tuple(step.step_ordinal for step in steps) != tuple(range(len(steps))):
            raise ValueError("ReactionDecisionSequence 的 step_ordinal 必须从 0 连续编号")
        object.__setattr__(self, "steps", steps)


@dataclass(frozen=True, slots=True)
class ReactionEvaluationRequest:
    interaction_id: str
    target_impact_ref: str
    frame: int
    order: int
    source_ref: ElementalSourceRef
    subject_ref: ElementalSubjectRef
    incoming_element: Element | None
    incoming_amount: AuraAmount
    observed_aura: AuraView
    current_damage_element: Element | None = None
    transformative_source_observation: (
        TransformativeSourceObservation | CapturedTransformativeScalingBasis | None
    ) = None
    trigger_context: ReactionTriggerContext | None = None
    observed_frozen_state: FrozenState | None = None
    observed_electro_charged_state: ElectroChargedState | None = None
    freeze_resistance_observation: FreezeResistanceObservation | None = None
    crystallize_source_observation: CrystallizeSourceObservation | None = None
    observed_burning_state: BurningState | None = None
    observed_quicken_state: QuickenState | None = None
    catalyze_impact_qualification: CatalyzeImpactQualification | None = None
    state_maintenance_allowed: bool = True
    character_source_refs: tuple[ElementalSourceRef, ...] = ()
    reaction_capability_keys: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        _text(self.interaction_id, "interaction_id")
        _text(self.target_impact_ref, "target_impact_ref")
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise ValueError("frame 必须是非负整数")
        if isinstance(self.order, bool) or not isinstance(self.order, int) or self.order < 0:
            raise ValueError("order 必须是非负整数")
        if not isinstance(self.incoming_amount, AuraAmount):
            raise ValueError("incoming_amount 必须是 AuraAmount")
        context = self.trigger_context
        if context is None:
            if not isinstance(self.incoming_element, Element) or self.incoming_amount.is_zero:
                raise ValueError("Reaction 评估需要正的入射元素量")
            context = ReactionTriggerContext(
                elemental_application=ReactionElementalApplication(
                    self.incoming_element,
                    self.incoming_amount,
                )
            )
        else:
            application = context.elemental_application
            if application is None:
                if self.incoming_element is not None or not self.incoming_amount.is_zero:
                    raise ValueError("无元素施加 Trigger Context 不能携带入射元素量")
            elif (
                self.incoming_element is not application.element
                or self.incoming_amount != application.amount
            ):
                raise ValueError("ReactionTriggerContext 与入射元素观察不一致")
        frozen_state = self.observed_frozen_state
        crystallize_source = self.crystallize_source_observation
        if crystallize_source is not None:
            if not isinstance(crystallize_source, CrystallizeSourceObservation):
                raise ValueError(
                    "crystallize_source_observation 必须是 CrystallizeSourceObservation 或 None"
                )
            if crystallize_source.source_ref != self.source_ref:
                raise ValueError("结晶来源观察必须与 Reaction 请求来源一致")
        if frozen_state is not None:
            if not isinstance(frozen_state, FrozenState):
                raise ValueError("observed_frozen_state 必须是 FrozenState 或 None")
            if frozen_state.subject_ref != self.subject_ref:
                raise ValueError("FrozenState 观察主体必须与 Reaction 请求一致")
            frozen_aura = self.observed_aura.component_for(AuraKind.FROZEN)
            if frozen_aura is None or frozen_aura.state_link_refs != (frozen_state.state_link_ref,):
                raise ValueError("FrozenState 观察必须与冻元素 Aura Link 一致")
        electro_charged_state = self.observed_electro_charged_state
        if electro_charged_state is not None:
            if not isinstance(electro_charged_state, ElectroChargedState):
                raise ValueError(
                    "observed_electro_charged_state 必须是 ElectroChargedState 或 None"
                )
            if electro_charged_state.subject_ref != self.subject_ref:
                raise ValueError("ElectroChargedState 观察主体必须与 Reaction 请求一致")
        burning_state = self.observed_burning_state
        if burning_state is not None:
            if not isinstance(burning_state, BurningState):
                raise ValueError("observed_burning_state 必须是 BurningState 或 None")
            if burning_state.subject_ref != self.subject_ref:
                raise ValueError("BurningState 观察主体必须与 Reaction 请求一致")
            burning_aura = self.observed_aura.component_for(AuraKind.BURNING)
            dendro_like = tuple(
                component
                for component in self.observed_aura.components
                if component.aura_kind in {AuraKind.DENDRO, AuraKind.QUICKEN}
                and burning_state.burning_aura_link_ref in component.state_link_refs
            )
            dendro_like_links = tuple(
                sorted(
                    {
                        link_ref
                        for component in dendro_like
                        for link_ref in component.state_link_refs
                    },
                    key=lambda item: item.link_key,
                )
            )
            if (
                burning_aura is None
                or not dendro_like
                or burning_aura.state_link_refs != (burning_state.burning_aura_link_ref,)
                or dendro_like_links != burning_state.dendro_like_link_refs
            ):
                raise ValueError("BurningState 观察必须与燃元素和类草 Aura Link 一致")
        quicken_state = self.observed_quicken_state
        if quicken_state is not None:
            if not isinstance(quicken_state, QuickenState):
                raise ValueError("observed_quicken_state 必须是 QuickenState 或 None")
            if quicken_state.subject_ref != self.subject_ref:
                raise ValueError("QuickenState 观察主体必须与 Reaction 请求一致")
            quicken_aura = self.observed_aura.component_for(AuraKind.QUICKEN)
            if (
                quicken_aura is None
                or quicken_state.quicken_aura_link_ref not in quicken_aura.state_link_refs
            ):
                raise ValueError("QuickenState 观察必须与激元素 Aura Link 一致")
        qualification = self.catalyze_impact_qualification
        if qualification is not None:
            if not isinstance(qualification, CatalyzeImpactQualification):
                raise ValueError(
                    "catalyze_impact_qualification 必须是 CatalyzeImpactQualification 或 None"
                )
            if qualification.target_impact_ref != self.target_impact_ref:
                raise ValueError("激化资格证据必须引用当前 target_impact_ref")
        if not isinstance(self.state_maintenance_allowed, bool):
            raise ValueError("state_maintenance_allowed 必须是布尔值")
        character_source_refs = tuple(self.character_source_refs)
        if any(not isinstance(item, ElementalSourceRef) for item in character_source_refs):
            raise ValueError("character_source_refs 必须是 ElementalSourceRef 序列")
        if len(set(character_source_refs)) != len(character_source_refs):
            raise ValueError("character_source_refs 不能重复")
        capability_keys = frozenset(self.reaction_capability_keys)
        if any(not isinstance(item, str) or not item.strip() for item in capability_keys):
            raise ValueError("reaction_capability_keys 必须是非空字符串集合")
        object.__setattr__(self, "character_source_refs", tuple(sorted(character_source_refs)))
        object.__setattr__(self, "reaction_capability_keys", capability_keys)
        freeze_resistance = self.freeze_resistance_observation
        if freeze_resistance is not None:
            if not isinstance(freeze_resistance, FreezeResistanceObservation):
                raise ValueError(
                    "freeze_resistance_observation 必须是 FreezeResistanceObservation 或 None"
                )
            if freeze_resistance.subject_ref != self.subject_ref:
                raise ValueError("冻结抗性观察主体必须与 Reaction 请求一致")
            if freeze_resistance.frame != self.frame:
                raise ValueError("冻结抗性观察帧必须与 Reaction 请求一致")
        object.__setattr__(self, "trigger_context", context)

    @property
    def has_active_frozen_state(self) -> bool:
        return self.observed_frozen_state is not None

    @property
    def has_active_burning_state(self) -> bool:
        return self.observed_burning_state is not None

    @property
    def has_active_quicken_state(self) -> bool:
        return self.observed_quicken_state is not None


@dataclass(frozen=True, slots=True)
class ReactionResolution:
    request: ReactionEvaluationRequest
    occurrence: ReactionOccurrence | None
    damage_adjustment: CurrentImpactDamageAdjustment | CatalyzeCurrentImpactDamageAdjustment | None
    decision_sequence: ReactionDecisionSequence | None = None
    generated_impact_batches: tuple[ReactionGeneratedImpactBatch, ...] = ()
    establishment_gate_resolutions: tuple[ReactionEstablishmentGateResolution, ...] = ()

    def __post_init__(self) -> None:
        if self.damage_adjustment is not None and not isinstance(
            self.damage_adjustment,
            (CurrentImpactDamageAdjustment, CatalyzeCurrentImpactDamageAdjustment),
        ):
            raise ValueError("damage_adjustment 必须是受支持的当前 Impact 调整")
        sequence = self.decision_sequence
        if sequence is None:
            sequence = (
                ReactionDecisionSequence()
                if self.occurrence is None
                else ReactionDecisionSequence(
                    (
                        ReactionDecisionStep(
                            0,
                            (self.occurrence.reaction_key,),
                            (self.occurrence.transition,),
                            (),
                            (self.occurrence,),
                        ),
                    )
                )
            )
        if not isinstance(sequence, ReactionDecisionSequence):
            raise ValueError("decision_sequence 必须是 ReactionDecisionSequence 或 None")
        assert isinstance(sequence, ReactionDecisionSequence)
        occurrences = tuple(
            occurrence for step in sequence.steps for occurrence in step.occurrences
        )
        if self.occurrence is None and occurrences:
            object.__setattr__(self, "occurrence", occurrences[0])
        elif self.occurrence is not None and (not occurrences or occurrences[0] != self.occurrence):
            raise ValueError("Resolution.occurrence 必须对应决策序列第一个 occurrence")
        generated_impact_batches = tuple(self.generated_impact_batches)
        if any(
            not isinstance(item, ReactionGeneratedImpactBatch) for item in generated_impact_batches
        ):
            raise ValueError("generated_impact_batches 必须是 ReactionGeneratedImpactBatch 序列")
        occurrence_refs = {item.occurrence_ref for item in occurrences}
        if any(
            not set(item.parent_occurrence_refs).issubset(occurrence_refs)
            for item in generated_impact_batches
        ):
            raise ValueError("派生元素 Impact batch 必须引用当前决策序列中的 occurrence")
        object.__setattr__(self, "decision_sequence", sequence)
        object.__setattr__(self, "generated_impact_batches", generated_impact_batches)
        gate_resolutions = tuple(self.establishment_gate_resolutions)
        if any(
            not isinstance(item, ReactionEstablishmentGateResolution) for item in gate_resolutions
        ):
            raise ValueError("establishment_gate_resolutions 必须是成立 Gate 决议序列")
        object.__setattr__(self, "establishment_gate_resolutions", gate_resolutions)

    @property
    def sequence(self) -> ReactionDecisionSequence:
        """规范化后的决策序列；构造后始终存在。"""
        assert self.decision_sequence is not None
        return self.decision_sequence

    @property
    def establishment_gate_blocked(self) -> bool:
        return any(
            resolution.decision is ReactionEstablishmentGateDecision.ESTABLISHMENT_GATE_BLOCKED
            for resolution in self.establishment_gate_resolutions
        )

    @property
    def effect_groups(self) -> tuple[ReactionEffectGroup, ...]:
        return tuple(
            group
            for step in self.sequence.steps
            for occurrence in step.occurrences
            for group in occurrence.effect_groups
        )


class InteractionReactionRule(Protocol):
    def evaluate(
        self,
        request: ReactionEvaluationRequest,
        definition: ReactionDefinition,
    ) -> ReactionResolution | None:
        """返回匹配到的无状态反应；无匹配时返回 ``None``。"""


@dataclass(frozen=True, slots=True)
class ReactionDefinition:
    reaction_key: str
    handler_key: str
    trigger_signatures: tuple[ReactionTriggerSignature, ...]
    profiles: tuple[ReactionProfileVariant, ...]
    rule: InteractionReactionRule
    entry_kind: ReactionEntryKind = ReactionEntryKind.ELEMENTAL_INTERACTION
    selection_priority: int = 0

    def __post_init__(self) -> None:
        _text(self.reaction_key, "reaction_key")
        _text(self.handler_key, "handler_key")
        if not isinstance(self.entry_kind, ReactionEntryKind):
            raise ValueError("Reaction Definition 的 entry_kind 不受支持")
        if (
            isinstance(self.selection_priority, bool)
            or not isinstance(self.selection_priority, int)
            or self.selection_priority < 0
        ):
            raise ValueError("Reaction Definition selection_priority 必须是非负整数")
        signatures = tuple(self.trigger_signatures)
        profiles = tuple(self.profiles)
        if self.entry_kind is ReactionEntryKind.ELEMENTAL_INTERACTION and (
            not signatures or not profiles
        ):
            raise ValueError("Reaction Definition 必须声明签名和 Profile")
        if len({item.direction_key for item in signatures}) != len(signatures):
            raise ValueError("Reaction Definition 的 direction_key 不能重复")
        if {item.direction_key for item in profiles} != {item.direction_key for item in signatures}:
            raise ValueError("Reaction Profile 必须与签名方向一一对应")
        object.__setattr__(self, "trigger_signatures", signatures)
        object.__setattr__(self, "profiles", profiles)

    def profile_for(self, direction_key: str) -> ReactionProfileVariant:
        return next(item for item in self.profiles if item.direction_key == direction_key)


@dataclass(frozen=True, slots=True)
class ReactionMutationPlan:
    operation_id: str
    frame: int
    interaction_ids: tuple[str, ...]
    expected_store_version: int
    resolutions: tuple[ReactionResolution, ...]
    establishment_gate_plan: ReactionEstablishmentGateMutationPlan | None = None

    def __post_init__(self) -> None:
        if self.establishment_gate_plan is not None:
            if self.establishment_gate_plan.frame != self.frame:
                raise ValueError("Reaction 与成立 Gate 计划帧必须一致")
            if self.establishment_gate_plan.expected_store_version != self.expected_store_version:
                raise ValueError("Reaction 与成立 Gate 计划必须使用同一 Store version")


@dataclass(frozen=True, slots=True)
class ReactionCommitReceipt:
    plan: ReactionMutationPlan
    version: int
