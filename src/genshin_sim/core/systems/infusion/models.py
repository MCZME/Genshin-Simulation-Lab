from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.core.attributes import (
    AttributeSubjectKind,
    AttributeSubjectRef,
    RuntimeSourceRef,
)
from genshin_sim.core.elements import AuraAmount, Element
from genshin_sim.core.systems.infusion.definitions import InfusionDefinition
from genshin_sim.core.systems.infusion.enums import (
    EffectiveElementReason,
    InfusionApplicationOutcome,
    InfusionLifecycleState,
    InfusionMode,
    InfusionRemovalReason,
    RefreshPolicy,
)
from genshin_sim.core.systems.infusion.errors import InfusionValidationError


def validate_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise InfusionValidationError(f"{field_name} 必须是非空字符串")


def validate_non_negative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InfusionValidationError(f"{field_name} 必须是非负整数")


def validate_positive_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise InfusionValidationError(f"{field_name} 必须是正整数")


def validate_frame(frame: int, field_name: str = "frame") -> None:
    validate_non_negative_int(frame, field_name)


def validate_character_ref(ref: AttributeSubjectRef, field_name: str) -> None:
    if not isinstance(ref, AttributeSubjectRef):
        raise InfusionValidationError(f"{field_name} 必须是 AttributeSubjectRef")
    if ref.kind is not AttributeSubjectKind.CHARACTER:
        raise InfusionValidationError(f"{field_name} 只支持角色主体")


def runtime_source_ref_key(ref: RuntimeSourceRef) -> tuple[str, str, str]:
    return (ref.kind.value, ref.source_key, ref.instance_id or "")


def subject_ref_to_dict(ref: AttributeSubjectRef) -> dict[str, str]:
    return {"kind": ref.kind.value, "entity_id": ref.entity_id}


def runtime_source_ref_to_dict(ref: RuntimeSourceRef) -> dict[str, str | None]:
    return {"kind": ref.kind.value, "source_key": ref.source_key, "instance_id": ref.instance_id}


@dataclass(frozen=True, order=True, slots=True)
class InfusionInstanceRef:
    sequence: int
    domain_key: str = "infusion"

    def __post_init__(self) -> None:
        validate_positive_int(self.sequence, "sequence")
        if self.domain_key != "infusion":
            raise InfusionValidationError("InfusionInstanceRef.domain_key 必须是 infusion")

    def to_key(self) -> str:
        return f"{self.domain_key}:{self.sequence}"

    def to_dict(self) -> dict[str, object]:
        return {"domain_key": self.domain_key, "sequence": self.sequence}

    def __str__(self) -> str:
        return self.to_key()


@dataclass(frozen=True, slots=True)
class ApplyInfusionRequest:
    request_id: str
    frame: int
    order: int
    definition_key: str
    character_ref: AttributeSubjectRef
    source_context: RuntimeSourceRef
    applier_ref: AttributeSubjectRef | None = None

    def __post_init__(self) -> None:
        validate_non_empty_text(self.request_id, "request_id")
        validate_frame(self.frame)
        validate_non_negative_int(self.order, "order")
        validate_non_empty_text(self.definition_key, "definition_key")
        validate_character_ref(self.character_ref, "character_ref")
        if not isinstance(self.source_context, RuntimeSourceRef):
            raise InfusionValidationError("source_context 必须是 RuntimeSourceRef")
        if self.applier_ref is not None:
            validate_character_ref(self.applier_ref, "applier_ref")


@dataclass(frozen=True, slots=True)
class RemoveInfusionRequest:
    request_id: str
    frame: int
    instance_ref: InfusionInstanceRef
    reason: InfusionRemovalReason

    def __post_init__(self) -> None:
        validate_non_empty_text(self.request_id, "request_id")
        validate_frame(self.frame)
        if not isinstance(self.instance_ref, InfusionInstanceRef):
            raise InfusionValidationError("instance_ref 必须是 InfusionInstanceRef")
        if self.reason not in {
            InfusionRemovalReason.DISPELLED,
            InfusionRemovalReason.CONSUMED,
            InfusionRemovalReason.EXPLICIT,
        }:
            raise InfusionValidationError("外部移除请求只允许 dispelled、consumed 或 explicit")


@dataclass(frozen=True, slots=True)
class InfusionRecord:
    instance_ref: InfusionInstanceRef
    definition: InfusionDefinition
    character_ref: AttributeSubjectRef
    applier_ref: AttributeSubjectRef | None
    source_context: RuntimeSourceRef
    mode: InfusionMode
    element: Element
    refresh_policy: RefreshPolicy
    created_frame: int
    last_applied_frame: int
    expires_at_frame: int
    remaining_gauge: AuraAmount
    frozen: bool = False
    next_refresh_frame: int | None = None
    lifecycle_state: InfusionLifecycleState = InfusionLifecycleState.ACTIVE
    removed_frame: int | None = None
    removal_reason: InfusionRemovalReason | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.instance_ref, InfusionInstanceRef):
            raise InfusionValidationError("instance_ref 必须是 InfusionInstanceRef")
        if not isinstance(self.definition, InfusionDefinition):
            raise InfusionValidationError("definition 必须是 InfusionDefinition")
        validate_character_ref(self.character_ref, "character_ref")
        if self.applier_ref is not None:
            validate_character_ref(self.applier_ref, "applier_ref")
        if not isinstance(self.source_context, RuntimeSourceRef):
            raise InfusionValidationError("source_context 必须是 RuntimeSourceRef")
        if self.mode != self.definition.mode:
            raise InfusionValidationError("record.mode 必须等于 definition.mode")
        if self.element != self.definition.element:
            raise InfusionValidationError("record.element 必须等于 definition.element")
        if self.refresh_policy != self.definition.refresh_policy:
            raise InfusionValidationError(
                "record.refresh_policy 必须等于 definition.refresh_policy"
            )
        validate_frame(self.created_frame, "created_frame")
        validate_frame(self.last_applied_frame, "last_applied_frame")
        validate_frame(self.expires_at_frame, "expires_at_frame")
        if not self.created_frame <= self.last_applied_frame < self.expires_at_frame:
            raise InfusionValidationError(
                "InfusionRecord 必须满足 created <= last_applied < expires"
            )
        if not isinstance(self.remaining_gauge, AuraAmount):
            raise InfusionValidationError("remaining_gauge 必须是 AuraAmount")
        if self.remaining_gauge > self.definition.weapon_gauge:
            raise InfusionValidationError("remaining_gauge 不能超过定义 weapon_gauge")
        if not isinstance(self.frozen, bool):
            raise InfusionValidationError("frozen 必须是布尔值")
        if self.refresh_policy is RefreshPolicy.ONCE:
            if self.next_refresh_frame is not None:
                raise InfusionValidationError("ONCE 记录不能携带 next_refresh_frame")
        else:
            if (
                self.next_refresh_frame is None
                or not self.last_applied_frame < self.next_refresh_frame
            ):
                raise InfusionValidationError(
                    "PERIODIC 记录必须携带晚于 last_applied 的 next_refresh_frame"
                )
        if not isinstance(self.lifecycle_state, InfusionLifecycleState):
            raise InfusionValidationError("lifecycle_state 不受支持")
        if self.lifecycle_state is InfusionLifecycleState.ACTIVE:
            if self.removed_frame is not None or self.removal_reason is not None:
                raise InfusionValidationError("活动记录不能携带移除信息")
        else:
            if self.removed_frame is None or self.removal_reason is None:
                raise InfusionValidationError("非活动记录必须携带移除帧和原因")
            validate_frame(self.removed_frame, "removed_frame")
            if self.removed_frame < self.created_frame:
                raise InfusionValidationError("removed_frame 不能早于 created_frame")
            if self.lifecycle_state is InfusionLifecycleState.EXPIRED:
                if self.removal_reason is not InfusionRemovalReason.EXPIRED:
                    raise InfusionValidationError("expired lifecycle 必须对应 expired reason")
            elif self.removal_reason is InfusionRemovalReason.EXPIRED:
                raise InfusionValidationError("removed lifecycle 不能对应 expired reason")

    def is_active_at(self, frame: int) -> bool:
        validate_frame(frame)
        return (
            self.lifecycle_state is InfusionLifecycleState.ACTIVE
            and self.created_frame <= frame < self.expires_at_frame
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "instance_ref": self.instance_ref.to_dict(),
            "definition": self.definition.to_dict(),
            "character_ref": subject_ref_to_dict(self.character_ref),
            "applier_ref": (
                None if self.applier_ref is None else subject_ref_to_dict(self.applier_ref)
            ),
            "source_context": runtime_source_ref_to_dict(self.source_context),
            "mode": self.mode.value,
            "element": self.element.value,
            "refresh_policy": self.refresh_policy.value,
            "created_frame": self.created_frame,
            "last_applied_frame": self.last_applied_frame,
            "expires_at_frame": self.expires_at_frame,
            "next_refresh_frame": self.next_refresh_frame,
            "lifecycle_state": self.lifecycle_state.value,
            "removed_frame": self.removed_frame,
            "removal_reason": None if self.removal_reason is None else self.removal_reason.value,
            "remaining_gauge": self.remaining_gauge.to_dict(),
            "frozen": self.frozen,
        }


@dataclass(frozen=True, slots=True)
class InfusionApplicationResult:
    request_id: str
    frame: int
    order: int
    outcome: InfusionApplicationOutcome
    instance_ref: InfusionInstanceRef
    definition_key: str
    mechanic_key: str
    mode: InfusionMode
    element: Element
    character_ref: AttributeSubjectRef
    applier_ref: AttributeSubjectRef | None
    source_context: RuntimeSourceRef
    expires_at_before: int | None
    expires_at_after: int
    next_refresh_frame_after: int | None
    replaced_instance_refs: tuple[InfusionInstanceRef, ...] = ()

    def __post_init__(self) -> None:
        validate_non_empty_text(self.request_id, "request_id")
        validate_frame(self.frame)
        validate_non_negative_int(self.order, "order")
        if not isinstance(self.outcome, InfusionApplicationOutcome):
            raise InfusionValidationError("outcome 不受支持")
        if not isinstance(self.instance_ref, InfusionInstanceRef):
            raise InfusionValidationError("instance_ref 必须是 InfusionInstanceRef")
        validate_non_empty_text(self.definition_key, "definition_key")
        validate_non_empty_text(self.mechanic_key, "mechanic_key")
        if not isinstance(self.mode, InfusionMode):
            raise InfusionValidationError("mode 不受支持")
        if not isinstance(self.element, Element):
            raise InfusionValidationError("element 不受支持")
        validate_character_ref(self.character_ref, "character_ref")
        if self.applier_ref is not None:
            validate_character_ref(self.applier_ref, "applier_ref")
        if not isinstance(self.source_context, RuntimeSourceRef):
            raise InfusionValidationError("source_context 必须是 RuntimeSourceRef")
        if self.expires_at_before is not None:
            validate_frame(self.expires_at_before, "expires_at_before")
        validate_frame(self.expires_at_after, "expires_at_after")
        if self.expires_at_after <= self.frame:
            raise InfusionValidationError("expires_at_after 必须晚于 frame")
        if self.next_refresh_frame_after is not None:
            validate_frame(self.next_refresh_frame_after, "next_refresh_frame_after")
            if self.next_refresh_frame_after <= self.frame:
                raise InfusionValidationError("next_refresh_frame_after 必须晚于 frame")
        object.__setattr__(
            self,
            "replaced_instance_refs",
            tuple(sorted(self.replaced_instance_refs)),
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
            "mode": self.mode.value,
            "element": self.element.value,
            "character_ref": subject_ref_to_dict(self.character_ref),
            "applier_ref": (
                None if self.applier_ref is None else subject_ref_to_dict(self.applier_ref)
            ),
            "source_context": runtime_source_ref_to_dict(self.source_context),
            "expires_at_before": self.expires_at_before,
            "expires_at_after": self.expires_at_after,
            "next_refresh_frame_after": self.next_refresh_frame_after,
            "replaced_instance_refs": tuple(ref.to_dict() for ref in self.replaced_instance_refs),
        }


@dataclass(frozen=True, slots=True)
class InfusionRemovalResult:
    frame: int
    instance_ref: InfusionInstanceRef
    definition_key: str
    mechanic_key: str
    mode: InfusionMode
    element: Element
    character_ref: AttributeSubjectRef
    reason: InfusionRemovalReason
    scheduled_expires_at_frame: int

    def __post_init__(self) -> None:
        validate_frame(self.frame)
        if not isinstance(self.instance_ref, InfusionInstanceRef):
            raise InfusionValidationError("instance_ref 必须是 InfusionInstanceRef")
        validate_non_empty_text(self.definition_key, "definition_key")
        validate_non_empty_text(self.mechanic_key, "mechanic_key")
        if not isinstance(self.mode, InfusionMode):
            raise InfusionValidationError("mode 不受支持")
        if not isinstance(self.element, Element):
            raise InfusionValidationError("element 不受支持")
        validate_character_ref(self.character_ref, "character_ref")
        if not isinstance(self.reason, InfusionRemovalReason):
            raise InfusionValidationError("reason 不受支持")
        validate_frame(self.scheduled_expires_at_frame, "scheduled_expires_at_frame")

    def to_dict(self) -> dict[str, object]:
        return {
            "frame": self.frame,
            "instance_ref": self.instance_ref.to_dict(),
            "definition_key": self.definition_key,
            "mechanic_key": self.mechanic_key,
            "mode": self.mode.value,
            "element": self.element.value,
            "character_ref": subject_ref_to_dict(self.character_ref),
            "reason": self.reason.value,
            "scheduled_expires_at_frame": self.scheduled_expires_at_frame,
        }


@dataclass(frozen=True, slots=True)
class EffectiveElementResolution:
    frame: int
    character_ref: AttributeSubjectRef
    element: Element
    mode: InfusionMode | None
    reason: EffectiveElementReason
    source_refs: tuple[RuntimeSourceRef, ...]
    weapon_gauge: AuraAmount | None = None

    def __post_init__(self) -> None:
        validate_frame(self.frame)
        validate_character_ref(self.character_ref, "character_ref")
        if not isinstance(self.element, Element):
            raise InfusionValidationError("element 不受支持")
        if self.mode is not None and not isinstance(self.mode, InfusionMode):
            raise InfusionValidationError("mode 不受支持")
        if not isinstance(self.reason, EffectiveElementReason):
            raise InfusionValidationError("reason 不受支持")
        for ref in self.source_refs:
            if not isinstance(ref, RuntimeSourceRef):
                raise InfusionValidationError("source_refs 必须是 RuntimeSourceRef")
        if len({runtime_source_ref_key(ref) for ref in self.source_refs}) != len(self.source_refs):
            raise InfusionValidationError("source_refs 不能重复")
        sources = tuple(sorted(self.source_refs, key=runtime_source_ref_key))
        if self.mode is InfusionMode.CONVERSION and len(sources) != 1:
            raise InfusionValidationError("转化解析必须恰好包含一个来源")
        if self.weapon_gauge is not None and (
            not isinstance(self.weapon_gauge, AuraAmount) or self.weapon_gauge.is_zero
        ):
            raise InfusionValidationError("weapon_gauge 必须是正 AuraAmount 或 None")
        object.__setattr__(self, "source_refs", sources)

    def to_dict(self) -> dict[str, object]:
        return {
            "frame": self.frame,
            "character_ref": subject_ref_to_dict(self.character_ref),
            "element": self.element.value,
            "mode": None if self.mode is None else self.mode.value,
            "reason": self.reason.value,
            "source_refs": tuple(runtime_source_ref_to_dict(ref) for ref in self.source_refs),
            "weapon_gauge": None if self.weapon_gauge is None else self.weapon_gauge.to_dict(),
        }


def removal_result_from_record(record: InfusionRecord) -> InfusionRemovalResult:
    if record.removed_frame is None or record.removal_reason is None:
        raise InfusionValidationError("InfusionRemovalResult 只能从已移除记录生成")
    return InfusionRemovalResult(
        frame=record.removed_frame,
        instance_ref=record.instance_ref,
        definition_key=record.definition.definition_key,
        mechanic_key=record.definition.mechanic_key,
        mode=record.mode,
        element=record.element,
        character_ref=record.character_ref,
        reason=record.removal_reason,
        scheduled_expires_at_frame=record.expires_at_frame,
    )


@dataclass(frozen=True, slots=True)
class InfusionMutationPlan:
    operation_id: str
    frame: int
    expected_store_version: int
    request_ids: tuple[str, ...] = ()
    expected_records: tuple[InfusionRecord, ...] = ()
    replacement_records: tuple[InfusionRecord, ...] = ()
    application_results: tuple[InfusionApplicationResult, ...] = ()
    removal_results: tuple[InfusionRemovalResult, ...] = ()

    def __post_init__(self) -> None:
        validate_non_empty_text(self.operation_id, "operation_id")
        validate_frame(self.frame)
        validate_non_negative_int(self.expected_store_version, "expected_store_version")
        request_ids = tuple(self.request_ids)
        for request_id in request_ids:
            validate_non_empty_text(request_id, "request_id")
        if len(request_ids) != len(set(request_ids)):
            raise InfusionValidationError("request_ids 不能重复")
        expected = tuple(sorted(self.expected_records, key=lambda item: item.instance_ref))
        replacements = tuple(sorted(self.replacement_records, key=lambda item: item.instance_ref))
        if len({record.instance_ref for record in expected}) != len(expected):
            raise InfusionValidationError("expected_records 包含重复 instance_ref")
        if len({record.instance_ref for record in replacements}) != len(replacements):
            raise InfusionValidationError("replacement_records 包含重复 instance_ref")
        applications = tuple(
            sorted(
                self.application_results,
                key=lambda item: (
                    item.order,
                    item.character_ref.kind.value,
                    item.character_ref.entity_id,
                    item.instance_ref.sequence,
                ),
            )
        )
        removals = tuple(
            sorted(self.removal_results, key=lambda item: (item.frame, item.instance_ref.sequence))
        )
        object.__setattr__(self, "request_ids", request_ids)
        object.__setattr__(self, "expected_records", expected)
        object.__setattr__(self, "replacement_records", replacements)
        object.__setattr__(self, "application_results", applications)
        object.__setattr__(self, "removal_results", removals)


@dataclass(frozen=True, slots=True)
class InfusionCommitReceipt:
    plan: InfusionMutationPlan
