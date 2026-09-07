"""完整伤害公式的稳定选择键。"""

from __future__ import annotations

FORMULA_KEY_GENERAL = "damage_formula.general"
FORMULA_KEY_TRANSFORMATIVE_REACTION = "damage_formula.transformative_reaction"
FORMULA_KEY_LUNAR_REACTION = "damage_formula.lunar_reaction"

KNOWN_FORMULA_KEYS = frozenset(
    {
        FORMULA_KEY_GENERAL,
        FORMULA_KEY_TRANSFORMATIVE_REACTION,
        FORMULA_KEY_LUNAR_REACTION,
    }
)

# 未注册主攻击标签的默认公式：原神中直伤统一走通用公式。
DEFAULT_FORMULA_KEY = FORMULA_KEY_GENERAL

# 反应命名空间：该前缀下的标签必须显式注册映射，未注册时报错而不是静默降级。
REACTION_TAG_PREFIX = "reaction."
