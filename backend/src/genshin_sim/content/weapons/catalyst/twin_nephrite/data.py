"""甲级宝珏内容数据：稳定键与版本。

范围边界：「击败敌人后一段时间内提升攻击力与移动速度」依赖敌人击败事实，
且移动速度没有属性语义，仿真不建模敌人死亡（D-095），本包被动按 no-op 处理
并在此记录；接入敌人模型后重写本包。
"""

from __future__ import annotations

TWIN_NEPHRITE_KEY_PREFIX = "weapon.twin_nephrite"
TWIN_NEPHRITE_HANDLER_KEY = TWIN_NEPHRITE_KEY_PREFIX
TWIN_NEPHRITE_PASSIVE_EFFECT_HANDLER_KEY = f"{TWIN_NEPHRITE_KEY_PREFIX}.passive"
TWIN_NEPHRITE_CONTENT_VERSION = "dev-twin-nephrite"
