from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EntityLifecycleState(StrEnum):
    """运行时实体的基础生命周期状态。"""

    ACTIVE = "active"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class EntityLifecycle:
    """实体身份共享的生命周期信息。

    这里仅描述实体是否存在；生命值、击败、死亡和其他战斗状态归属后续机制或系统。
    """

    created_frame: int = 0
    expires_at_frame: int | None = None
    state: EntityLifecycleState = EntityLifecycleState.ACTIVE

    def __post_init__(self) -> None:
        if self.created_frame < 0:
            msg = "实体创建帧不能为负数"
            raise ValueError(msg)
        if self.expires_at_frame is not None and self.expires_at_frame <= self.created_frame:
            msg = "实体过期帧必须晚于创建帧"
            raise ValueError(msg)

    def is_active_at(self, frame: int) -> bool:
        if frame < 0:
            msg = "帧号不能为负数"
            raise ValueError(msg)
        if self.state is not EntityLifecycleState.ACTIVE:
            return False
        if frame < self.created_frame:
            return False
        return self.expires_at_frame is None or frame < self.expires_at_frame

    def to_dict(self) -> dict[str, object]:
        return {
            "created_frame": self.created_frame,
            "expires_at_frame": self.expires_at_frame,
            "state": self.state.value,
        }

    def expired(self) -> EntityLifecycle:
        """返回终结后的生命周期值，不修改已共享的原值。"""

        if self.state is EntityLifecycleState.EXPIRED:
            return self
        return EntityLifecycle(
            created_frame=self.created_frame,
            expires_at_frame=self.expires_at_frame,
            state=EntityLifecycleState.EXPIRED,
        )
