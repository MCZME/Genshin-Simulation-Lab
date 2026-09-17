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
    """查询目标在指定帧是否持有某个已提交的 Buff 实例。

    面向内容侧条件效果（武器、圣遗物等）的窄只读端口：只回答存在性，
    不暴露 Buff 实例细节，也不允许任何写入。
    """

    def has_buff(
        self,
        *,
        target_ref: AttributeSubjectRef,
        definition_key: str,
        frame: int,
    ) -> bool: ...
