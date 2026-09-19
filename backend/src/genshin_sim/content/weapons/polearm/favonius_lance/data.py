"""西风长枪内容数据：稳定键与版本。

顺风而行的判定、参数解读与钩子实现落在 ``content/generic/favonius_windfall.py``；
本文件只声明本武器的内容级键。
"""

from __future__ import annotations

FAVONIUS_LANCE_HANDLER_KEY = "weapon.favonius_lance"
FAVONIUS_LANCE_CONTENT_VERSION = "dev-favonius-lance"

# 效果行 ``weapon:13407:passive:113407`` 的绑定键。行为实现落在武器内容单元上
# （效果通道不携带精炼等级），该效果行因此按空实现注册。
FAVONIUS_LANCE_PASSIVE_EFFECT_HANDLER_KEY = "weapon.favonius_lance.passive"

FAVONIUS_LANCE_WINDFALL_IMPACT_KEY = "weapon.favonius_lance.windfall"
