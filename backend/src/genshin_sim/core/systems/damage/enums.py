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

    # 反应公式专属修饰项：由对应反应公式在自己的公式体内消费，不进入直伤槽位账单。
    # 剧变与星烁各占独立阶段，两公式的 allowed_modifier_stages 白名单互不牵连。
    TRANSFORMATIVE_REACTION_BONUS_ADD = "transformative_reaction_bonus_add"

    # 星烁公式专属阶段：按星烁公式的可修饰位置逐个切分，一个位置一个阶段。
    # 通用公式已有对应位置的一律复用通用阶段（倍率复用 component_coefficient_*、
    # 暴击复用 crit_*、抗性复用 resistance_add），不在此另设同名阶段。
    STELLAR_BASE_MULTIPLIER_ADD = "stellar_base_multiplier_add"
    STELLAR_BASE_BONUS_ADD = "stellar_base_bonus_add"
    STELLAR_REACTION_BONUS_ADD = "stellar_reaction_bonus_add"
    STELLAR_AUTHORITY_MULTIPLIER_ADD = "stellar_authority_multiplier_add"
    STELLAR_FEATHER_ADDITION_ADD = "stellar_feather_addition_add"
    STELLAR_ASCENSION_BONUS_ADD = "stellar_ascension_bonus_add"

    # 月曜公式专属阶段：同样按可修饰位置逐个切分。月曜的暴击位与抗性位复用通用
    # 阶段（暴击复用 crit_*、抗性复用 resistance_add），因此这里只补月曜独有位置。
    # 倍率位与反应系数位不开放，原因见 LUNAR_ALLOWED_MODIFIER_STAGES
    # 的注释。月曜两个模式（直伤与反应复合）共用同一套阶段，差异只在基础值来源与
    # 反应系数。
    LUNAR_BASE_DAMAGE_BONUS_ADD = "lunar_base_damage_bonus_add"
    LUNAR_REACTION_BONUS_ADD = "lunar_reaction_bonus_add"
    LUNAR_ADDITIONAL_BASE_DAMAGE_ADD = "lunar_additional_base_damage_add"
    LUNAR_ASCENSION_BONUS_ADD = "lunar_ascension_bonus_add"


class CritOutcome(StrEnum):
    """一次伤害的暴击判定结果。"""

    NOT_APPLICABLE = "not_applicable"
    NON_CRITICAL = "non_critical"
    CRITICAL = "critical"


class DamageModifierStackingPolicy(StrEnum):
    """同一叠加组内选择生效修饰项的策略。"""

    HIGHEST = "highest"
    LOWEST = "lowest"
