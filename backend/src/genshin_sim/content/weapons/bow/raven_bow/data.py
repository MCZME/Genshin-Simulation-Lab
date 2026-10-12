"""鸦羽弓内容数据：稳定键、版本与被动数值口径。"""

from __future__ import annotations

from genshin_sim.core.elements import Element

RAVEN_BOW_KEY_PREFIX = "weapon.raven_bow"
RAVEN_BOW_HANDLER_KEY = RAVEN_BOW_KEY_PREFIX
RAVEN_BOW_PASSIVE_EFFECT_HANDLER_KEY = f"{RAVEN_BOW_KEY_PREFIX}.passive"
RAVEN_BOW_CONTENT_VERSION = "dev-raven-bow"

# 被动审计标签。
RAVEN_BOW_AUDIT_TAG = "raven_bow"

# 资产效果参数的位置约定：components[0] 是受影响敌人的伤害加成。
RAVEN_BOW_BONUS_COMPONENT_INDEX = 0

# 「处于水元素或火元素影响下」：按 core.elements 的统一口径判定（燃烧归火）。
RAVEN_BOW_AFFECTED_ELEMENTS = (Element.HYDRO, Element.PYRO)
