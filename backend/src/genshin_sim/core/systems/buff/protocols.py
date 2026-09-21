from __future__ import annotations

from typing import Protocol

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.systems.buff.models import BuffRecord


class BuffReader(Protocol):
    def active(
        self,
        frame: int,
        target_ref: AttributeSubjectRef | None = None,
        definition_key: str | None = None,
        mechanic_key: str | None = None,
    ) -> tuple[BuffRecord, ...]: ...


class TargetBuffPresenceReadPort(Protocol):
    """查询目标在指定帧的 Buff 存在性与活动层数。

    面向内容侧条件效果（武器、圣遗物等）的窄只读端口：只回答存在性与层数，
    不暴露 Buff 实例细节，也不允许任何写入。
    """

    def has_buff(
        self,
        *,
        target_ref: AttributeSubjectRef,
        definition_key: str,
        frame: int,
    ) -> bool: ...

    def active_stack_count(
        self,
        *,
        target_ref: AttributeSubjectRef,
        definition_key: str,
        frame: int,
    ) -> int: ...
