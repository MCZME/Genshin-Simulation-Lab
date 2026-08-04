from __future__ import annotations

import math
from dataclasses import dataclass

from genshin_sim.core.attributes import (
    AttributeResolution,
    AttributeSubjectKind,
    AttributeSubjectRef,
    RuntimeSourceRef,
)
from genshin_sim.core.systems.damage import DamageElement
from genshin_sim.core.systems.shield.enums import (
    ShieldChangeReason,
    ShieldElement,
    ShieldGrantOutcome,
    ShieldGrantPolicy,
    ShieldLifecycleState,
    ShieldProtectionKind,
    ShieldRemovalReason,
)
from genshin_sim.core.systems.shield.errors import (
    ShieldCapacityError,
    ShieldPolicyError,
    ShieldValidationError,
)
from genshin_sim.core.systems.shield.formulas import (
    ShieldCapacityComponentResult,
    ShieldCapacityFormula,
    ShieldNativeMultiplierResult,
    normalize_shield_zero,
    validate_non_empty_text,
    validate_non_negative_shield_float,
    validate_shield_float,
)


def validate_frame(frame: int, field_name: str = "frame") -> None:
    if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
        raise ShieldValidationError(f"{field_name} 必须是非负整数")


def validate_positive_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ShieldValidationError(f"{field_name} 必须是正整数")


def validate_character_ref(ref: AttributeSubjectRef, field_name: str) -> None:
    if not isinstance(ref, AttributeSubjectRef):
        raise ShieldValidationError(f"{field_name} 必须是 AttributeSubjectRef")
    if ref.kind is not AttributeSubjectKind.CHARACTER:
        raise ShieldValidationError(f"{field_name} 必须引用角色主体")


def normalize_tags(tags: frozenset[str]) -> frozenset[str]:
    normalized = frozenset(tags)
    for tag in normalized:
        validate_non_empty_text(tag, "shield tag")
    return normalized


@dataclass(frozen=True, slots=True)
class ShieldProtectionRef:
    kind: ShieldProtectionKind
    protection_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ShieldProtectionKind):
            raise ShieldValidationError("protection kind 不受支持")
        validate_non_empty_text(self.protection_id, "protection_id")

    @classmethod
    def active_team(cls, protection_id: str = "team:player") -> ShieldProtectionRef:
        return cls(ShieldProtectionKind.ACTIVE_TEAM, protection_id)

    @classmethod
    def character(cls, protection_id: str) -> ShieldProtectionRef:
        return cls(ShieldProtectionKind.CHARACTER, protection_id)

    def to_key(self) -> str:
        return f"{self.kind.value}:{self.protection_id}"

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind.value, "protection_id": self.protection_id}


@dataclass(frozen=True, slots=True)
class ShieldGrantRequest:
    grant_id: str
    frame: int
    mechanic_key: str
    handler_key: str
    protection_ref: ShieldProtectionRef
    creator_ref: AttributeSubjectRef
    source_context: RuntimeSourceRef
    element: ShieldElement
    duration_frames: int
    grant_formula: ShieldCapacityFormula
    grant_policy: ShieldGrantPolicy
    conflict_key: str
    capacity_limit_formula: ShieldCapacityFormula | None = None
    tags: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        for value, name in (
            (self.grant_id, "grant_id"),
            (self.mechanic_key, "mechanic_key"),
            (self.handler_key, "handler_key"),
            (self.conflict_key, "conflict_key"),
        ):
            validate_non_empty_text(value, name)
        validate_frame(self.frame)
        validate_character_ref(self.creator_ref, "creator_ref")
        if not isinstance(self.protection_ref, ShieldProtectionRef):
            raise ShieldValidationError("protection_ref 必须是 ShieldProtectionRef")
        if not isinstance(self.source_context, RuntimeSourceRef):
            raise ShieldValidationError("source_context 必须是 RuntimeSourceRef")
        if not isinstance(self.element, ShieldElement):
            raise ShieldValidationError("element 不受支持")
        validate_positive_int(self.duration_frames, "duration_frames")
        if not isinstance(self.grant_formula, ShieldCapacityFormula):
            raise ShieldValidationError("grant_formula 必须是 ShieldCapacityFormula")
        if not isinstance(self.grant_policy, ShieldGrantPolicy):
            raise ShieldValidationError("grant_policy 不受支持")
        if self.grant_policy is ShieldGrantPolicy.ADD_CAPPED_REFRESH:
            if self.capacity_limit_formula is None:
                raise ShieldPolicyError("add_capped_refresh 必须提供 capacity_limit_formula")
        elif self.capacity_limit_formula is not None:
            raise ShieldPolicyError("只有 add_capped_refresh 可以提供 capacity_limit_formula")
        if self.capacity_limit_formula is not None and not isinstance(
            self.capacity_limit_formula,
            ShieldCapacityFormula,
        ):
            raise ShieldValidationError("capacity_limit_formula 必须是 ShieldCapacityFormula")
        object.__setattr__(self, "tags", normalize_tags(self.tags))


@dataclass(frozen=True, slots=True)
class ShieldGrantResolution:
    grant_id: str
    frame: int
    creator_ref: AttributeSubjectRef
    protection_ref: ShieldProtectionRef
    component_results: tuple[ShieldCapacityComponentResult, ...]
    flat_absorption: float
    native_multiplier_results: tuple[ShieldNativeMultiplierResult, ...]
    granted_absorption: float
    capacity_limit: float | None
    attribute_trace: tuple[AttributeResolution, ...]
    source_context: RuntimeSourceRef

    def __post_init__(self) -> None:
        validate_non_empty_text(self.grant_id, "grant_id")
        validate_frame(self.frame)
        validate_character_ref(self.creator_ref, "creator_ref")
        object.__setattr__(self, "component_results", tuple(self.component_results))
        object.__setattr__(
            self,
            "native_multiplier_results",
            tuple(self.native_multiplier_results),
        )
        object.__setattr__(self, "attribute_trace", tuple(self.attribute_trace))
        object.__setattr__(
            self,
            "flat_absorption",
            validate_non_negative_shield_float(self.flat_absorption, "flat_absorption"),
        )
        granted = validate_shield_float(self.granted_absorption, "granted_absorption")
        if granted <= 0:
            raise ShieldCapacityError("granted_absorption 必须是正数")
        object.__setattr__(self, "granted_absorption", granted)
        if self.capacity_limit is not None:
            capacity_limit = validate_shield_float(self.capacity_limit, "capacity_limit")
            if capacity_limit <= 0:
                raise ShieldCapacityError("capacity_limit 必须是正数")
            object.__setattr__(self, "capacity_limit", capacity_limit)

    def to_dict(self) -> dict[str, object]:
        return {
            "grant_id": self.grant_id,
            "frame": self.frame,
            "creator_ref": _subject_ref_to_dict(self.creator_ref),
            "protection_ref": self.protection_ref.to_dict(),
            "component_results": tuple(item.to_dict() for item in self.component_results),
            "flat_absorption": self.flat_absorption,
            "native_multiplier_results": tuple(
                item.to_dict() for item in self.native_multiplier_results
            ),
            "granted_absorption": self.granted_absorption,
            "capacity_limit": self.capacity_limit,
            "attribute_trace": tuple(
                _attribute_resolution_to_dict(item) for item in self.attribute_trace
            ),
            "source_context": _runtime_source_ref_to_dict(self.source_context),
        }


@dataclass(frozen=True, order=True, slots=True)
class ShieldInstanceRef:
    sequence: int
    domain_key: str = "shield"

    def __post_init__(self) -> None:
        validate_positive_int(self.sequence, "sequence")
        if self.domain_key != "shield":
            raise ShieldValidationError("ShieldInstanceRef.domain_key 必须是 shield")

    def to_dict(self) -> dict[str, object]:
        return {"domain_key": self.domain_key, "sequence": self.sequence}


@dataclass(frozen=True, slots=True)
class ShieldState:
    protection_ref: ShieldProtectionRef
    creator_ref: AttributeSubjectRef
    source_context: RuntimeSourceRef
    element: ShieldElement
    maximum_native_absorption: float
    remaining_native_absorption: float
    conflict_key: str
    grant_snapshot_ref: str
    tags: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        for value, name in (
            (self.conflict_key, "conflict_key"),
            (self.grant_snapshot_ref, "grant_snapshot_ref"),
        ):
            validate_non_empty_text(value, name)
        validate_character_ref(self.creator_ref, "creator_ref")
        maximum = validate_shield_float(
            self.maximum_native_absorption,
            "maximum_native_absorption",
        )
        remaining = validate_shield_float(
            self.remaining_native_absorption,
            "remaining_native_absorption",
        )
        if maximum <= 0 or remaining < 0 or remaining > maximum:
            raise ShieldCapacityError(
                "护盾状态必须满足 0 <= remaining_native_absorption <= maximum_native_absorption"
            )
        object.__setattr__(self, "maximum_native_absorption", maximum)
        object.__setattr__(self, "remaining_native_absorption", remaining)
        object.__setattr__(self, "tags", normalize_tags(self.tags))


@dataclass(frozen=True, slots=True)
class ShieldRecord:
    instance_ref: ShieldInstanceRef
    mechanic_key: str
    handler_key: str
    created_frame: int
    expires_at_frame: int
    lifecycle_state: ShieldLifecycleState
    state: ShieldState
    removed_frame: int | None = None
    removal_reason: ShieldRemovalReason | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.instance_ref, ShieldInstanceRef):
            raise ShieldValidationError("instance_ref 必须是 ShieldInstanceRef")
        validate_non_empty_text(self.mechanic_key, "mechanic_key")
        validate_non_empty_text(self.handler_key, "handler_key")
        validate_frame(self.created_frame, "created_frame")
        validate_frame(self.expires_at_frame, "expires_at_frame")
        if self.created_frame >= self.expires_at_frame:
            raise ShieldValidationError("created_frame 必须早于 expires_at_frame")
        if not isinstance(self.lifecycle_state, ShieldLifecycleState):
            raise ShieldValidationError("lifecycle_state 不受支持")
        if not isinstance(self.state, ShieldState):
            raise ShieldValidationError("state 必须是 ShieldState")
        if self.lifecycle_state is ShieldLifecycleState.ACTIVE:
            if self.removed_frame is not None or self.removal_reason is not None:
                raise ShieldValidationError("活动护盾不能携带移除信息")
            if self.state.remaining_native_absorption <= 0:
                raise ShieldCapacityError("活动护盾的 remaining_native_absorption 必须为正数")
        else:
            if self.removed_frame is None or self.removal_reason is None:
                raise ShieldValidationError("非活动护盾必须携带移除帧和原因")
            validate_frame(self.removed_frame, "removed_frame")

    def is_active_at(self, frame: int) -> bool:
        validate_frame(frame)
        return (
            self.lifecycle_state is ShieldLifecycleState.ACTIVE
            and self.created_frame <= frame < self.expires_at_frame
        )


@dataclass(frozen=True, slots=True)
class ShieldGrantResult:
    resolution: ShieldGrantResolution
    outcome: ShieldGrantOutcome
    instance_ref: ShieldInstanceRef
    replaced_instance_ref: ShieldInstanceRef | None
    remaining_before: float
    remaining_after: float
    maximum_after: float
    expires_at_before: int | None
    expires_at_after: int

    def __post_init__(self) -> None:
        if not isinstance(self.instance_ref, ShieldInstanceRef):
            raise ShieldValidationError("instance_ref 必须是 ShieldInstanceRef")
        if self.replaced_instance_ref is not None and not isinstance(
            self.replaced_instance_ref, ShieldInstanceRef
        ):
            raise ShieldValidationError("replaced_instance_ref 必须是 ShieldInstanceRef 或 None")
        if not isinstance(self.outcome, ShieldGrantOutcome):
            raise ShieldValidationError("outcome 不受支持")
        for field_name in ("remaining_before", "remaining_after", "maximum_after"):
            object.__setattr__(
                self,
                field_name,
                validate_non_negative_shield_float(getattr(self, field_name), field_name),
            )
        if self.remaining_after <= 0 or self.maximum_after <= 0:
            raise ShieldCapacityError("授予后的活动护盾容量必须为正数")
        if self.remaining_after > self.maximum_after:
            raise ShieldCapacityError("remaining_after 不能大于 maximum_after")
        if self.expires_at_before is not None:
            validate_frame(self.expires_at_before, "expires_at_before")
        validate_frame(self.expires_at_after, "expires_at_after")

    def to_dict(self) -> dict[str, object]:
        return {
            "resolution": self.resolution.to_dict(),
            "outcome": self.outcome.value,
            "instance_ref": self.instance_ref.to_dict(),
            "replaced_instance_ref": None
            if self.replaced_instance_ref is None
            else self.replaced_instance_ref.to_dict(),
            "remaining_before": self.remaining_before,
            "remaining_after": self.remaining_after,
            "maximum_after": self.maximum_after,
            "expires_at_before": self.expires_at_before,
            "expires_at_after": self.expires_at_after,
        }


@dataclass(frozen=True, slots=True)
class ShieldGrantPlan:
    """护盾授予的完整记录替换计划。"""

    operation_id: str
    frame: int
    expected_store_version: int
    expected_records: tuple[ShieldRecord, ...]
    replacement_records: tuple[ShieldRecord, ...]
    result: ShieldGrantResult
    capacity_changes: tuple[ShieldCapacityChangeResult, ...] = ()
    removals: tuple[ShieldRemovalResult, ...] = ()

    def __post_init__(self) -> None:
        validate_non_empty_text(self.operation_id, "operation_id")
        validate_frame(self.frame)
        if (
            isinstance(self.expected_store_version, bool)
            or not isinstance(self.expected_store_version, int)
            or self.expected_store_version < 0
        ):
            raise ShieldValidationError("expected_store_version 必须是非负整数")
        if not isinstance(self.result, ShieldGrantResult):
            raise ShieldValidationError("result 必须是 ShieldGrantResult")
        if self.result.resolution.frame != self.frame:
            raise ShieldValidationError("ShieldGrantPlan 与 result 帧不一致")
        expected = tuple(sorted(self.expected_records, key=lambda item: item.instance_ref))
        replacements = tuple(sorted(self.replacement_records, key=lambda item: item.instance_ref))
        if any(not isinstance(record, ShieldRecord) for record in expected):
            raise ShieldValidationError("expected_records 必须全部是 ShieldRecord")
        if any(not isinstance(record, ShieldRecord) for record in replacements):
            raise ShieldValidationError("replacement_records 必须全部是 ShieldRecord")
        if len({record.instance_ref for record in expected}) != len(expected):
            raise ShieldValidationError("expected_records 包含重复 instance_ref")
        if len({record.instance_ref for record in replacements}) != len(replacements):
            raise ShieldValidationError("replacement_records 包含重复 instance_ref")
        object.__setattr__(self, "expected_records", expected)
        object.__setattr__(self, "replacement_records", replacements)
        object.__setattr__(self, "capacity_changes", tuple(self.capacity_changes))
        object.__setattr__(self, "removals", tuple(self.removals))


@dataclass(frozen=True, slots=True)
class ShieldGrantCommitReceipt:
    """已经提交的护盾授予计划回执。"""

    plan: ShieldGrantPlan


@dataclass(frozen=True, slots=True)
class ShieldCapacityChangeResult:
    frame: int
    instance_ref: ShieldInstanceRef
    mechanic_key: str
    protection_ref: ShieldProtectionRef
    reason: ShieldChangeReason
    native_before: float
    native_after: float
    maximum_before: float
    maximum_after: float

    def __post_init__(self) -> None:
        validate_frame(self.frame)
        if not isinstance(self.instance_ref, ShieldInstanceRef):
            raise ShieldValidationError("instance_ref 必须是 ShieldInstanceRef")
        validate_non_empty_text(self.mechanic_key, "mechanic_key")
        if not isinstance(self.reason, ShieldChangeReason):
            raise ShieldValidationError("change reason 不受支持")
        for field_name in (
            "native_before",
            "native_after",
            "maximum_before",
            "maximum_after",
        ):
            object.__setattr__(
                self,
                field_name,
                validate_non_negative_shield_float(getattr(self, field_name), field_name),
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "frame": self.frame,
            "instance_ref": self.instance_ref.to_dict(),
            "mechanic_key": self.mechanic_key,
            "protection_ref": self.protection_ref.to_dict(),
            "reason": self.reason.value,
            "native_before": self.native_before,
            "native_after": self.native_after,
            "maximum_before": self.maximum_before,
            "maximum_after": self.maximum_after,
        }


@dataclass(frozen=True, slots=True)
class ShieldRemovalResult:
    frame: int
    instance_ref: ShieldInstanceRef
    mechanic_key: str
    protection_ref: ShieldProtectionRef
    reason: ShieldRemovalReason
    native_remaining: float

    def __post_init__(self) -> None:
        validate_frame(self.frame)
        if not isinstance(self.instance_ref, ShieldInstanceRef):
            raise ShieldValidationError("instance_ref 必须是 ShieldInstanceRef")
        validate_non_empty_text(self.mechanic_key, "mechanic_key")
        if not isinstance(self.reason, ShieldRemovalReason):
            raise ShieldValidationError("removal reason 不受支持")
        object.__setattr__(
            self,
            "native_remaining",
            validate_non_negative_shield_float(self.native_remaining, "native_remaining"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "frame": self.frame,
            "instance_ref": self.instance_ref.to_dict(),
            "mechanic_key": self.mechanic_key,
            "protection_ref": self.protection_ref.to_dict(),
            "reason": self.reason.value,
            "native_remaining": self.native_remaining,
        }


@dataclass(frozen=True, slots=True)
class ShieldAbsorptionRequest:
    damage_id: str
    frame: int
    target_ref: AttributeSubjectRef
    incoming_amount: float
    element: DamageElement
    source_ref: AttributeSubjectRef | None = None
    source_context: RuntimeSourceRef | None = None
    tags: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        validate_non_empty_text(self.damage_id, "damage_id")
        validate_frame(self.frame)
        validate_character_ref(self.target_ref, "target_ref")
        object.__setattr__(
            self,
            "incoming_amount",
            validate_non_negative_shield_float(self.incoming_amount, "incoming_amount"),
        )
        if not isinstance(self.element, DamageElement):
            raise ShieldValidationError("damage element 不受支持")
        if self.source_ref is not None and not isinstance(self.source_ref, AttributeSubjectRef):
            raise ShieldValidationError("source_ref 必须是 AttributeSubjectRef 或 None")
        if self.source_context is not None and not isinstance(
            self.source_context,
            RuntimeSourceRef,
        ):
            raise ShieldValidationError("source_context 必须是 RuntimeSourceRef 或 None")
        object.__setattr__(self, "tags", normalize_tags(self.tags))

    def to_dict(self) -> dict[str, object]:
        return {
            "damage_id": self.damage_id,
            "frame": self.frame,
            "target_ref": _subject_ref_to_dict(self.target_ref),
            "incoming_amount": self.incoming_amount,
            "element": self.element.value,
            "source_ref": None
            if self.source_ref is None
            else _subject_ref_to_dict(self.source_ref),
            "source_context": None
            if self.source_context is None
            else _runtime_source_ref_to_dict(self.source_context),
            "tags": tuple(sorted(self.tags)),
        }


@dataclass(frozen=True, slots=True)
class ShieldHitResult:
    instance_ref: ShieldInstanceRef
    mechanic_key: str
    protection_ref: ShieldProtectionRef
    element: ShieldElement
    native_before: float
    native_cost: float
    native_after: float
    element_multiplier: float
    shield_strength: float
    shield_strength_multiplier: float
    effective_multiplier: float
    absorbable_incoming_damage: float
    depleted: bool

    def __post_init__(self) -> None:
        if not isinstance(self.instance_ref, ShieldInstanceRef):
            raise ShieldValidationError("instance_ref 必须是 ShieldInstanceRef")
        validate_non_empty_text(self.mechanic_key, "mechanic_key")
        for field_name in (
            "native_before",
            "native_cost",
            "native_after",
            "element_multiplier",
            "shield_strength",
            "shield_strength_multiplier",
            "effective_multiplier",
            "absorbable_incoming_damage",
        ):
            object.__setattr__(
                self,
                field_name,
                validate_shield_float(getattr(self, field_name), field_name),
            )
        if min(self.native_before, self.native_cost, self.native_after) < 0:
            raise ShieldCapacityError("ShieldHitResult 原生容量不能为负数")
        if self.effective_multiplier <= 0:
            raise ShieldCapacityError("effective_multiplier 必须是正数")
        if not isinstance(self.depleted, bool):
            raise ShieldValidationError("depleted 必须是布尔值")

    def to_dict(self) -> dict[str, object]:
        return {
            "instance_ref": self.instance_ref.to_dict(),
            "mechanic_key": self.mechanic_key,
            "protection_ref": self.protection_ref.to_dict(),
            "element": self.element.value,
            "native_before": self.native_before,
            "native_cost": self.native_cost,
            "native_after": self.native_after,
            "element_multiplier": self.element_multiplier,
            "shield_strength": self.shield_strength,
            "shield_strength_multiplier": self.shield_strength_multiplier,
            "effective_multiplier": self.effective_multiplier,
            "absorbable_incoming_damage": self.absorbable_incoming_damage,
            "depleted": self.depleted,
        }


@dataclass(frozen=True, slots=True)
class ShieldAbsorptionResult:
    damage_id: str
    frame: int
    target_ref: AttributeSubjectRef
    incoming_amount: float
    element: DamageElement
    matched_protection_refs: tuple[ShieldProtectionRef, ...]
    active_character_shield_strength: float
    shield_hits: tuple[ShieldHitResult, ...]
    protected_damage: float
    health_bound_damage: float
    had_active_shield_before: bool
    has_active_shield_after: bool
    depleted_instance_refs: tuple[ShieldInstanceRef, ...]

    def __post_init__(self) -> None:
        validate_non_empty_text(self.damage_id, "damage_id")
        validate_frame(self.frame)
        validate_character_ref(self.target_ref, "target_ref")
        object.__setattr__(self, "shield_hits", tuple(self.shield_hits))
        object.__setattr__(
            self,
            "matched_protection_refs",
            tuple(sorted(set(self.matched_protection_refs), key=lambda item: item.to_key())),
        )
        object.__setattr__(
            self,
            "depleted_instance_refs",
            tuple(sorted(self.depleted_instance_refs)),
        )
        for field_name in (
            "incoming_amount",
            "active_character_shield_strength",
            "protected_damage",
            "health_bound_damage",
        ):
            object.__setattr__(
                self,
                field_name,
                validate_shield_float(getattr(self, field_name), field_name),
            )
        if min(self.incoming_amount, self.protected_damage, self.health_bound_damage) < 0:
            raise ShieldCapacityError("来伤和保护量不能为负数")
        if not math.isclose(
            self.incoming_amount,
            self.protected_damage + self.health_bound_damage,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise ShieldCapacityError(
                "incoming_amount 必须等于 protected_damage + health_bound_damage"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "damage_id": self.damage_id,
            "frame": self.frame,
            "target_ref": _subject_ref_to_dict(self.target_ref),
            "incoming_amount": self.incoming_amount,
            "element": self.element.value,
            "matched_protection_refs": tuple(
                item.to_dict() for item in self.matched_protection_refs
            ),
            "active_character_shield_strength": self.active_character_shield_strength,
            "shield_hits": tuple(hit.to_dict() for hit in self.shield_hits),
            "protected_damage": self.protected_damage,
            "health_bound_damage": self.health_bound_damage,
            "had_active_shield_before": self.had_active_shield_before,
            "has_active_shield_after": self.has_active_shield_after,
            "depleted_instance_refs": tuple(item.to_dict() for item in self.depleted_instance_refs),
        }


@dataclass(frozen=True, slots=True)
class ShieldMutationPlan:
    operation_id: str
    frame: int
    expected_store_version: int
    expected_records: tuple[ShieldRecord, ...]
    replacement_records: tuple[ShieldRecord, ...]

    def __post_init__(self) -> None:
        validate_non_empty_text(self.operation_id, "operation_id")
        validate_frame(self.frame)
        if (
            isinstance(self.expected_store_version, bool)
            or not isinstance(self.expected_store_version, int)
            or self.expected_store_version < 0
        ):
            raise ShieldValidationError("expected_store_version 必须是非负整数")
        if any(not isinstance(record, ShieldRecord) for record in self.expected_records):
            raise ShieldValidationError("expected_records 必须全部是 ShieldRecord")
        if any(not isinstance(record, ShieldRecord) for record in self.replacement_records):
            raise ShieldValidationError("replacement_records 必须全部是 ShieldRecord")
        object.__setattr__(
            self,
            "expected_records",
            tuple(sorted(self.expected_records, key=lambda item: item.instance_ref)),
        )
        object.__setattr__(
            self,
            "replacement_records",
            tuple(sorted(self.replacement_records, key=lambda item: item.instance_ref)),
        )
        expected_refs = [record.instance_ref for record in self.expected_records]
        replacement_refs = [record.instance_ref for record in self.replacement_records]
        if len(expected_refs) != len(set(expected_refs)):
            raise ShieldValidationError("expected_records 包含重复 instance_ref")
        if len(replacement_refs) != len(set(replacement_refs)):
            raise ShieldValidationError("replacement_records 包含重复 instance_ref")


@dataclass(frozen=True, slots=True)
class ShieldAbsorptionPlan:
    damage_id: str
    frame: int
    target_ref: AttributeSubjectRef
    operation_id: str
    expected_store_version: int
    expected_records: tuple[ShieldRecord, ...]
    replacement_records: tuple[ShieldRecord, ...]
    result: ShieldAbsorptionResult
    capacity_changes: tuple[ShieldCapacityChangeResult, ...]
    removals: tuple[ShieldRemovalResult, ...]

    def __post_init__(self) -> None:
        validate_non_empty_text(self.damage_id, "damage_id")
        validate_character_ref(self.target_ref, "target_ref")
        if not isinstance(self.result, ShieldAbsorptionResult):
            raise ShieldValidationError("result 必须是 ShieldAbsorptionResult")
        if (
            self.result.damage_id != self.damage_id
            or self.result.frame != self.frame
            or self.result.target_ref != self.target_ref
        ):
            raise ShieldValidationError("ShieldAbsorptionPlan 与 result 身份不一致")
        object.__setattr__(self, "capacity_changes", tuple(self.capacity_changes))
        object.__setattr__(self, "removals", tuple(self.removals))
        normalized = ShieldMutationPlan(
            operation_id=self.operation_id,
            frame=self.frame,
            expected_store_version=self.expected_store_version,
            expected_records=self.expected_records,
            replacement_records=self.replacement_records,
        )
        object.__setattr__(self, "expected_records", normalized.expected_records)
        object.__setattr__(self, "replacement_records", normalized.replacement_records)


@dataclass(frozen=True, slots=True)
class ShieldCommitReceipt:
    plan: ShieldAbsorptionPlan


def normalize_capacity_after(value: float) -> float:
    normalized = normalize_shield_zero(value)
    if normalized < 0:
        raise ShieldCapacityError("护盾剩余容量不能为负数")
    return normalized


def _subject_ref_to_dict(ref: AttributeSubjectRef) -> dict[str, str]:
    return {"kind": ref.kind.value, "entity_id": ref.entity_id}


def _runtime_source_ref_to_dict(ref: RuntimeSourceRef) -> dict[str, str | None]:
    return {
        "kind": ref.kind.value,
        "source_key": ref.source_key,
        "instance_id": ref.instance_id,
    }


def _attribute_resolution_to_dict(result: AttributeResolution) -> dict[str, object]:
    return {
        "attribute_key": str(result.attribute_key),
        "subject_ref": _subject_ref_to_dict(result.subject_ref),
        "base_value": result.base_value,
        "final_value": result.final_value,
        "policy_key": result.policy_key,
    }
