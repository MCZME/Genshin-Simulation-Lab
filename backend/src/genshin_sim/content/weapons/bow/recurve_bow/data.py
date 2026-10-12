"""反曲弓内容数据：稳定键与版本。

范围边界：「击败敌人时恢复生命值」依赖敌人生命与击败事实，仿真不建模敌人
死亡（D-095），本包被动按 no-op 处理并在此记录；接入敌人模型后重写本包。
"""

from __future__ import annotations

RECURVE_BOW_KEY_PREFIX = "weapon.recurve_bow"
RECURVE_BOW_HANDLER_KEY = RECURVE_BOW_KEY_PREFIX
RECURVE_BOW_PASSIVE_EFFECT_HANDLER_KEY = f"{RECURVE_BOW_KEY_PREFIX}.passive"
RECURVE_BOW_CONTENT_VERSION = "dev-recurve-bow"
