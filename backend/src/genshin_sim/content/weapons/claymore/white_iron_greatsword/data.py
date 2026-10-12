"""白铁大剑内容数据：稳定键与版本。

范围边界：「击败敌人时恢复生命值」依赖敌人生命与击败事实，仿真不建模敌人
死亡（D-095），本包被动按 no-op 处理并在此记录；接入敌人模型后重写本包。
"""

from __future__ import annotations

WHITE_IRON_GREATSWORD_KEY_PREFIX = "weapon.white_iron_greatsword"
WHITE_IRON_GREATSWORD_HANDLER_KEY = WHITE_IRON_GREATSWORD_KEY_PREFIX
WHITE_IRON_GREATSWORD_PASSIVE_EFFECT_HANDLER_KEY = f"{WHITE_IRON_GREATSWORD_KEY_PREFIX}.passive"
WHITE_IRON_GREATSWORD_CONTENT_VERSION = "dev-white-iron-greatsword"
