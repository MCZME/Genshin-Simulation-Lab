"""游戏规则默认面板的基础属性值。"""

from __future__ import annotations

from genshin_sim.core.attributes.keys import (
    STAT_CRIT_DAMAGE,
    STAT_CRIT_RATE,
    STAT_ENERGY_RECHARGE,
    AttributeKey,
)
from genshin_sim.core.attributes.models import RuntimeSourceKind, RuntimeSourceRef

# 每个角色都具备的基础面板值（游戏规则，非资产数据）。
GAME_BASE_CRIT_RATE = 0.05
GAME_BASE_CRIT_DAMAGE = 0.5
GAME_BASE_ENERGY_RECHARGE = 1.0

# 角色主体按此表获得基础面板贡献，顺序即注入顺序。
GAME_BASE_CHARACTER_PANEL: tuple[tuple[AttributeKey, float], ...] = (
    (STAT_CRIT_RATE, GAME_BASE_CRIT_RATE),
    (STAT_CRIT_DAMAGE, GAME_BASE_CRIT_DAMAGE),
    (STAT_ENERGY_RECHARGE, GAME_BASE_ENERGY_RECHARGE),
)


def game_base_panel_source_ref(attribute_key: AttributeKey) -> RuntimeSourceRef:
    """返回基础面板值的来源引用，便于在属性来源链中署名。"""

    return RuntimeSourceRef(RuntimeSourceKind.SYSTEM, f"base.{attribute_key}")
