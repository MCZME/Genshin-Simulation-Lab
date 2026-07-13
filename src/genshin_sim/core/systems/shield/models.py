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
from genshin_sim.core.systems.health import (
    CharacterDamageApplication,
    CharacterHealthChangeResult,
)
from genshin_sim.core.systems.shield.enums import (
    ShieldChangeReason,
    ShieldElement,
    ShieldGrantOutcome,
    ShieldGrantPolicy,
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
    grants_interruption_resistance: bool = False
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
        if not isinstance(self.grants_interruption_resistance, bool):
            raise ShieldValidationError("grants_interruption_resistance 必须是布尔值")
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


@dataclass(frozen=True, slots=True)
class ShieldComponent:
    instance_id: int
    mechanic_key: str
    handler_key: str
    protection_ref: ShieldProtectionRef
    creator_ref: AttributeSubjectRef
    source_context: RuntimeSourceRef
    element: ShieldElement
    maximum_native_absorption: float
    remaining_native_absorption: float
    conflict_key: str
    grants_interruption_resistance: bool
    grant_snapshot_ref: str
    tags: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        validate_positive_int(self.instance_id, "instance_id")
        for value, name in (
            (self.mechanic_key, "mechanic_key"),
            (self.handler_key, "handler_key"),
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
        if maximum <= 0 or remaining <= 0 or remaining > maximum:
            raise ShieldCapacityError(
                "活动护盾必须满足 0 < remaining_native_absorption <= maximum_native_absorption"
            )
        object.__setattr__(self, "maximum_native_absorption", maximum)
        object.__setattr__(self, "remaining_native_absorption", remaining)
        if not isinstance(self.grants_interruption_resistance, bool):
            raise ShieldValidationError("grants_interruption_resistance 必须是布尔值")
        object.__setattr__(self, "tags", normalize_tags(self.tags))


@dataclass(frozen=True, slots=True)
class ShieldGrantResult:
    resolution: ShieldGrantResolution
    outcome: ShieldGrantOutcome
    instance_id: int
    replaced_instance_id: int | None
    remaining_before: float
    remaining_after: float
    maximum_after: float
    expires_at_before: int | None
    expires_at_after: int

    def __post_init__(self) -> None:
        validate_positive_int(self.instance_id, "instance_id")
        if self.replaced_instance_id is not None:
            validate_positive_int(self.replaced_instance_id, "replaced_instance_id")
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
            "instance_id": self.instance_id,
            "replaced_instance_id": self.replaced_instance_id,
            "remaining_before": self.remaining_before,
            "remaining_after": self.remaining_after,
            "maximum_after": self.maximum_after,
            "expires_at_before": self.expires_at_before,
            "expires_at_after": self.expires_at_after,
        }


@dataclass(frozen=True, slots=True)
class ShieldCapacityChangeResult:
    frame: int
    instance_id: int
    mechanic_key: str
    protection_ref: ShieldProtectionRef
    reason: ShieldChangeReason
    native_before: float
    native_after: float
    maximum_before: float
    maximum_after: float

    def __post_init__(self) -> None:
        validate_frame(self.frame)
        validate_positive_int(self.instance_id, "instance_id")
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
            "instance_id": self.instance_id,
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
    instance_id: int
    mechanic_key: str
    protection_ref: ShieldProtectionRef
    reason: ShieldRemovalReason
    native_remaining: float

    def __post_init__(self) -> None:
        validate_frame(self.frame)
        validate_positive_int(self.instance_id, "instance_id")
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
            "instance_id": self.instance_id,
            "mechanic_key": self.mechanic_key,
            "protection_ref": self.protection_ref.to_dict(),
            "reason": self.reason.value,
            "native_remaining": self.native_remaining,
        }


@dataclass(frozen=True, slots=True)
class CharacterIncomingDamage:
    damage_id: str
    frame: int
    protection_ref: ShieldProtectionRef
    target_ref: AttributeSubjectRef
    mitigated_amount: float
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
            "mitigated_amount",
            validate_non_negative_shield_float(self.mitigated_amount, "mitigated_amount"),
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

    @property
    def amount(self) -> float:
        """兼容调用方术语；语义始终是护盾前减免后的来伤量。"""

        return self.mitigated_amount

    def to_dict(self) -> dict[str, object]:
        return {
            "damage_id": self.damage_id,
            "frame": self.frame,
            "protection_ref": self.protection_ref.to_dict(),
            "target_ref": _subject_ref_to_dict(self.target_ref),
            "mitigated_amount": self.mitigated_amount,
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
    instance_id: int
    mechanic_key: str
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
        validate_positive_int(self.instance_id, "instance_id")
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
            "instance_id": self.instance_id,
            "mechanic_key": self.mechanic_key,
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
    protection_ref: ShieldProtectionRef
    target_ref: AttributeSubjectRef
    mitigated_amount: float
    element: DamageElement
    active_character_shield_strength: float
    shield_hits: tuple[ShieldHitResult, ...]
    protected_damage: float
    health_bound_damage: float
    had_active_shield_before: bool
    has_active_shield_after: bool
    depleted_instance_ids: tuple[int, ...]

    def __post_init__(self) -> None:
        validate_non_empty_text(self.damage_id, "damage_id")
        validate_frame(self.frame)
        validate_character_ref(self.target_ref, "target_ref")
        object.__setattr__(self, "shield_hits", tuple(self.shield_hits))
        object.__setattr__(
            self,
            "depleted_instance_ids",
            tuple(sorted(self.depleted_instance_ids)),
        )
        for field_name in (
            "mitigated_amount",
            "active_character_shield_strength",
            "protected_damage",
            "health_bound_damage",
        ):
            object.__setattr__(
                self,
                field_name,
                validate_shield_float(getattr(self, field_name), field_name),
            )
        if min(self.mitigated_amount, self.protected_damage, self.health_bound_damage) < 0:
            raise ShieldCapacityError("来伤和保护量不能为负数")
        if not math.isclose(
            self.mitigated_amount,
            self.protected_damage + self.health_bound_damage,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise ShieldCapacityError(
                "mitigated_amount 必须等于 protected_damage + health_bound_damage"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "damage_id": self.damage_id,
            "frame": self.frame,
            "protection_ref": self.protection_ref.to_dict(),
            "target_ref": _subject_ref_to_dict(self.target_ref),
            "mitigated_amount": self.mitigated_amount,
            "element": self.element.value,
            "active_character_shield_strength": self.active_character_shield_strength,
            "shield_hits": tuple(hit.to_dict() for hit in self.shield_hits),
            "protected_damage": self.protected_damage,
            "health_bound_damage": self.health_bound_damage,
            "had_active_shield_before": self.had_active_shield_before,
            "has_active_shield_after": self.has_active_shield_after,
            "depleted_instance_ids": self.depleted_instance_ids,
        }


@dataclass(frozen=True, slots=True)
class IncomingDamageApplicationRecord:
    incoming_damage: CharacterIncomingDamage
    shield_result: ShieldAbsorptionResult
    health_application: CharacterDamageApplication
    health_result: CharacterHealthChangeResult

    def to_dict(self) -> dict[str, object]:
        return {
            "incoming_damage": self.incoming_damage.to_dict(),
            "shield_result": self.shield_result.to_dict(),
            "health_application": _health_application_to_dict(self.health_application),
            "health_result": self.health_result.to_dict(),
        }


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


def _health_application_to_dict(
    request: CharacterDamageApplication,
) -> dict[str, object]:
    return {
        "change_id": request.change_id,
        "frame": request.frame,
        "target_ref": _subject_ref_to_dict(request.target_ref),
        "amount": request.amount,
        "source_ref": None
        if request.source_ref is None
        else _subject_ref_to_dict(request.source_ref),
        "source_context": None
        if request.source_context is None
        else _runtime_source_ref_to_dict(request.source_context),
        "tags": tuple(sorted(request.tags)),
    }
