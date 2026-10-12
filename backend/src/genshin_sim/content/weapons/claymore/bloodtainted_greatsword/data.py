"""沐浴龙血的剑内容数据：稳定键、版本与被动数值口径。"""

from __future__ import annotations

from genshin_sim.core.elements import Element

BLOODTAINTED_GREATSWORD_KEY_PREFIX = "weapon.bloodtainted_greatsword"
BLOODTAINTED_GREATSWORD_HANDLER_KEY = BLOODTAINTED_GREATSWORD_KEY_PREFIX
BLOODTAINTED_GREATSWORD_PASSIVE_EFFECT_HANDLER_KEY = f"{BLOODTAINTED_GREATSWORD_KEY_PREFIX}.passive"
BLOODTAINTED_GREATSWORD_CONTENT_VERSION = "dev-bloodtainted-greatsword"

# 被动审计标签。
BLOODTAINTED_GREATSWORD_AUDIT_TAG = "bloodtainted_greatsword"

# 资产效果参数的位置约定：components[0] 是受影响敌人的伤害加成。
BLOODTAINTED_GREATSWORD_BONUS_COMPONENT_INDEX = 0

# 「处于火元素或雷元素影响下」：按 core.elements 的统一口径判定（燃烧归火）。
BLOODTAINTED_GREATSWORD_AFFECTED_ELEMENTS = (Element.PYRO, Element.ELECTRO)
