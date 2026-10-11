"""异世界行记内容数据：稳定键、版本与被动数值口径。

资产来源：Project Amber / Yatta 当前默认数据（``weapon:14303``）。
被动「能量沐浴」：获得元素微粒或元素晶球时，恢复生命值（按精炼取最大生命比例）。
"""

from __future__ import annotations

OTHERWORLDLY_STORY_KEY_PREFIX = "weapon.otherworldly_story"
OTHERWORLDLY_STORY_HANDLER_KEY = OTHERWORLDLY_STORY_KEY_PREFIX
OTHERWORLDLY_STORY_PASSIVE_EFFECT_HANDLER_KEY = f"{OTHERWORLDLY_STORY_KEY_PREFIX}.passive"
OTHERWORLDLY_STORY_CONTENT_VERSION = "dev-otherworldly-story"

# 治疗命中键。
OTHERWORLDLY_STORY_HEAL_IMPACT_KEY = f"{OTHERWORLDLY_STORY_KEY_PREFIX}.heal"

# 资产效果参数的位置约定：components[0] 是治疗的最大生命值比例。
HEAL_RATIO_COMPONENT_INDEX = 0
