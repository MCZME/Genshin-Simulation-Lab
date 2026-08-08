from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from genshin_sim.core.actions import ActionOwnerRef, CandidateTargetRef
from genshin_sim.core.elements import AuraAmount, Element
from genshin_sim.core.space.geometry import ImpactAreaSpec
from genshin_sim.core.systems.aura import AuraStrength
from genshin_sim.core.systems.damage import DamageScalingTerm


class ImpactKind(StrEnum):
    """动作或运行态实体发起的机制请求类型。"""

    DAMAGE = "damage"
    SHIELD = "shield"
    HEAL = "heal"
    APPLY_AURA = "apply_aura"
    APPLY_STATUS = "apply_status"
    CREATE_ENTITY = "create_entity"
    ENERGY = "energy"
    MOVEMENT = "movement"


class StrikeType(StrEnum):
    """Damage Impact 提供给状态型 Reaction 的稳定打击证据。"""

    DEFAULT = "默认"
    BLUNT = "钝击"


@dataclass(frozen=True, slots=True)
class DamageImpactSpec:
    """所有 Damage Impact 共用的类型化命中意图。"""

    impact_ref: str
    main_attack_tag: str
    element: Element
    scaling_terms: tuple[DamageScalingTerm, ...] = ()
    flat_base_damage: float = 0.0
    can_crit: bool = True
    additional_attack_tags: tuple[str, ...] = ()
    strike_type: StrikeType | None = None
    range_type: str | None = None
    elemental_strength: AuraStrength | None = None
    elemental_amount: AuraAmount = field(default_factory=AuraAmount.zero)
    icd_tag_key: str | None = None
    icd_sequence_key: str | None = None
    area: ImpactAreaSpec | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.impact_ref, "impact_ref"),
            (self.main_attack_tag, "main_attack_tag"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} 必须是非空字符串")
        if not isinstance(self.element, Element):
            raise ValueError("DamageImpactSpec 的 element 不受支持")
        terms = tuple(self.scaling_terms)
        if any(not isinstance(term, DamageScalingTerm) for term in terms):
            raise ValueError("scaling_terms 必须是 DamageScalingTerm 序列")
        if len({term.component_key for term in terms}) != len(terms):
            raise ValueError("DamageImpactSpec 的 component_key 不能重复")
        if isinstance(self.flat_base_damage, bool) or not isinstance(
            self.flat_base_damage,
            int | float,
        ):
            raise ValueError("flat_base_damage 必须是数字")
        if not isinstance(self.can_crit, bool):
            raise ValueError("can_crit 必须是布尔值")
        tags = tuple(self.additional_attack_tags)
        if any(not isinstance(tag, str) or not tag.strip() for tag in tags):
            raise ValueError("additional_attack_tags 必须是非空字符串序列")
        if self.strike_type is not None and not isinstance(self.strike_type, StrikeType):
            raise ValueError("strike_type 提供时必须是 StrikeType")
        if self.range_type is not None and (
            not isinstance(self.range_type, str) or not self.range_type.strip()
        ):
            raise ValueError("range_type 提供时必须是非空字符串")
        if self.elemental_strength is not None and not isinstance(
            self.elemental_strength,
            AuraStrength,
        ):
            raise ValueError("elemental_strength 必须是 AuraStrength 或 None")
        if not isinstance(self.elemental_amount, AuraAmount):
            raise ValueError("elemental_amount 必须是 AuraAmount")
        if self.elemental_strength is None and not self.elemental_amount.is_zero:
            raise ValueError("elemental_amount 为正时必须提供 elemental_strength")
        if self.elemental_strength is not None and self.element is Element.PHYSICAL:
            raise ValueError("物理伤害不能携带元素施加")
        if (self.icd_tag_key is None) != (self.icd_sequence_key is None):
            raise ValueError("ICD 标签与序列必须同时提供或同时省略")
        for value, name in (
            (self.icd_tag_key, "icd_tag_key"),
            (self.icd_sequence_key, "icd_sequence_key"),
        ):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} 提供时必须是非空字符串")
        if self.area is not None and not isinstance(self.area, ImpactAreaSpec):
            raise ValueError("area 提供时必须是非空 ImpactAreaSpec")
        object.__setattr__(self, "scaling_terms", terms)
        object.__setattr__(self, "additional_attack_tags", tags)


@dataclass(frozen=True, slots=True)
class ElementalApplicationSpec:
    """不造成伤害的元素施加类型化意图。"""

    impact_ref: str
    element: Element
    elemental_strength: AuraStrength
    elemental_amount: AuraAmount = field(default_factory=AuraAmount.one)
    icd_tag_key: str | None = None
    icd_sequence_key: str | None = None
    area: ImpactAreaSpec | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.impact_ref, str) or not self.impact_ref.strip():
            raise ValueError("impact_ref 必须是非空字符串")
        if not isinstance(self.element, Element):
            raise ValueError("ElementalApplicationSpec 的 element 不受支持")
        if not isinstance(self.elemental_strength, AuraStrength):
            raise ValueError("ElementalApplicationSpec 的 elemental_strength 不受支持")
        if not isinstance(self.elemental_amount, AuraAmount) or self.elemental_amount.is_zero:
            raise ValueError("ElementalApplicationSpec 的 elemental_amount 必须为正数")
        if (self.icd_tag_key is None) != (self.icd_sequence_key is None):
            raise ValueError("ICD 标签与序列必须同时提供或同时省略")
        if self.area is not None and not isinstance(self.area, ImpactAreaSpec):
            raise ValueError("area 提供时必须是非空 ImpactAreaSpec")
        for value, name in (
            (self.icd_tag_key, "icd_tag_key"),
            (self.icd_sequence_key, "icd_sequence_key"),
        ):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} 提供时必须是非空字符串")


@dataclass(frozen=True, slots=True)
class ImpactRequest:
    """一次待机制系统结算的通用影响请求。

    该模型只描述请求来源和结算意图，不直接计算伤害、治疗、附着或状态结果。
    """

    frame: int
    kind: ImpactKind
    impact_key: str
    owner_slot: int | None = None
    action_key: str | None = None
    request_id: str | None = None
    source_impact_point_id: str | None = None
    target_refs: tuple[str, ...] = ()
    anchor_entity_id: str | None = None
    scaling_ref: str | None = None
    element: str | None = None
    tags: tuple[str, ...] = ()
    params: Mapping[str, object] = field(default_factory=dict)
    damage_spec: DamageImpactSpec | None = None
    elemental_application_spec: ElementalApplicationSpec | None = None

    def __post_init__(self) -> None:
        if self.frame < 0:
            msg = "影响请求帧号不能为负数"
            raise ValueError(msg)
        if not self.impact_key.strip():
            msg = "impact_key 必须是非空字符串"
            raise ValueError(msg)
        if self.owner_slot is not None and self.owner_slot <= 0:
            msg = "owner_slot 必须是正整数"
            raise ValueError(msg)

        object.__setattr__(self, "target_refs", tuple(self.target_refs))
        object.__setattr__(self, "tags", tuple(self.tags))
        object.__setattr__(self, "params", dict(self.params))
        if self.damage_spec is not None and self.kind is not ImpactKind.DAMAGE:
            raise ValueError("只有 DAMAGE ImpactRequest 可以携带 damage_spec")
        if self.elemental_application_spec is not None and self.kind is not ImpactKind.APPLY_AURA:
            raise ValueError("只有 APPLY_AURA ImpactRequest 可以携带 elemental_application_spec")
        if self.damage_spec is not None and self.elemental_application_spec is not None:
            raise ValueError("ImpactRequest 不能同时携带 damage_spec 与 elemental_application_spec")
        for value, name in (
            (self.request_id, "request_id"),
            (self.source_impact_point_id, "source_impact_point_id"),
            (self.anchor_entity_id, "anchor_entity_id"),
        ):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} 提供时必须是非空字符串")
        if self._requires_elemental_root_identity() and not (
            self.request_id or self.source_impact_point_id
        ):
            raise ValueError("元素交互 ImpactRequest 必须提供 request_id 或 source_impact_point_id")

    def _requires_elemental_root_identity(self) -> bool:
        spec = self.damage_spec
        return self.elemental_application_spec is not None or (
            spec is not None
            and (
                (spec.elemental_strength is not None and not spec.elemental_amount.is_zero)
                or spec.strike_type is not None
            )
        )


@dataclass(frozen=True, slots=True)
class ActionImpactContext:
    """ActionImpactPoint 到期后传给 content impact factory 的上下文。"""

    frame: int
    impact_point_id: str
    source_instance_id: int
    owner: ActionOwnerRef
    action_key: str
    impact_key: str
    target_refs: tuple[CandidateTargetRef, ...] = ()
    params: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.frame < 0:
            msg = "动作影响上下文帧号不能为负数"
            raise ValueError(msg)
        if self.source_instance_id <= 0:
            msg = "source_instance_id 必须是正整数"
            raise ValueError(msg)
        if not self.impact_point_id.strip():
            msg = "impact_point_id 必须是非空字符串"
            raise ValueError(msg)
        if not self.action_key.strip():
            msg = "action_key 必须是非空字符串"
            raise ValueError(msg)
        if not self.impact_key.strip():
            msg = "impact_key 必须是非空字符串"
            raise ValueError(msg)
        object.__setattr__(self, "target_refs", tuple(self.target_refs))
        object.__setattr__(self, "params", dict(self.params))
