from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from genshin_sim.core.mechanics.errors import MechanicValidationError


class MechanicLifecycleState(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REMOVED = "removed"


def validate_frame(frame: int, field_name: str = "frame") -> None:
    if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
        raise MechanicValidationError(f"{field_name} 必须是非负整数")


def validate_positive_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise MechanicValidationError(f"{field_name} 必须是正整数")


def validate_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise MechanicValidationError(f"{field_name} 必须是非空字符串")


@dataclass(frozen=True, slots=True)
class MechanicInstance:
    """带稳定身份、所有权和生命周期的最小机制实例。"""

    instance_id: int
    capability_key: str
    mechanic_key: str
    handler_key: str
    owner_ref: str
    created_frame: int
    expires_at_frame: int
    lifecycle_state: MechanicLifecycleState = MechanicLifecycleState.ACTIVE
    removed_frame: int | None = None
    removal_reason: str | None = None

    def __post_init__(self) -> None:
        validate_positive_int(self.instance_id, "instance_id")
        validate_non_empty_text(self.capability_key, "capability_key")
        validate_non_empty_text(self.mechanic_key, "mechanic_key")
        validate_non_empty_text(self.handler_key, "handler_key")
        validate_non_empty_text(self.owner_ref, "owner_ref")
        validate_frame(self.created_frame, "created_frame")
        validate_frame(self.expires_at_frame, "expires_at_frame")
        if self.created_frame >= self.expires_at_frame:
            raise MechanicValidationError("created_frame 必须早于 expires_at_frame")
        if not isinstance(self.lifecycle_state, MechanicLifecycleState):
            raise MechanicValidationError("lifecycle_state 不受支持")
        if self.lifecycle_state is MechanicLifecycleState.ACTIVE:
            if self.removed_frame is not None or self.removal_reason is not None:
                raise MechanicValidationError("活动实例不能携带移除信息")
        else:
            if self.removed_frame is None:
                raise MechanicValidationError("非活动实例必须携带 removed_frame")
            validate_frame(self.removed_frame, "removed_frame")
            if self.removal_reason is None:
                raise MechanicValidationError("非活动实例必须携带 removal_reason")
            validate_non_empty_text(self.removal_reason, "removal_reason")
            if self.lifecycle_state is MechanicLifecycleState.EXPIRED:
                if self.removed_frame < self.expires_at_frame:
                    raise MechanicValidationError("过期实例不能早于 expires_at_frame 移除")
            elif not self.created_frame <= self.removed_frame < self.expires_at_frame:
                raise MechanicValidationError("显式移除帧必须位于实例活动区间")

    def is_active_at(self, frame: int) -> bool:
        validate_frame(frame)
        return (
            self.lifecycle_state is MechanicLifecycleState.ACTIVE
            and self.created_frame <= frame < self.expires_at_frame
        )

    def with_expiry(self, expires_at_frame: int) -> MechanicInstance:
        validate_frame(expires_at_frame, "expires_at_frame")
        if expires_at_frame <= self.created_frame:
            raise MechanicValidationError("expires_at_frame 必须晚于 created_frame")
        if self.lifecycle_state is not MechanicLifecycleState.ACTIVE:
            raise MechanicValidationError("只有活动实例可以刷新过期帧")
        return replace(self, expires_at_frame=expires_at_frame)

    def mark_removed(
        self,
        *,
        frame: int,
        reason: str,
        state: MechanicLifecycleState = MechanicLifecycleState.REMOVED,
    ) -> MechanicInstance:
        validate_frame(frame)
        validate_non_empty_text(reason, "removal_reason")
        if state is MechanicLifecycleState.ACTIVE:
            raise MechanicValidationError("移除状态不能是 active")
        if self.lifecycle_state is not MechanicLifecycleState.ACTIVE:
            raise MechanicValidationError("实例已不处于活动状态")
        if state is MechanicLifecycleState.EXPIRED:
            if frame < self.expires_at_frame:
                raise MechanicValidationError("实例尚未到期")
        elif not self.is_active_at(frame):
            raise MechanicValidationError("显式移除帧必须位于实例活动区间")
        return replace(
            self,
            lifecycle_state=state,
            removed_frame=frame,
            removal_reason=reason,
        )


@dataclass(frozen=True, slots=True)
class MechanicRemovalRecord:
    frame: int
    instance: MechanicInstance
    reason: str

    def __post_init__(self) -> None:
        validate_frame(self.frame)
        if not isinstance(self.instance, MechanicInstance):
            raise MechanicValidationError("instance 必须是 MechanicInstance")
        validate_non_empty_text(self.reason, "reason")

    @property
    def instance_id(self) -> int:
        return self.instance.instance_id
