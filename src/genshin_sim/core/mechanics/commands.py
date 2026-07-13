from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.core.mechanics.errors import MechanicValidationError
from genshin_sim.core.mechanics.models import (
    validate_frame,
    validate_non_empty_text,
    validate_positive_int,
)


@dataclass(frozen=True, slots=True)
class CreateMechanicInstanceCommand:
    capability_key: str
    mechanic_key: str
    handler_key: str
    owner_ref: str
    frame: int
    duration_frames: int

    def __post_init__(self) -> None:
        validate_non_empty_text(self.capability_key, "capability_key")
        validate_non_empty_text(self.mechanic_key, "mechanic_key")
        validate_non_empty_text(self.handler_key, "handler_key")
        validate_non_empty_text(self.owner_ref, "owner_ref")
        validate_frame(self.frame)
        validate_positive_int(self.duration_frames, "duration_frames")

    @property
    def expires_at_frame(self) -> int:
        return self.frame + self.duration_frames


@dataclass(frozen=True, slots=True)
class RefreshMechanicExpiryCommand:
    instance_id: int
    frame: int
    expires_at_frame: int

    def __post_init__(self) -> None:
        validate_positive_int(self.instance_id, "instance_id")
        validate_frame(self.frame)
        validate_frame(self.expires_at_frame, "expires_at_frame")
        if self.expires_at_frame <= self.frame:
            raise MechanicValidationError("expires_at_frame 必须晚于刷新执行帧")


@dataclass(frozen=True, slots=True)
class RemoveMechanicInstanceCommand:
    instance_id: int
    frame: int
    reason: str

    def __post_init__(self) -> None:
        validate_positive_int(self.instance_id, "instance_id")
        validate_frame(self.frame)
        validate_non_empty_text(self.reason, "reason")
