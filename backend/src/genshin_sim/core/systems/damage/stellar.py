"""星烁反应独立伤害公式的无状态实现。

该模块只消费角色能力已经解析出的强类型区间，不读取 Buff、ReactionState
或协调器；注册进 ``damage_formula.stellar_reaction`` 的结算分支在
``core/systems/damage/formulas.py`` 中负责实时属性读取与审计组装。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from genshin_sim.core.attributes import AttributeSubjectKind, AttributeSubjectRef

# 反应星烁复合模式按折前伤害稳定排序后保留的参与者上限。
STELLAR_COMPOSITE_PARTICIPANT_LIMIT = 4


@dataclass(frozen=True, slots=True)
class StellarReactionParticipantInput:
    """星烁复合伤害中一名参与者的 Damage 侧输入。

    ``reaction_base_value`` 是该参与者自身等级对应的星烁反应基础值（观察期
    冻结）；星烁基础增伤、星烁增伤、星烁大权区、反应星烁羽毛区与星烁擢升
    按参与者各自携带；元素精通、暴击与目标抗性由公式实时读取。
    """

    participant_ref: AttributeSubjectRef
    source_level: int
    reaction_base_value: float
    stellar_base_bonus: float = 0.0
    stellar_bonus: float = 0.0
    stellar_authority_multiplier: float = 1.0
    stellar_feather_addition: float = 0.0
    stellar_ascension_bonus: float = 0.0
    can_crit: bool = True

    def __post_init__(self) -> None:
        if self.participant_ref.kind is not AttributeSubjectKind.CHARACTER:
            raise ValueError("星烁伤害参与者必须是角色主体")
        if (
            isinstance(self.source_level, bool)
            or not isinstance(self.source_level, int)
            or self.source_level <= 0
        ):
            raise ValueError("星烁伤害参与者等级必须是正整数")
        for name in (
            "reaction_base_value",
            "stellar_base_bonus",
            "stellar_bonus",
            "stellar_authority_multiplier",
            "stellar_feather_addition",
            "stellar_ascension_bonus",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value):
                raise ValueError(f"{name} 必须是有限数字")
            object.__setattr__(self, name, value)
        if self.reaction_base_value < 0 or self.stellar_feather_addition < 0:
            raise ValueError("星烁参与者基础值和羽毛区不能为负数")
        if self.stellar_authority_multiplier < 0 or self.stellar_ascension_bonus < 0:
            raise ValueError("星烁参与者乘数不能为负数")
        if not isinstance(self.can_crit, bool):
            raise ValueError("星烁参与者 can_crit 必须是布尔值")


@dataclass(frozen=True, slots=True)
class StellarReactionDamageInput:
    mode: str
    scaling_value: float
    stellar_base_multiplier: float
    elemental_mastery: float = 0.0
    stellar_base_bonus: float = 0.0
    stellar_bonus: float = 0.0
    stellar_authority_multiplier: float = 1.0
    direct_stellar_feather_addition: float = 0.0
    critical_multiplier: float = 1.0
    resistance_multiplier: float = 1.0
    stellar_ascension_bonus: float = 0.0
    participants: tuple[StellarReactionParticipantInput, ...] = ()

    def __post_init__(self) -> None:
        if self.mode not in {"character_direct", "reaction_composite"}:
            raise ValueError("星烁伤害 mode 不受支持")
        for name in (
            "scaling_value",
            "stellar_base_multiplier",
            "elemental_mastery",
            "stellar_base_bonus",
            "stellar_bonus",
            "stellar_authority_multiplier",
            "direct_stellar_feather_addition",
            "critical_multiplier",
            "resistance_multiplier",
            "stellar_ascension_bonus",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value):
                raise ValueError(f"{name} 必须是有限数字")
            object.__setattr__(self, name, value)
        if self.scaling_value < 0 or self.stellar_base_multiplier < 0:
            raise ValueError("星烁基础输入不能为负数")
        if self.elemental_mastery < 0 or self.direct_stellar_feather_addition < 0:
            raise ValueError("星烁精通和羽毛区不能为负数")
        if self.stellar_authority_multiplier < 0 or self.critical_multiplier < 0:
            raise ValueError("星烁乘数不能为负数")
        if self.resistance_multiplier < 0:
            raise ValueError("抗性乘数不能为负数")
        participants = tuple(self.participants)
        if any(not isinstance(item, StellarReactionParticipantInput) for item in participants):
            raise ValueError("participants 必须是 StellarReactionParticipantInput 序列")
        participant_ids = [item.participant_ref.entity_id for item in participants]
        if len(participant_ids) != len(set(participant_ids)):
            raise ValueError("星烁伤害参与者不能重复角色")
        if self.mode == "character_direct" and participants:
            raise ValueError("角色直伤星烁不能携带参与者列表")
        object.__setattr__(
            self,
            "participants",
            tuple(sorted(participants, key=lambda item: item.participant_ref.entity_id)),
        )


@dataclass(frozen=True, slots=True)
class StellarReactionComponentResolution:
    """反应星烁复合模式中一名参与者的独立结算审计。"""

    participant_ref: AttributeSubjectRef
    source_level: int
    reaction_base_value: float
    elemental_mastery: float
    mastery_bonus: float
    critical: Any | None
    resistance: Any | None
    component_damage: float
    weight: float
    weighted_damage: float
    source_attribute_trace: tuple[Any, ...] = ()
    target_attribute_trace: tuple[Any, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "reaction_base_value",
            "elemental_mastery",
            "mastery_bonus",
            "component_damage",
            "weight",
            "weighted_damage",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} 必须是有限非负数")
            object.__setattr__(self, name, value)

    def to_dict(self) -> dict[str, object]:
        return {
            "participant_ref": {
                "kind": self.participant_ref.kind.value,
                "entity_id": self.participant_ref.entity_id,
            },
            "source_level": self.source_level,
            "reaction_base_value": self.reaction_base_value,
            "elemental_mastery": self.elemental_mastery,
            "mastery_bonus": self.mastery_bonus,
            "crit_outcome": (None if self.critical is None else self.critical.outcome.value),
            "crit_multiplier": (None if self.critical is None else self.critical.multiplier),
            "resistance_multiplier": (
                None if self.resistance is None else self.resistance.multiplier
            ),
            "component_damage": self.component_damage,
            "weight": self.weight,
            "weighted_damage": self.weighted_damage,
        }


@dataclass(frozen=True, slots=True)
class StellarReactionDamageResolution:
    """星烁伤害的公式输入与区间审计。

    纯函数路径只填充 ``input`` 与 ``damage``；结算器分支额外写入实时
    元素精通、暴击区、抗性区与最终伤害审计。``reaction_composite`` 模式
    以 ``components`` 承载逐参与者结算与权重聚合，顶层字段取排名第一
    参与者的实时读取投影。审计对象由 damage 模块构造，本模块不引入对
    ``models`` 的运行时依赖。
    """

    input: StellarReactionDamageInput
    damage: float
    elemental_mastery: float = 0.0
    mastery_bonus: float = 0.0
    critical: Any | None = None
    resistance: Any | None = None
    official_damage: float = 0.0
    debug_multiplier: float = 1.0
    final_damage: float = 0.0
    components: tuple[StellarReactionComponentResolution, ...] = field(default=())
    source_attribute_trace: tuple[Any, ...] = field(default=())
    target_attribute_trace: tuple[Any, ...] = field(default=())

    def __post_init__(self) -> None:
        for name in (
            "damage",
            "elemental_mastery",
            "mastery_bonus",
            "official_damage",
            "debug_multiplier",
            "final_damage",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} 必须是有限非负数")
            object.__setattr__(self, name, value)
        components = tuple(self.components)
        if any(not isinstance(item, StellarReactionComponentResolution) for item in components):
            raise ValueError("components 必须是 StellarReactionComponentResolution 序列")
        object.__setattr__(self, "components", components)

    def to_dict(self) -> dict[str, object]:
        """返回稳定的星烁伤害审计摘要。"""

        payload = {
            "mode": self.input.mode,
            "scaling_value": self.input.scaling_value,
            "stellar_base_multiplier": self.input.stellar_base_multiplier,
            "stellar_base_bonus": self.input.stellar_base_bonus,
            "elemental_mastery": self.elemental_mastery,
            "mastery_bonus": self.mastery_bonus,
            "stellar_bonus": self.input.stellar_bonus,
            "stellar_authority_multiplier": self.input.stellar_authority_multiplier,
            "direct_stellar_feather_addition": self.input.direct_stellar_feather_addition,
            "crit_outcome": (None if self.critical is None else self.critical.outcome.value),
            "crit_rate": (None if self.critical is None else self.critical.crit_rate),
            "crit_damage": (None if self.critical is None else self.critical.crit_damage),
            "crit_multiplier": (None if self.critical is None else self.critical.multiplier),
            "resistance_multiplier": (
                None if self.resistance is None else self.resistance.multiplier
            ),
            "base_resistance": (
                None if self.resistance is None else self.resistance.base_resistance
            ),
            "resistance_add": (None if self.resistance is None else self.resistance.resistance_add),
            "stellar_ascension_bonus": self.input.stellar_ascension_bonus,
            "official_damage": self.official_damage,
            "debug_multiplier": self.debug_multiplier,
            "final_damage": self.final_damage,
        }
        if self.components:
            payload["components"] = [item.to_dict() for item in self.components]
        return payload


def resolve_stellar_zone_damage(
    *,
    scaling_value: float,
    stellar_base_multiplier: float,
    elemental_mastery: float,
    stellar_base_bonus: float,
    stellar_bonus: float,
    stellar_authority_multiplier: float,
    feather_addition: float,
    critical_multiplier: float,
    resistance_multiplier: float,
    stellar_ascension_bonus: float,
) -> float:
    """按资料中的星烁区间顺序结算一名参与者的完整单人伤害。"""

    mastery = 6.0 * elemental_mastery / (elemental_mastery + 2000.0)
    damage = (
        scaling_value
        * stellar_base_multiplier
        * (1.0 + stellar_base_bonus)
        * (1.0 + mastery + stellar_bonus)
        * stellar_authority_multiplier
        + feather_addition
    )
    damage *= critical_multiplier * resistance_multiplier
    damage *= 1.0 + stellar_ascension_bonus
    if not math.isfinite(damage) or damage < 0:
        raise ValueError("星烁伤害结果必须是有限非负数")
    return damage


def resolve_stellar_reaction_damage(
    value: StellarReactionDamageInput,
) -> StellarReactionDamageResolution:
    """按资料中的直伤星烁区间顺序结算一名参与者。"""

    damage = resolve_stellar_zone_damage(
        scaling_value=value.scaling_value,
        stellar_base_multiplier=value.stellar_base_multiplier,
        elemental_mastery=value.elemental_mastery,
        stellar_base_bonus=value.stellar_base_bonus,
        stellar_bonus=value.stellar_bonus,
        stellar_authority_multiplier=value.stellar_authority_multiplier,
        feather_addition=value.direct_stellar_feather_addition,
        critical_multiplier=value.critical_multiplier,
        resistance_multiplier=value.resistance_multiplier,
        stellar_ascension_bonus=value.stellar_ascension_bonus,
    )
    return StellarReactionDamageResolution(value, damage)
