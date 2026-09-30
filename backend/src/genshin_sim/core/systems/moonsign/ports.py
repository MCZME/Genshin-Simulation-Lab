"""月兆领域窄只读协议。"""

from __future__ import annotations

from typing import Protocol

from genshin_sim.core.systems.moonsign.models import MoonsignLevel


class LunarDamageBonusPort(Protocol):
    """向月曜伤害修饰 provider 提供当前非月兆月曜增伤（小数倍率）。

    只读、只暴露一个标量：增伤的来源角色与到期帧由 ``MOONSIGN_BONUS_APPLIED`` /
    ``MOONSIGN_BONUS_EXPIRED`` 事实与快照承载，provider 不重复读取。
    """

    def lunar_reaction_bonus(self, frame: int) -> float: ...


class MoonsignLevelReadPort(Protocol):
    """向角色内容提供月兆等级只读查询。"""

    @property
    def level(self) -> MoonsignLevel: ...
