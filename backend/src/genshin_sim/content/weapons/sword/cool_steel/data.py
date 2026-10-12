"""冷刃内容数据：稳定键、版本与被动数值口径。"""

from __future__ import annotations

from genshin_sim.core.elements import Element

COOL_STEEL_KEY_PREFIX = "weapon.cool_steel"
COOL_STEEL_HANDLER_KEY = COOL_STEEL_KEY_PREFIX
COOL_STEEL_PASSIVE_EFFECT_HANDLER_KEY = f"{COOL_STEEL_KEY_PREFIX}.passive"
COOL_STEEL_CONTENT_VERSION = "dev-cool-steel"

# 被动审计标签。
COOL_STEEL_AUDIT_TAG = "cool_steel"

# 资产效果参数的位置约定：components[0] 是受影响敌人的伤害加成。
COOL_STEEL_BONUS_COMPONENT_INDEX = 0

# 「处于水元素或冰元素影响下」：按 core.elements 的统一口径判定（冻结归冰）。
COOL_STEEL_AFFECTED_ELEMENTS = (Element.HYDRO, Element.CRYO)
