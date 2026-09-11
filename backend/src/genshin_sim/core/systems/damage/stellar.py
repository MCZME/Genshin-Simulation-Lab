"""星烁反应独立伤害公式的无状态实现。

该模块只消费角色能力已经解析出的强类型区间，不读取 Buff、ReactionState
或协调器；接入 DamageResolver 的适配层可在角色技能切片中完成。
"""

from __future__ import annotations

import math
from dataclasses import dataclass


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


@dataclass(frozen=True, slots=True)
class StellarReactionDamageResolution:
    input: StellarReactionDamageInput
    damage: float


def resolve_stellar_reaction_damage(
    value: StellarReactionDamageInput,
) -> StellarReactionDamageResolution:
    """按资料中的直伤星烁区间顺序结算一名参与者。"""
    mastery = 6.0 * value.elemental_mastery / (value.elemental_mastery + 2000.0)
    damage = (
        value.scaling_value
        * value.stellar_base_multiplier
        * (1.0 + value.stellar_base_bonus)
        * (1.0 + mastery + value.stellar_bonus)
        * value.stellar_authority_multiplier
        + value.direct_stellar_feather_addition
    )
    damage *= value.critical_multiplier * value.resistance_multiplier
    damage *= 1.0 + value.stellar_ascension_bonus
    if not math.isfinite(damage) or damage < 0:
        raise ValueError("星烁伤害结果必须是有限非负数")
    return StellarReactionDamageResolution(value, damage)
