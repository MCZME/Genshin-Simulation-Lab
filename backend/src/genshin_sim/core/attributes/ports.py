"""属性解析的窄只读端口。

这里只定义属性系统在解析队伍作用域主体时需要向外部询问的最小问题，不引入
队伍、空间或 Buff 领域的具体对象。适配实现在装配层，未绑定时 provider 必须
返回空，因此属性运行时不需要重建。
"""

from __future__ import annotations

from typing import Protocol

from genshin_sim.core.attributes.models import AttributeSubjectRef


class TeamScopeProjectionPort(Protocol):
    """回答"角色主体归属于哪个队伍作用域，以及现在是否为当前场上角色"。

    `TEAM` 主体的词条投影到该队伍的全部角色；`ACTIVE_CHARACTER` 主体的词条
    只投影到当前场上角色。属性系统只消费这两个答案，不感知判断依据。
    """

    def team_scope_for(self, character_ref: AttributeSubjectRef) -> str | None:
        """返回角色主体所属队伍的作用域 id；未知角色返回 None。"""

        ...

    def is_active_character(self, character_ref: AttributeSubjectRef) -> bool:
        """返回该角色主体当前是否为场上角色；未知角色返回 False。"""

        ...
