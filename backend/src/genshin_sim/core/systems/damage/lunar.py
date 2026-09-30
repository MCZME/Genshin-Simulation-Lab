"""月曜反应伤害公式的槽位结构与纯计算。

本模块只承载月曜公式的**位置结构、机制侧冻结基线与槽位键**，以及
"槽位合并值 → 伤害"的纯计算。影响数值的效果一律以 ``DamageModifierTerm``
进入槽位账单，由 ``core/systems/damage/formulas.py`` 的结算分支收集、署名与消费。

月曜有直伤（``CHARACTER_DIRECT``）与反应复合（``REACTION_COMPOSITE``）两个模式，
两者共用同一套位置与槽位通道，差异只在基础值来源与反应系数：

- 直伤模式的基础值是 ``主属性 × 倍率 × 倍率百分比``，由参与者的 ``scaling_terms``
  承载；
- 反应复合模式的基础值是机制侧冻结的等级基础伤害，没有内容侧来源。

两个模式的倍率区都不在这套槽位白名单里：复合模式没有内容侧来源，直伤模式的
倍率虽然可以被修饰，但绑定在**参与者**上，而 component_key 的合法集合由
``DamageModifierIndex`` 从请求级 ``scaling_terms`` 读取，参与者组件在顶层收集里
无法寻址（详见 ``formulas.py`` 的 ``LUNAR_ALLOWED_MODIFIER_STAGES`` 说明）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# 反应月曜复合模式按折前伤害稳定排序后使用的固定权重。
#
# 权重与反应系数是一对口径：本权重取「未折入」写法（0.60 : 0.30 : 0.05，即
# 1 : 1/2 : 1/12），因此机制侧传入的 ``reaction_multiplier`` 必须是资料里的未折入
# 反应系数（月感电 3.0、月结晶 1.6）。资料另有一套把最高权重折进反应倍率的等价
# 写法（反应倍率 1.8 / 0.96 配 1 : 1/2 : 1/12 分配）；两套逐组分等价，换口径时
# 权重与系数必须同时改，否则会重复计入 0.60。
LUNAR_COMPOSITE_WEIGHTS: tuple[float, ...] = (0.60, 0.30, 0.05)

# 月曜公式的槽位键：与 allowed_modifier_stages 白名单按位置一一对应，
# 供槽位三段审计（冻结基线 / Σ修饰项 / 合并值）稳定命名。倍率区由
# scaling 策略给出、精通、暴击与抗性由面板与策略给出，因此不在此重复命名。
LUNAR_SLOT_BASE_DAMAGE_BONUS = "lunar_base_damage_bonus"
LUNAR_SLOT_REACTION_BONUS = "lunar_reaction_bonus"
LUNAR_SLOT_ADDITIONAL_BASE_DAMAGE = "lunar_additional_base_damage"
LUNAR_SLOT_ASCENSION_MULTIPLIER = "lunar_ascension_multiplier"


@dataclass(frozen=True, slots=True)
class LunarZoneSlotAudit:
    """月曜一个可修饰位置的三段审计。

    ``baseline`` 是机制侧冻结或面板读取得到的基础值，``modifier_sum`` 是从槽位
    账单收集到的修饰项合计，``merged`` 是进入公式实算的合并值。三段同时保留，
    使 ``merged`` 偏离基线时可以定位到是谁贡献了多少。
    """

    slot_key: str
    baseline: float
    modifier_sum: float
    merged: float

    def __post_init__(self) -> None:
        for name in ("baseline", "modifier_sum", "merged"):
            value = float(getattr(self, name))
            if not math.isfinite(value):
                raise ValueError(f"{self.slot_key}.{name} 必须是有限数字")
            object.__setattr__(self, name, value)

    def to_dict(self) -> dict[str, object]:
        """返回稳定的槽位审计字典。"""

        return {
            "slot_key": self.slot_key,
            "baseline": self.baseline,
            "modifier_sum": self.modifier_sum,
            "merged": self.merged,
        }


@dataclass(frozen=True, slots=True)
class LunarZoneDamage:
    """月曜单组分公式的一次纯计算结果。

    ``base_damage_after_reaction`` 是基础区括号值（倍率 × 反应倍率 × 基础伤害提升
    × 精通与反应增伤区 + 附加伤害），``damage`` 是在此之上乘算暴击、擢升与抗性后
    的组分伤害。分开保留是为了让扁平结果模型能用括号值填 ``base_damage``。
    """

    base_damage_after_reaction: float
    reaction_uplift_multiplier: float
    critical_multiplier: float
    ascension_multiplier: float
    resistance_multiplier: float
    damage: float

    def __post_init__(self) -> None:
        for name in (
            "base_damage_after_reaction",
            "reaction_uplift_multiplier",
            "critical_multiplier",
            "ascension_multiplier",
            "resistance_multiplier",
            "damage",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"月曜 {name} 必须是有限非负数")
            object.__setattr__(self, name, value)

    def to_dict(self) -> dict[str, object]:
        """返回稳定的区间计算结果字典。"""

        return {
            "base_damage_after_reaction": self.base_damage_after_reaction,
            "reaction_uplift_multiplier": self.reaction_uplift_multiplier,
            "critical_multiplier": self.critical_multiplier,
            "ascension_multiplier": self.ascension_multiplier,
            "resistance_multiplier": self.resistance_multiplier,
            "damage": self.damage,
        }


def resolve_lunar_zone_damage(
    *,
    core_base_damage: float,
    reaction_multiplier: float,
    elemental_mastery: float,
    mastery_numerator: float,
    mastery_denominator: float,
    base_damage_bonus: float,
    reaction_bonus: float,
    additional_base_damage: float,
    critical_multiplier: float,
    ascension_multiplier: float,
    resistance_multiplier: float,
) -> LunarZoneDamage:
    """按资料中的月曜区间顺序结算一个组分公式。

    入参全部是**已合并的槽位值**（冻结基线 + 槽位账单修饰项合计），本函数不做
    任何收集或署名：那是结算分支的职责。``core_base_damage`` 是倍率区合并值——
    直伤模式来自 ``scaling_terms`` 的倍率区策略，反应复合模式是冻结的等级基础伤害。
    """

    if mastery_denominator <= 0:
        raise ValueError("月曜精通系数分母必须为正数")
    mastery_bonus = (
        mastery_numerator * elemental_mastery / (elemental_mastery + mastery_denominator)
    )
    reaction_uplift_multiplier = 1.0 + mastery_bonus + reaction_bonus
    if reaction_uplift_multiplier <= 0:
        raise ValueError("月曜反应提升乘数必须为正数")
    base_damage_after_reaction = (
        core_base_damage
        * reaction_multiplier
        * (1.0 + base_damage_bonus)
        * reaction_uplift_multiplier
        + additional_base_damage
    )
    if not math.isfinite(base_damage_after_reaction) or base_damage_after_reaction < 0:
        raise ValueError("月曜基础伤害区必须是有限非负数")
    damage = (
        base_damage_after_reaction
        * critical_multiplier
        * ascension_multiplier
        * resistance_multiplier
    )
    if not math.isfinite(damage) or damage < 0:
        raise ValueError("月曜组分伤害必须是有限非负数")
    return LunarZoneDamage(
        base_damage_after_reaction=base_damage_after_reaction,
        reaction_uplift_multiplier=reaction_uplift_multiplier,
        critical_multiplier=critical_multiplier,
        ascension_multiplier=ascension_multiplier,
        resistance_multiplier=resistance_multiplier,
        damage=damage,
    )
