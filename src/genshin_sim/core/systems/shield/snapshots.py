from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from genshin_sim.core.attributes import AttributeSubjectRef, RuntimeSourceRef
from genshin_sim.core.systems.shield.enums import ShieldElement
from genshin_sim.core.systems.shield.models import (
    ShieldProtectionRef,
    validate_frame,
)

if TYPE_CHECKING:
    from genshin_sim.core.systems.shield.runtime import ShieldRuntime


@dataclass(frozen=True, slots=True)
class ShieldInstanceSnapshot:
    instance_id: int
    mechanic_key: str
    protection_ref: ShieldProtectionRef
    creator_ref: AttributeSubjectRef
    source_context: RuntimeSourceRef
    element: ShieldElement
    maximum_native_absorption: float
    remaining_native_absorption: float
    created_frame: int
    expires_at_frame: int
    tags: frozenset[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "instance_id": self.instance_id,
            "mechanic_key": self.mechanic_key,
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
            self,
            "instances",
            tuple(sorted(self.instances, key=lambda item: item.instance_id)),
        )

    @classmethod
    def from_runtime(cls, runtime: ShieldRuntime, frame: int) -> ShieldSnapshot:
        validate_frame(frame)
        snapshots = []
        for component in runtime.component_store.components:
            instance = runtime.mechanic_runtime.instance_store.require(component.instance_id)
            if not instance.is_active_at(frame):
                continue
            snapshots.append(
                ShieldInstanceSnapshot(
                    instance_id=component.instance_id,
                    mechanic_key=component.mechanic_key,
                    protection_ref=component.protection_ref,
                    creator_ref=component.creator_ref,
                    source_context=component.source_context,
                    element=component.element,
                    maximum_native_absorption=component.maximum_native_absorption,
                    remaining_native_absorption=component.remaining_native_absorption,
                    created_frame=instance.created_frame,
                    expires_at_frame=instance.expires_at_frame,
                    tags=component.tags,
                )
            )
        return cls(frame=frame, instances=tuple(snapshots))

    def to_dict(self) -> dict[str, object]:
        return {
            "frame": self.frame,
            "instances": tuple(item.to_dict() for item in self.instances),
        }


def _subject_ref_to_dict(ref: AttributeSubjectRef) -> dict[str, str]:
    return {"kind": ref.kind.value, "entity_id": ref.entity_id}


def _runtime_source_ref_to_dict(ref: RuntimeSourceRef) -> dict[str, str | None]:
    return {
        "kind": ref.kind.value,
        "source_key": ref.source_key,
        "instance_id": ref.instance_id,
    }
