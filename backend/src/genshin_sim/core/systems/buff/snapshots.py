from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from genshin_sim.core.attributes import AttributeSubjectRef, RuntimeSourceRef
from genshin_sim.core.systems.buff.models import (
    BuffInstanceRef,
    BuffRecord,
    BuffResolvedAttributeModifier,
    validate_frame,
)

if TYPE_CHECKING:
    from genshin_sim.core.systems.buff.runtime import BuffRuntime


@dataclass(frozen=True, slots=True)
class BuffInstanceSnapshot:
    instance_ref: BuffInstanceRef
    definition_key: str
    mechanic_key: str
    handler_key: str
    conflict_key: str
    target_ref: AttributeSubjectRef
    applier_ref: AttributeSubjectRef | None
    source_context: RuntimeSourceRef
    stack_count: int
    max_stacks: int
    resolved_modifiers: tuple[BuffResolvedAttributeModifier, ...]
    created_frame: int
    last_applied_frame: int
    expires_at_frame: int
    tags: frozenset[str]
    # Buff 显示名：内容层提供，只进入展示投影，不作为身份或冲突依据。
    display_name: str | None = None

    @classmethod
    def from_record(cls, record: BuffRecord) -> BuffInstanceSnapshot:
        state = record.state
        definition = record.definition
        return cls(
            instance_ref=record.instance_ref,
            definition_key=definition.definition_key,
            mechanic_key=definition.mechanic_key,
            handler_key=definition.handler_key,
            conflict_key=definition.conflict_key,
            target_ref=state.target_ref,
            applier_ref=state.applier_ref,
            source_context=state.source_context,
            stack_count=state.stack_count,
            max_stacks=state.max_stacks,
            resolved_modifiers=state.resolved_modifiers,
            created_frame=record.created_frame,
            last_applied_frame=record.last_applied_frame,
            expires_at_frame=record.expires_at_frame,
            tags=state.tags,
            display_name=definition.display_name,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "instance_ref": self.instance_ref.to_dict(),
            "definition_key": self.definition_key,
            "mechanic_key": self.mechanic_key,
            "handler_key": self.handler_key,
            "conflict_key": self.conflict_key,
            "display_name": self.display_name,
            "target_ref": _subject_ref_to_dict(self.target_ref),
            "applier_ref": (
                None if self.applier_ref is None else _subject_ref_to_dict(self.applier_ref)
            ),
            "source_context": _runtime_source_ref_to_dict(self.source_context),
            "stack_count": self.stack_count,
            "max_stacks": self.max_stacks,
            "resolved_modifiers": tuple(item.to_dict() for item in self.resolved_modifiers),
            "created_frame": self.created_frame,
            "last_applied_frame": self.last_applied_frame,
            "expires_at_frame": self.expires_at_frame,
            "tags": tuple(sorted(self.tags)),
        }


@dataclass(frozen=True, slots=True)
class BuffSnapshot:
    frame: int
    instances: tuple[BuffInstanceSnapshot, ...]

    def __post_init__(self) -> None:
        validate_frame(self.frame)
        object.__setattr__(
            self,
            "instances",
            tuple(sorted(self.instances, key=lambda item: item.instance_ref)),
        )

    @classmethod
    def from_runtime(cls, runtime: BuffRuntime, frame: int) -> BuffSnapshot:
        validate_frame(frame)
        snapshots = []
        for record in runtime.buff_store.records:
            if not record.is_active_at(frame):
                continue
            snapshots.append(BuffInstanceSnapshot.from_record(record))
        return cls(frame=frame, instances=tuple(snapshots))

    def to_dict(self) -> dict[str, object]:
        return {"frame": self.frame, "instances": tuple(item.to_dict() for item in self.instances)}


def _subject_ref_to_dict(ref: AttributeSubjectRef) -> dict[str, str]:
    return {"kind": ref.kind.value, "entity_id": ref.entity_id}


def _runtime_source_ref_to_dict(ref: RuntimeSourceRef) -> dict[str, str | None]:
    return {"kind": ref.kind.value, "source_key": ref.source_key, "instance_id": ref.instance_id}
