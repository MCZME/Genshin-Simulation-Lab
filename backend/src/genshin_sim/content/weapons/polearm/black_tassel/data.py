"""黑缨枪内容数据：稳定键与版本。

范围边界：「对史莱姆类敌人造成的伤害增加」依赖敌人分类，仿真不建模敌人分类
（D-095），本包被动按 no-op 处理并在此记录；接入敌人分类后重写本包。
"""

from __future__ import annotations

BLACK_TASSEL_KEY_PREFIX = "weapon.black_tassel"
BLACK_TASSEL_HANDLER_KEY = BLACK_TASSEL_KEY_PREFIX
BLACK_TASSEL_PASSIVE_EFFECT_HANDLER_KEY = f"{BLACK_TASSEL_KEY_PREFIX}.passive"
BLACK_TASSEL_CONTENT_VERSION = "dev-black-tassel"
