"""跨机制聚合的反应族键集合。

与各 mechanic 目录下的 ``keys.py`` 区分：那里定义单个反应的稳定键，这里定义
「同属一个游戏机制族」的反应集合，供核心与内容侧的条件效果判定共用。

新增星烁反应机制时只需在此登记一次，内容侧不必各自维护集合副本。
"""

from __future__ import annotations

from genshin_sim.core.systems.reaction.mechanics.stellar_conduct.keys import (
    STELLAR_CONDUCT_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.stellar_swirl.keys import (
    STELLAR_SWIRL_REACTION_KEY,
)

# 星烁反应族：星超导与星扩散。
STELLAR_REACTION_KEYS = frozenset(
    {
        STELLAR_CONDUCT_REACTION_KEY,
        STELLAR_SWIRL_REACTION_KEY,
    }
)
