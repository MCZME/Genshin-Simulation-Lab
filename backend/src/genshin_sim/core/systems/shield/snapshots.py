from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from genshin_sim.core.attributes import AttributeSubjectRef, RuntimeSourceRef
from genshin_sim.core.systems.shield.enums import ShieldElement
from genshin_sim.core.systems.shield.models import (
    ShieldInstanceRef,
    ShieldProtectionRef,
    ShieldRecord,
    validate_frame,
)

if TYPE_CHECKING:
    from genshin_sim.core.systems.shield.runtime import ShieldRuntime


@dataclass(frozen=True, slots=True)
class ShieldInstanceSnapshot:
    instance_ref: ShieldInstanceRef
    mechanic_key: str
    handler_key: str
    protection_ref: ShieldProtectionRef
    creator_ref: AttributeSubjectRef
    source_context: RuntimeSourceRef
    element: ShieldElement
    maximum_native_absorption: float
    remaining_native_absorption: float
    created_frame: int
    expires_at_frame: int
    tags: frozenset[str]

    @classmethod
    def from_record(cls, record: ShieldRecord) -> ShieldInstanceSnapshot:
        state = record.state
        return cls(
            instance_ref=record.instance_ref,
            mechanic_key=record.mechanic_key,
            handler_key=record.handler_key,
            protection_ref=state.protection_ref,
            creator_ref=state.creator_ref,
            source_context=state.source_context,
            element=state.element,
            maximum_native_absorption=state.maximum_native_absorption,
            remaining_native_absorption=state.remaining_native_absorption,
            created_frame=record.created_frame,
            expires_at_frame=record.expires_at_frame,
            tags=state.tags,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "instance_ref": self.instance_ref.to_dict(),
            "mechanic_key": self.mechanic_key,
            "handler_key": self.handler_key,
            "protection_ref": self.protection_ref.to_dict(),
            "creator_ref": _subject_ref_to_dict(self.creator_ref),
            "source_context": _runtime_source_ref_to_dict(self.source_context),
            "element": self.element.value,
            "maximum_native_absorption": self.maximum_native_absorption,
            "remaining_native_absorption": self.remaining_native_absorption,
            "created_frame": self.created_frame,
            "expires_at_frame": self.expires_at_frame,
            "tags": tuple(sorted(self.tags)),
        }


@dataclass(frozen=True, slots=True)
class ShieldSnapshot:
    frame: int
    instances: tuple[ShieldInstanceSnapshot, ...]

    def __post_init__(self) -> None:
        validate_frame(self.frame)
        object.__setattr__(
            self, "instances", tuple(sorted(self.instances, key=lambda item: item.instance_ref))
        )

    @classmethod
    def from_runtime(cls, runtime: ShieldRuntime, frame: int) -> ShieldSnapshot:
        validate_frame(frame)
        snapshots = []
        for record in runtime.shield_store.records:
            if not record.is_active_at(frame):
                continue
            snapshots.append(ShieldInstanceSnapshot.from_record(record))
        return cls(frame=frame, instances=tuple(snapshots))

    def to_dict(self) -> dict[str, object]:
        return {"frame": self.frame, "instances": tuple(item.to_dict() for item in self.instances)}


def _subject_ref_to_dict(ref: AttributeSubjectRef) -> dict[str, str]:
    return {"kind": ref.kind.value, "entity_id": ref.entity_id}


def _runtime_source_ref_to_dict(ref: RuntimeSourceRef) -> dict[str, str | None]:
    return {"kind": ref.kind.value, "source_key": ref.source_key, "instance_id": ref.instance_id}
