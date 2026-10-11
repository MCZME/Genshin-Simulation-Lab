"""旅行剑内容数据：稳定键、版本与被动数值口径。

资产来源：Project Amber / Yatta 当前默认数据（``weapon:11303``）。
被动「旅程」：获得元素晶球或元素微粒时，恢复生命值（按精炼取最大生命比例）。
"""

from __future__ import annotations

TRAVELERS_HANDY_SWORD_KEY_PREFIX = "weapon.travelers_handy_sword"
TRAVELERS_HANDY_SWORD_HANDLER_KEY = TRAVELERS_HANDY_SWORD_KEY_PREFIX
TRAVELERS_HANDY_SWORD_PASSIVE_EFFECT_HANDLER_KEY = f"{TRAVELERS_HANDY_SWORD_KEY_PREFIX}.passive"
TRAVELERS_HANDY_SWORD_CONTENT_VERSION = "dev-travelers-handy-sword"

# 治疗命中键。
TRAVELERS_HANDY_SWORD_HEAL_IMPACT_KEY = f"{TRAVELERS_HANDY_SWORD_KEY_PREFIX}.heal"

# 资产效果参数的位置约定：components[0] 是治疗的最大生命值比例。
HEAL_RATIO_COMPONENT_INDEX = 0
