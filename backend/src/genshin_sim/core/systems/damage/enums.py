"""伤害系统使用的稳定枚举。"""

from __future__ import annotations

from enum import StrEnum


class LunarReactionDamageMode(StrEnum):
    """月曜伤害的来源模式。"""

    CHARACTER_DIRECT = "character_direct"
    REACTION_COMPOSITE = "reaction_composite"


class DamageReactionCapability(StrEnum):
    """Damage Profile 声明的反应公式扩展能力。"""

    SECONDARY_AMPLIFYING = "secondary_amplifying"


class DamageModifierStage(StrEnum):
    """伤害专用修饰项进入流水线的计算阶段。"""

    # 面板属性读取：公式从属性系统读取角色/目标面板值后物化为词条，
    # 作为对应槽位的基础贡献进入伤害账单；属性系统内部的 modifier 不进入伤害系统。
    PANEL_ATTRIBUTE_VALUE = "panel_attribute_value"
    PANEL_ELEMENT_BONUS = "panel_element_bonus"
    PANEL_CRIT_RATE = "panel_crit_rate"
    PANEL_CRIT_DAMAGE = "panel_crit_damage"
    PANEL_RESISTANCE = "panel_resistance"
    PANEL_ELEMENTAL_MASTERY = "panel_elemental_mastery"

    COMPONENT_COEFFICIENT_PERCENT_ADD = "component_coefficient_percent_add"
    COMPONENT_COEFFICIENT_FLAT_ADD = "component_coefficient_flat_add"
    BASE_DAMAGE_FLAT_ADD = "base_damage_flat_add"
    DAMAGE_BONUS_ADD = "damage_bonus_add"
    DEFENSE_REDUCTION = "defense_reduction"
    DEFENSE_IGNORE = "defense_ignore"
    CRIT_RATE_ADD = "crit_rate_add"
    CRIT_DAMAGE_ADD = "crit_damage_add"
    RESISTANCE_ADD = "resistance_add"


class CritOutcome(StrEnum):
    """一次伤害的暴击判定结果。"""

    NOT_APPLICABLE = "not_applicable"
    NON_CRITICAL = "non_critical"
    CRITICAL = "critical"


class DamageModifierStackingPolicy(StrEnum):
    """同一叠加组内选择生效修饰项的策略。"""

    HIGHEST = "highest"
    LOWEST = "lowest"
