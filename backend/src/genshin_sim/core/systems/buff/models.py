from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from genshin_sim.core.attributes import (
    AttributeSubjectKind,
    AttributeSubjectRef,
    RuntimeSourceRef,
)
from genshin_sim.core.systems.buff.definitions import (
    BuffAttributeModifierTemplate,
    BuffDefinition,
    normalize_tags,
    validate_non_empty_text,
    validate_non_negative_int,
    validate_positive_int,
)
from genshin_sim.core.systems.buff.enums import (
    BuffApplicationOutcome,
    BuffLifecycleState,
    BuffRemovalReason,
)

if TYPE_CHECKING:
    from genshin_sim.core.systems.buff.snapshots import BuffInstanceSnapshot
from genshin_sim.core.systems.buff.errors import BuffValidationError


def validate_finite_number(value: float | int, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise BuffValidationError(f"{field_name} 必须是数字")
    result = float(value)
    if not math.isfinite(result):
        raise BuffValidationError(f"{field_name} 必须是有限数字")
    return result


def validate_frame(frame: int, field_name: str = "frame") -> None:
    validate_non_negative_int(frame, field_name)


def validate_subject_ref(ref: AttributeSubjectRef, field_name: str) -> None:
    if not isinstance(ref, AttributeSubjectRef):
        raise BuffValidationError(f"{field_name} 必须是 AttributeSubjectRef")
    if ref.kind not in {AttributeSubjectKind.CHARACTER, AttributeSubjectKind.TARGET}:
        raise BuffValidationError(f"{field_name} 只支持角色或目标主体")


def subject_ref_to_dict(ref: AttributeSubjectRef) -> dict[str, str]:
    return {"kind": ref.kind.value, "entity_id": ref.entity_id}


def runtime_source_ref_to_dict(ref: RuntimeSourceRef) -> dict[str, str | None]:
    return {"kind": ref.kind.value, "source_key": ref.source_key, "instance_id": ref.instance_id}


@dataclass(frozen=True, order=True, slots=True)
class BuffInstanceRef:
    sequence: int
    domain_key: str = "buff"

    def __post_init__(self) -> None:
        validate_positive_int(self.sequence, "sequence")
        if self.domain_key != "buff":
            raise BuffValidationError("BuffInstanceRef.domain_key 必须是 buff")

    def to_key(self) -> str:
        return f"{self.domain_key}:{self.sequence}"

    def to_dict(self) -> dict[str, object]:
        return {"domain_key": self.domain_key, "sequence": self.sequence}

    def __str__(self) -> str:
        return self.to_key()


@dataclass(frozen=True, slots=True)
class BuffModifierValue:
    term_key: str
    value: float

    def __post_init__(self) -> None:
        validate_non_empty_text(self.term_key, "term_key")
        object.__setattr__(self, "value", validate_finite_number(self.value, "modifier value"))

    def to_dict(self) -> dict[str, object]:
        return {"term_key": self.term_key, "value": self.value}


@dataclass(frozen=True, slots=True)
class ApplyBuffRequest:
    request_id: str
    frame: int
    order: int
    definition_key: str
    target_ref: AttributeSubjectRef
    source_context: RuntimeSourceRef
    duration_frames: int
    stack_delta: int = 1
    modifier_values: tuple[BuffModifierValue, ...] = ()
    applier_ref: AttributeSubjectRef | None = None

    def __post_init__(self) -> None:
        validate_non_empty_text(self.request_id, "request_id")
        validate_non_empty_text(self.definition_key, "definition_key")
        validate_frame(self.frame)
        validate_non_negative_int(self.order, "order")
        validate_subject_ref(self.target_ref, "target_ref")
        if not isinstance(self.source_context, RuntimeSourceRef):
            raise BuffValidationError("source_context 必须是 RuntimeSourceRef")
        if self.applier_ref is not None:
            validate_subject_ref(self.applier_ref, "applier_ref")
        validate_positive_int(self.duration_frames, "duration_frames")
        validate_positive_int(self.stack_delta, "stack_delta")
        values = tuple(sorted(self.modifier_values, key=lambda item: item.term_key))
        keys = [value.term_key for value in values]
        if len(keys) != len(set(keys)):
            raise BuffValidationError(
                f"ApplyBuffRequest {self.request_id!r} modifier term_key 重复"
            )
        object.__setattr__(self, "modifier_values", values)


@dataclass(frozen=True, slots=True)
class BuffResolvedAttributeModifier:
    template: BuffAttributeModifierTemplate
    value: float

    def __post_init__(self) -> None:
        if not isinstance(self.template, BuffAttributeModifierTemplate):
            raise BuffValidationError("template 必须是 BuffAttributeModifierTemplate")
        object.__setattr__(self, "value", validate_finite_number(self.value, "resolved value"))

    @property
    def term_key(self) -> str:
        return self.template.term_key

    def to_dict(self) -> dict[str, object]:
        return {"template": self.template.to_dict(), "value": self.value}


@dataclass(frozen=True, slots=True)
class BuffState:
    target_ref: AttributeSubjectRef
    applier_ref: AttributeSubjectRef | None
    source_context: RuntimeSourceRef
    stack_count: int
    max_stacks: int
    resolved_modifiers: tuple[BuffResolvedAttributeModifier, ...] = ()
    tags: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        validate_subject_ref(self.target_ref, "target_ref")
        if self.applier_ref is not None:
            validate_subject_ref(self.applier_ref, "applier_ref")
        if not isinstance(self.source_context, RuntimeSourceRef):
            raise BuffValidationError("source_context 必须是 RuntimeSourceRef")
        validate_positive_int(self.stack_count, "stack_count")
        validate_positive_int(self.max_stacks, "max_stacks")
        if self.stack_count > self.max_stacks:
            raise BuffValidationError("stack_count 不能大于 max_stacks")
        object.__setattr__(self, "resolved_modifiers", tuple(self.resolved_modifiers))
        object.__setattr__(self, "tags", normalize_tags(self.tags, "buff state tags"))

    def to_dict(self) -> dict[str, object]:
        return {
            "target_ref": subject_ref_to_dict(self.target_ref),
            "applier_ref": (
                None if self.applier_ref is None else subject_ref_to_dict(self.applier_ref)
            ),
            "source_context": runtime_source_ref_to_dict(self.source_context),
            "stack_count": self.stack_count,
            "max_stacks": self.max_stacks,
            "resolved_modifiers": tuple(item.to_dict() for item in self.resolved_modifiers),
            "tags": tuple(sorted(self.tags)),
        }


@dataclass(frozen=True, slots=True)
class BuffRecord:
    instance_ref: BuffInstanceRef
    definition: BuffDefinition
    created_frame: int
    last_applied_frame: int
    expires_at_frame: int
    lifecycle_state: BuffLifecycleState
    state: BuffState
    removed_frame: int | None = None
    removal_reason: BuffRemovalReason | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.instance_ref, BuffInstanceRef):
            raise BuffValidationError("instance_ref 必须是 BuffInstanceRef")
        if not isinstance(self.definition, BuffDefinition):
            raise BuffValidationError("definition 必须是 BuffDefinition")
        validate_frame(self.created_frame, "created_frame")
        validate_frame(self.last_applied_frame, "last_applied_frame")
        validate_frame(self.expires_at_frame, "expires_at_frame")
        if not self.created_frame <= self.last_applied_frame < self.expires_at_frame:
            raise BuffValidationError("BuffRecord 必须满足 created <= last_applied < expires")
        if not isinstance(self.lifecycle_state, BuffLifecycleState):
            raise BuffValidationError("lifecycle_state 不受支持")
        if not isinstance(self.state, BuffState):
            raise BuffValidationError("state 必须是 BuffState")
        if self.state.max_stacks != self.definition.max_stacks:
            raise BuffValidationError("state.max_stacks 必须等于 definition.max_stacks")
        if self.state.tags != self.definition.tags:
            raise BuffValidationError("state.tags 必须等于 definition.tags")
        expected_terms = tuple(
            template.term_key for template in self.definition.attribute_modifiers
        )
        actual_terms = tuple(item.term_key for item in self.state.resolved_modifiers)
        if actual_terms != expected_terms:
            raise BuffValidationError("resolved modifier keys 必须与 definition 模板一致")
        if self.lifecycle_state is BuffLifecycleState.ACTIVE:
            if self.removed_frame is not None or self.removal_reason is not None:
                raise BuffValidationError("活动 Buff 不能携带移除信息")
        else:
            if self.removed_frame is None or self.removal_reason is None:
                raise BuffValidationError("非活动 Buff 必须携带移除帧和原因")
            validate_frame(self.removed_frame, "removed_frame")
            if self.removed_frame < self.created_frame:
                raise BuffValidationError("removed_frame 不能早于 created_frame")
            if self.lifecycle_state is BuffLifecycleState.EXPIRED:
                if self.removal_reason is not BuffRemovalReason.EXPIRED:
                    raise BuffValidationError("expired lifecycle 必须对应 expired reason")
            elif self.removal_reason is BuffRemovalReason.EXPIRED:
                raise BuffValidationError("removed lifecycle 不能对应 expired reason")

    def is_active_at(self, frame: int) -> bool:
        validate_frame(frame)
        return (
            self.lifecycle_state is BuffLifecycleState.ACTIVE
            and self.created_frame <= frame < self.expires_at_frame
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "instance_ref": self.instance_ref.to_dict(),
            "definition": self.definition.to_dict(),
            "created_frame": self.created_frame,
            "last_applied_frame": self.last_applied_frame,
            "expires_at_frame": self.expires_at_frame,
            "lifecycle_state": self.lifecycle_state.value,
            "state": self.state.to_dict(),
            "removed_frame": self.removed_frame,
            "removal_reason": None if self.removal_reason is None else self.removal_reason.value,
        }


@dataclass(frozen=True, slots=True)
class BuffApplicationResult:
    request_id: str
    frame: int
    order: int
    outcome: BuffApplicationOutcome
    instance_ref: BuffInstanceRef
    definition_key: str
    mechanic_key: str
    target_ref: AttributeSubjectRef
    applier_ref: AttributeSubjectRef | None
    source_context: RuntimeSourceRef
    stacks_before: int
    stacks_after: int
    expires_at_before: int | None
    expires_at_after: int
    replaced_instance_refs: tuple[BuffInstanceRef, ...] = ()
    resolved_modifiers_after: tuple[BuffResolvedAttributeModifier, ...] = ()
    instance_after: BuffInstanceSnapshot | None = None

    def __post_init__(self) -> None:
        validate_non_empty_text(self.request_id, "request_id")
        validate_frame(self.frame)
        validate_non_negative_int(self.order, "order")
        if not isinstance(self.outcome, BuffApplicationOutcome):
            raise BuffValidationError("outcome 不受支持")
        if not isinstance(self.instance_ref, BuffInstanceRef):
            raise BuffValidationError("instance_ref 必须是 BuffInstanceRef")
        validate_non_empty_text(self.definition_key, "definition_key")
        validate_non_empty_text(self.mechanic_key, "mechanic_key")
        validate_subject_ref(self.target_ref, "target_ref")
        if self.applier_ref is not None:
            validate_subject_ref(self.applier_ref, "applier_ref")
        if not isinstance(self.source_context, RuntimeSourceRef):
            raise BuffValidationError("source_context 必须是 RuntimeSourceRef")
        validate_non_negative_int(self.stacks_before, "stacks_before")
        validate_positive_int(self.stacks_after, "stacks_after")
        if self.expires_at_before is not None:
            validate_frame(self.expires_at_before, "expires_at_before")
        validate_frame(self.expires_at_after, "expires_at_after")
        if self.expires_at_after <= self.frame:
            raise BuffValidationError("expires_at_after 必须晚于 frame")
        object.__setattr__(
            self,
            "replaced_instance_refs",
            tuple(sorted(self.replaced_instance_refs)),
        )
        object.__setattr__(
            self,
            "resolved_modifiers_after",
            tuple(self.resolved_modifiers_after),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "frame": self.frame,
            "order": self.order,
            "outcome": self.outcome.value,
            "instance_ref": self.instance_ref.to_dict(),
            "definition_key": self.definition_key,
            "mechanic_key": self.mechanic_key,
            "target_ref": subject_ref_to_dict(self.target_ref),
            "applier_ref": (
                None if self.applier_ref is None else subject_ref_to_dict(self.applier_ref)
            ),
            "source_context": runtime_source_ref_to_dict(self.source_context),
            "stacks_before": self.stacks_before,
            "stacks_after": self.stacks_after,
            "expires_at_before": self.expires_at_before,
            "expires_at_after": self.expires_at_after,
            "replaced_instance_refs": tuple(ref.to_dict() for ref in self.replaced_instance_refs),
            "resolved_modifiers_after": tuple(
                item.to_dict() for item in self.resolved_modifiers_after
            ),
            "instance_after": (
                None if self.instance_after is None else self.instance_after.to_dict()
            ),
        }


@dataclass(frozen=True, slots=True)
class RemoveBuffRequest:
    request_id: str
    frame: int
    instance_ref: BuffInstanceRef
    reason: BuffRemovalReason

    def __post_init__(self) -> None:
        validate_non_empty_text(self.request_id, "request_id")
        validate_frame(self.frame)
        if not isinstance(self.instance_ref, BuffInstanceRef):
            raise BuffValidationError("instance_ref 必须是 BuffInstanceRef")
        if self.reason not in {
            BuffRemovalReason.DISPELLED,
            BuffRemovalReason.CONSUMED,
            BuffRemovalReason.EXPLICIT,
        }:
            raise BuffValidationError("外部移除请求只允许 dispelled、consumed 或 explicit")


@dataclass(frozen=True, slots=True)
class BuffRemovalResult:
    frame: int
    instance_ref: BuffInstanceRef
    definition_key: str
    mechanic_key: str
    target_ref: AttributeSubjectRef
    applier_ref: AttributeSubjectRef | None
    source_context: RuntimeSourceRef
    reason: BuffRemovalReason
    stack_count: int
    scheduled_expires_at_frame: int

    def __post_init__(self) -> None:
        validate_frame(self.frame)
        if not isinstance(self.instance_ref, BuffInstanceRef):
            raise BuffValidationError("instance_ref 必须是 BuffInstanceRef")
        validate_non_empty_text(self.definition_key, "definition_key")
        validate_non_empty_text(self.mechanic_key, "mechanic_key")
        validate_subject_ref(self.target_ref, "target_ref")
        if self.applier_ref is not None:
            validate_subject_ref(self.applier_ref, "applier_ref")
        if not isinstance(self.source_context, RuntimeSourceRef):
            raise BuffValidationError("source_context 必须是 RuntimeSourceRef")
        if not isinstance(self.reason, BuffRemovalReason):
            raise BuffValidationError("removal reason 不受支持")
        validate_positive_int(self.stack_count, "stack_count")
        validate_frame(self.scheduled_expires_at_frame, "scheduled_expires_at_frame")

    def to_dict(self) -> dict[str, object]:
        return {
            "frame": self.frame,
            "instance_ref": self.instance_ref.to_dict(),
            "definition_key": self.definition_key,
            "mechanic_key": self.mechanic_key,
            "target_ref": subject_ref_to_dict(self.target_ref),
            "applier_ref": (
                None if self.applier_ref is None else subject_ref_to_dict(self.applier_ref)
            ),
            "source_context": runtime_source_ref_to_dict(self.source_context),
            "reason": self.reason.value,
            "stack_count": self.stack_count,
            "scheduled_expires_at_frame": self.scheduled_expires_at_frame,
        }


def removal_result_from_record(record: BuffRecord) -> BuffRemovalResult:
    if record.removed_frame is None or record.removal_reason is None:
        raise BuffValidationError("BuffRemovalResult 只能从已移除记录生成")
    return BuffRemovalResult(
        frame=record.removed_frame,
        instance_ref=record.instance_ref,
        definition_key=record.definition.definition_key,
        mechanic_key=record.definition.mechanic_key,
        target_ref=record.state.target_ref,
        applier_ref=record.state.applier_ref,
        source_context=record.state.source_context,
        reason=record.removal_reason,
        stack_count=record.state.stack_count,
        scheduled_expires_at_frame=record.expires_at_frame,
    )


@dataclass(frozen=True, slots=True)
class BuffMutationPlan:
    operation_id: str
    frame: int
    expected_store_version: int
    request_ids: tuple[str, ...] = ()
    expected_records: tuple[BuffRecord, ...] = ()
    replacement_records: tuple[BuffRecord, ...] = ()
    application_results: tuple[BuffApplicationResult, ...] = ()
    removal_results: tuple[BuffRemovalResult, ...] = ()

    def __post_init__(self) -> None:
        validate_non_empty_text(self.operation_id, "operation_id")
        validate_frame(self.frame)
        validate_non_negative_int(self.expected_store_version, "expected_store_version")
        request_ids = tuple(self.request_ids)
        for request_id in request_ids:
            validate_non_empty_text(request_id, "request_id")
        if len(request_ids) != len(set(request_ids)):
            raise BuffValidationError("request_ids 不能重复")
        expected = tuple(sorted(self.expected_records, key=lambda item: item.instance_ref))
        replacements = tuple(sorted(self.replacement_records, key=lambda item: item.instance_ref))
        if len({record.instance_ref for record in expected}) != len(expected):
            raise BuffValidationError("expected_records 包含重复 instance_ref")
        if len({record.instance_ref for record in replacements}) != len(replacements):
            raise BuffValidationError("replacement_records 包含重复 instance_ref")
        applications = tuple(
            sorted(
                self.application_results,
                key=lambda item: (
                    item.order,
                    item.target_ref.kind.value,
                    item.target_ref.entity_id,
                    item.instance_ref.sequence,
                ),
            )
        )
        removals = tuple(
            sorted(
                self.removal_results,
                key=lambda item: (item.frame, item.instance_ref.sequence),
            )
        )
        object.__setattr__(self, "request_ids", request_ids)
        object.__setattr__(self, "expected_records", expected)
        object.__setattr__(self, "replacement_records", replacements)
        object.__setattr__(self, "application_results", applications)
        object.__setattr__(self, "removal_results", removals)


@dataclass(frozen=True, slots=True)
class BuffCommitReceipt:
    plan: BuffMutationPlan
