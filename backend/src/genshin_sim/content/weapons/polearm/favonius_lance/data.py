from __future__ import annotations

FAVONIUS_LANCE_HANDLER_KEY = "weapon.favonius_lance"
FAVONIUS_LANCE_CONTENT_VERSION = "dev-favonius-lance"

# 效果行 ``weapon:13407:passive:113407`` 的绑定键。行为实现落在武器内容单元上
# （效果通道不携带精炼等级），该效果行因此按空实现注册。
FAVONIUS_LANCE_PASSIVE_EFFECT_HANDLER_KEY = "weapon.favonius_lance.passive"

FAVONIUS_LANCE_WINDFALL_IMPACT_KEY = "weapon.favonius_lance.windfall"

# 本包声明的帧率基准：资产效果参数以秒记录时间，运行态以帧推进。
FRAMES_PER_SECOND = 60

# 产球形态：3 个无元素微粒。资产效果参数不含数量与元素，由本包声明。
FAVONIUS_LANCE_PICKUP_KIND = "particle"
FAVONIUS_LANCE_PICKUP_ELEMENT = "clear"
FAVONIUS_LANCE_PARTICLE_COUNT = 3

# 载体延迟抽样区间（闭区间，工程约定）。
FAVONIUS_LANCE_TRAVEL_FRAMES_MIN = 20
FAVONIUS_LANCE_TRAVEL_FRAMES_MAX = 50
