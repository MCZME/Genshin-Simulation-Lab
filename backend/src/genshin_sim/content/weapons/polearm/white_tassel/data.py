"""白缨枪内容数据：稳定键、版本与被动数值口径。

资产来源：Project Amber / Yatta 当前默认数据（``weapon:13301``）。
被动「锐利」：普通攻击造成的伤害提升（按精炼取值）。
"""

from __future__ import annotations

WHITE_TASSEL_KEY_PREFIX = "weapon.white_tassel"
WHITE_TASSEL_HANDLER_KEY = WHITE_TASSEL_KEY_PREFIX
WHITE_TASSEL_PASSIVE_EFFECT_HANDLER_KEY = f"{WHITE_TASSEL_KEY_PREFIX}.passive"
WHITE_TASSEL_CONTENT_VERSION = "dev-white-tassel"

# 被动主攻击标签：普通攻击。
WHITE_TASSEL_ATTACK_TAG = "普通攻击"

# 资产效果参数的位置约定：components[0] 是普通攻击伤害加成。
WHITE_TASSEL_BONUS_COMPONENT_INDEX = 0
