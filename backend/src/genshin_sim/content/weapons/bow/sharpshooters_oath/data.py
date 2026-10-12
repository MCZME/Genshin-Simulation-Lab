"""神射手之誓内容数据：稳定键与版本。

范围边界：「针对要害造成的伤害提升」依赖命中部位判定，仿真不建模弱点（D-095），
本包被动按 no-op 处理并在此记录；接入部位判定后重写本包。
"""

from __future__ import annotations

SHARPSHOOTERS_OATH_KEY_PREFIX = "weapon.sharpshooters_oath"
SHARPSHOOTERS_OATH_HANDLER_KEY = SHARPSHOOTERS_OATH_KEY_PREFIX
SHARPSHOOTERS_OATH_PASSIVE_EFFECT_HANDLER_KEY = f"{SHARPSHOOTERS_OATH_KEY_PREFIX}.passive"
SHARPSHOOTERS_OATH_CONTENT_VERSION = "dev-sharpshooters-oath"
