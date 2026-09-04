"""月兆领域窄只读协议。"""

from __future__ import annotations

from typing import Protocol

from genshin_sim.core.systems.moonsign.models import MoonsignLevel


class LunarDamageBonusPort(Protocol):
    """向月曜伤害捕获提供当前非月兆月曜增伤（小数倍率）。"""

    def lunar_reaction_bonus(self, frame: int) -> float: ...


class MoonsignLevelReadPort(Protocol):
    """向角色内容提供月兆等级只读查询。"""

    @property
    def level(self) -> MoonsignLevel: ...
