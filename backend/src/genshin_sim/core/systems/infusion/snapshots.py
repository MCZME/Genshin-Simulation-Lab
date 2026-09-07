from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from genshin_sim.core.attributes import AttributeSubjectRef, RuntimeSourceRef
from genshin_sim.core.elements import AuraAmount, Element
from genshin_sim.core.systems.infusion.enums import (
    InfusionLifecycleState,
    InfusionMode,
    RefreshPolicy,
)
from genshin_sim.core.systems.infusion.models import (
    InfusionInstanceRef,
    InfusionRecord,
    runtime_source_ref_to_dict,
    subject_ref_to_dict,
    validate_frame,
)

if TYPE_CHECKING:
    from genshin_sim.core.systems.infusion.runtime import InfusionRuntime


@dataclass(frozen=True, slots=True)
class InfusionInstanceSnapshot:
    instance_ref: InfusionInstanceRef
    definition_key: str
    mechanic_key: str
    handler_key: str
    mode: InfusionMode
    element: Element
    weapon_gauge: AuraAmount
    remaining_gauge: AuraAmount
    frozen: bool
    character_ref: AttributeSubjectRef
    applier_ref: AttributeSubjectRef | None
    source_context: RuntimeSourceRef
    refresh_policy: RefreshPolicy
    created_frame: int
    last_applied_frame: int
    expires_at_frame: int
    next_refresh_frame: int | None
    lifecycle_state: InfusionLifecycleState

    @classmethod
    def from_record(cls, record: InfusionRecord) -> InfusionInstanceSnapshot:
        definition = record.definition
        return cls(
            instance_ref=record.instance_ref,
            definition_key=definition.definition_key,
            mechanic_key=definition.mechanic_key,
            handler_key=definition.handler_key,
            mode=record.mode,
            element=record.element,
            weapon_gauge=definition.weapon_gauge,
            remaining_gauge=record.remaining_gauge,
            frozen=record.frozen,
            character_ref=record.character_ref,
            applier_ref=record.applier_ref,
            source_context=record.source_context,
            refresh_policy=record.refresh_policy,
            created_frame=record.created_frame,
            last_applied_frame=record.last_applied_frame,
            expires_at_frame=record.expires_at_frame,
            next_refresh_frame=record.next_refresh_frame,
            lifecycle_state=record.lifecycle_state,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "instance_ref": self.instance_ref.to_dict(),
            "definition_key": self.definition_key,
            "mechanic_key": self.mechanic_key,
            "handler_key": self.handler_key,
            "mode": self.mode.value,
            "element": self.element.value,
            "weapon_gauge": self.weapon_gauge.to_dict(),
            "remaining_gauge": self.remaining_gauge.to_dict(),
            "frozen": self.frozen,
            "character_ref": subject_ref_to_dict(self.character_ref),
            "applier_ref": (
                None if self.applier_ref is None else subject_ref_to_dict(self.applier_ref)
            ),
            "source_context": runtime_source_ref_to_dict(self.source_context),
            "refresh_policy": self.refresh_policy.value,
            "created_frame": self.created_frame,
            "last_applied_frame": self.last_applied_frame,
            "expires_at_frame": self.expires_at_frame,
            "next_refresh_frame": self.next_refresh_frame,
            "lifecycle_state": self.lifecycle_state.value,
        }


@dataclass(frozen=True, slots=True)
class InfusionSnapshot:
    frame: int
    instances: tuple[InfusionInstanceSnapshot, ...]

    def __post_init__(self) -> None:
        validate_frame(self.frame)
        object.__setattr__(
            self,
            "instances",
            tuple(sorted(self.instances, key=lambda item: item.instance_ref)),
        )

    @classmethod
    def from_runtime(cls, runtime: InfusionRuntime, frame: int) -> InfusionSnapshot:
        validate_frame(frame)
        snapshots = []
        for record in runtime.infusion_store.records:
            if not record.is_active_at(frame):
                continue
            snapshots.append(InfusionInstanceSnapshot.from_record(record))
        return cls(frame=frame, instances=tuple(snapshots))

    def to_dict(self) -> dict[str, object]:
        return {"frame": self.frame, "instances": tuple(item.to_dict() for item in self.instances)}
