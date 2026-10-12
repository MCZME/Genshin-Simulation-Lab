"""魔导绪论内容数据：稳定键、版本与被动数值口径。"""

from __future__ import annotations

from genshin_sim.core.elements import Element

MAGIC_GUIDE_KEY_PREFIX = "weapon.magic_guide"
MAGIC_GUIDE_HANDLER_KEY = MAGIC_GUIDE_KEY_PREFIX
MAGIC_GUIDE_PASSIVE_EFFECT_HANDLER_KEY = f"{MAGIC_GUIDE_KEY_PREFIX}.passive"
MAGIC_GUIDE_CONTENT_VERSION = "dev-magic-guide"

# 被动审计标签。
MAGIC_GUIDE_AUDIT_TAG = "magic_guide"

# 资产效果参数的位置约定：components[0] 是受影响敌人的伤害加成。
MAGIC_GUIDE_BONUS_COMPONENT_INDEX = 0

# 「处于水元素或雷元素影响下」：按 core.elements 的统一口径判定（水与雷没有派生持久分量）。
MAGIC_GUIDE_AFFECTED_ELEMENTS = (Element.HYDRO, Element.ELECTRO)
