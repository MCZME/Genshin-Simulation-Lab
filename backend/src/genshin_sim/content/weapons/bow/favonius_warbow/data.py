"""西风猎弓内容数据：稳定键与版本。

顺风而行的判定、参数解读与钩子实现落在 ``content/generic/favonius_windfall.py``；
本文件只声明本武器的内容级键。
"""

from __future__ import annotations

FAVONIUS_WARBOW_HANDLER_KEY = "weapon.favonius_warbow"
FAVONIUS_WARBOW_CONTENT_VERSION = "dev-favonius-series"

# 效果行 ``weapon:15401:passive:115401`` 的绑定键。行为实现落在武器内容单元上
# （效果通道不携带精炼等级），该效果行因此按空实现注册。
FAVONIUS_WARBOW_PASSIVE_EFFECT_HANDLER_KEY = "weapon.favonius_warbow.passive"

FAVONIUS_WARBOW_WINDFALL_IMPACT_KEY = "weapon.favonius_warbow.windfall"
