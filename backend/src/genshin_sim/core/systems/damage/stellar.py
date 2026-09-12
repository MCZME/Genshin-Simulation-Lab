"""星烁反应独立伤害公式的无状态实现。

该模块只消费角色能力已经解析出的强类型区间，不读取 Buff、ReactionState
或协调器；注册进 ``damage_formula.stellar_reaction`` 的结算分支在
``core/systems/damage/formulas.py`` 中负责实时属性读取与审计组装。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


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
    """星烁伤害的公式输入与区间审计。

    纯函数路径只填充 ``input`` 与 ``damage``；结算器分支额外写入实时
    元素精通、暴击区、抗性区与最终伤害审计。审计对象由 damage 模块构造，
    本模块不引入对 ``models`` 的运行时依赖。
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

    def to_dict(self) -> dict[str, object]:
        """返回稳定的星烁伤害审计摘要。"""

        return {
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
            "resistance_add": (
                None if self.resistance is None else self.resistance.resistance_add
            ),
            "stellar_ascension_bonus": self.input.stellar_ascension_bonus,
            "official_damage": self.official_damage,
            "debug_multiplier": self.debug_multiplier,
            "final_damage": self.final_damage,
        }


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
