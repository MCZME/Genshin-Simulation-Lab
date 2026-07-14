"""元素能量领域的稳定模型。"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum

from genshin_sim.core.attributes import AttributeSubjectKind, AttributeSubjectRef, RuntimeSourceRef
from genshin_sim.core.systems.energy.errors import (
    EnergyValidationError,
    UnsupportedEnergyElementError,
    UnsupportedEnergySubjectError,
)


class EnergyElement(StrEnum):
    PYRO = "pyro"
    HYDRO = "hydro"
    ELECTRO = "electro"
    CRYO = "cryo"
    ANEMO = "anemo"
    GEO = "geo"
    DENDRO = "dendro"
    CLEAR = "clear"


class EnergyPickupKind(StrEnum):
    PARTICLE = "particle"
    ORB = "orb"


class EnergyChangeKind(StrEnum):
    PICKUP_RESTORE = "pickup_restore"
    DIRECT_RESTORE = "direct_restore"
    DIRECT_DRAIN = "direct_drain"
    BURST_SPEND = "burst_spend"


class EnergyRecipientStatus(StrEnum):
    APPLIED = "applied"
    CAPPED = "capped"
    NO_ELEMENTAL_ENERGY_RESOURCE = "no_elemental_energy_resource"


def validate_energy_float(value: float | int, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise EnergyValidationError(f"{field_name} 必须是数字")
    result = float(value)
    if not math.isfinite(result):
        raise EnergyValidationError(f"{field_name} 必须是有限数字")
    return 0.0 if result == 0.0 else result


def validate_non_negative_energy_float(value: float | int, field_name: str) -> float:
    result = validate_energy_float(value, field_name)
    if result < 0:
        raise EnergyValidationError(f"{field_name} 不能为负数")
    return result


def validate_frame(frame: int) -> None:
    if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
        raise EnergyValidationError("frame 必须是非负整数")


def validate_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise EnergyValidationError(f"{field_name} 必须是非空字符串")


def validate_character_ref(ref: AttributeSubjectRef) -> None:
    if not isinstance(ref, AttributeSubjectRef) or ref.kind is not AttributeSubjectKind.CHARACTER:
        raise UnsupportedEnergySubjectError("元素能量系统只支持角色主体")


def normalize_tags(tags: frozenset[str] | tuple[str, ...] | list[str]) -> frozenset[str]:
    result = frozenset(tags)
    for tag in result:
        validate_text(tag, "元素能量标签")
    return result


@dataclass(frozen=True, slots=True)
class CharacterEnergyProfile:
    character_ref: AttributeSubjectRef
    character_key: str
    element: EnergyElement
    capacity: float

    def __post_init__(self) -> None:
        validate_character_ref(self.character_ref)
        validate_text(self.character_key, "character_key")
        if not isinstance(self.element, EnergyElement) or self.element is EnergyElement.CLEAR:
            raise UnsupportedEnergyElementError("角色元素必须是七种元素之一")
        object.__setattr__(
            self, "capacity", validate_non_negative_energy_float(self.capacity, "capacity")
        )


@dataclass(frozen=True, slots=True)
class SpawnEnergyPickupRequest:
    request_id: str
    frame: int
    pickup_kind: EnergyPickupKind
    element: EnergyElement
    count: int
    travel_frames: int
    source_ref: AttributeSubjectRef | None = None
    source_context: RuntimeSourceRef | None = None
    tags: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        validate_text(self.request_id, "request_id")
        validate_frame(self.frame)
        if not isinstance(self.pickup_kind, EnergyPickupKind):
            raise EnergyValidationError("pickup_kind 不受支持")
        if not isinstance(self.element, EnergyElement):
            raise UnsupportedEnergyElementError("pickup element 不受支持")
        if isinstance(self.count, bool) or not isinstance(self.count, int) or self.count <= 0:
            raise EnergyValidationError("count 必须是正整数")
        if (
            isinstance(self.travel_frames, bool)
            or not isinstance(self.travel_frames, int)
            or self.travel_frames < 0
        ):
            raise EnergyValidationError("travel_frames 必须是非负整数")
        object.__setattr__(self, "tags", normalize_tags(self.tags))


@dataclass(frozen=True, slots=True)
class RestoreEnergyRequest:
    change_id: str
    frame: int
    target_ref: AttributeSubjectRef
    amount: float
    source_ref: AttributeSubjectRef | None = None
    source_context: RuntimeSourceRef | None = None
    tags: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        validate_text(self.change_id, "change_id")
        validate_frame(self.frame)
        validate_character_ref(self.target_ref)
        object.__setattr__(
            self, "amount", validate_non_negative_energy_float(self.amount, "amount")
        )
        object.__setattr__(self, "tags", normalize_tags(self.tags))


@dataclass(frozen=True, slots=True)
class DrainEnergyRequest(RestoreEnergyRequest):
    pass


@dataclass(frozen=True, slots=True)
class SpendBurstEnergyRequest:
    change_id: str
    frame: int
    target_ref: AttributeSubjectRef
    action_instance_id: str
    source_context: RuntimeSourceRef | None = None
    tags: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        validate_text(self.change_id, "change_id")
        validate_frame(self.frame)
        validate_character_ref(self.target_ref)
        validate_text(self.action_instance_id, "action_instance_id")
        object.__setattr__(self, "tags", normalize_tags(self.tags))


@dataclass(frozen=True, slots=True)
class EnergyPickupRecord:
    pickup_id: str
    request_id: str
    created_frame: int
    settle_frame: int
    pickup_kind: EnergyPickupKind
    element: EnergyElement
    count: int
    source_ref: AttributeSubjectRef | None
    source_context: RuntimeSourceRef | None
    tags: frozenset[str]
    spawn_order: int

    def __post_init__(self) -> None:
        validate_text(self.pickup_id, "pickup_id")
        validate_text(self.request_id, "request_id")
        validate_frame(self.created_frame)
        validate_frame(self.settle_frame)
        if self.settle_frame < self.created_frame:
            raise EnergyValidationError("settle_frame 不能早于 created_frame")
        if not isinstance(self.pickup_kind, EnergyPickupKind):
            raise EnergyValidationError("pickup_kind 不受支持")
        if not isinstance(self.element, EnergyElement):
            raise UnsupportedEnergyElementError("pickup element 不受支持")
        if isinstance(self.count, bool) or not isinstance(self.count, int) or self.count <= 0:
            raise EnergyValidationError("count 必须是正整数")
        if (
            isinstance(self.spawn_order, bool)
            or not isinstance(self.spawn_order, int)
            or self.spawn_order < 0
        ):
            raise EnergyValidationError("spawn_order 必须是非负整数")
        object.__setattr__(self, "tags", normalize_tags(self.tags))

    @property
    def sort_key(self) -> tuple[int, int, int, str]:
        return (self.settle_frame, self.created_frame, self.spawn_order, self.pickup_id)

    def to_dict(self) -> dict[str, object]:
        return {
            "pickup_id": self.pickup_id,
            "request_id": self.request_id,
            "created_frame": self.created_frame,
            "settle_frame": self.settle_frame,
            "pickup_kind": self.pickup_kind.value,
            "element": self.element.value,
            "count": self.count,
            "source_ref": _subject_dict(self.source_ref),
            "source_context": _source_dict(self.source_context),
            "tags": tuple(sorted(self.tags)),
            "spawn_order": self.spawn_order,
        }


@dataclass(frozen=True, slots=True)
class CharacterEnergyChangeResult:
    change_id: str
    frame: int
    change_kind: EnergyChangeKind
    target_ref: AttributeSubjectRef
    source_ref: AttributeSubjectRef | None
    source_context: RuntimeSourceRef | None
    requested_amount: float
    effective_amount: float
    unapplied_amount: float
    energy_before: float
    energy_after: float
    capacity: float
    tags: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        validate_text(self.change_id, "change_id")
        validate_frame(self.frame)
        if not isinstance(self.change_kind, EnergyChangeKind):
            raise EnergyValidationError("change_kind 不受支持")
        validate_character_ref(self.target_ref)
        for name in (
            "requested_amount",
            "effective_amount",
            "unapplied_amount",
            "energy_before",
            "energy_after",
            "capacity",
        ):
            object.__setattr__(
                self, name, validate_non_negative_energy_float(getattr(self, name), name)
            )
        if self.energy_before > self.capacity or self.energy_after > self.capacity:
            raise EnergyValidationError("当前能量不能超过 capacity")
        if not math.isclose(
            self.requested_amount,
            self.effective_amount + self.unapplied_amount,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise EnergyValidationError(
                "requested_amount 必须等于 effective_amount + unapplied_amount"
            )
        object.__setattr__(self, "tags", normalize_tags(self.tags))

    @property
    def delta(self) -> float:
        return self.energy_after - self.energy_before

    def to_dict(self) -> dict[str, object]:
        return {
            "change_id": self.change_id,
            "frame": self.frame,
            "change_kind": self.change_kind.value,
            "target_ref": _subject_dict(self.target_ref),
            "source_ref": _subject_dict(self.source_ref),
            "source_context": _source_dict(self.source_context),
            "requested_amount": self.requested_amount,
            "effective_amount": self.effective_amount,
            "unapplied_amount": self.unapplied_amount,
            "energy_before": self.energy_before,
            "energy_after": self.energy_after,
            "capacity": self.capacity,
            "delta": self.delta,
            "tags": tuple(sorted(self.tags)),
        }


@dataclass(frozen=True, slots=True)
class EnergyRecipientResolution:
    target_ref: AttributeSubjectRef
    slot: int
    status: EnergyRecipientStatus
    is_active: bool
    character_element: EnergyElement
    pickup_element: EnergyElement
    pickup_kind: EnergyPickupKind
    count: int
    kind_multiplier: float
    element_multiplier: float
    field_multiplier: float
    recharge_bonus: float | None
    recharge_multiplier: float | None
    base_amount: float
    requested_amount: float
    change_result: CharacterEnergyChangeResult | None

    def to_dict(self) -> dict[str, object]:
        return {
            "target_ref": _subject_dict(self.target_ref),
            "slot": self.slot,
            "status": self.status.value,
            "is_active": self.is_active,
            "character_element": self.character_element.value,
            "pickup_element": self.pickup_element.value,
            "pickup_kind": self.pickup_kind.value,
            "count": self.count,
            "kind_multiplier": self.kind_multiplier,
            "element_multiplier": self.element_multiplier,
            "field_multiplier": self.field_multiplier,
            "recharge_bonus": self.recharge_bonus,
            "recharge_multiplier": self.recharge_multiplier,
            "base_amount": self.base_amount,
            "requested_amount": self.requested_amount,
            "change_result": None if self.change_result is None else self.change_result.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class EnergyPickupSettlementResult:
    pickup: EnergyPickupRecord
    settled_frame: int
    active_slot: int
    team_size: int
    recipients: tuple[EnergyRecipientResolution, ...]

    def __post_init__(self) -> None:
        validate_frame(self.settled_frame)
        object.__setattr__(
            self, "recipients", tuple(sorted(self.recipients, key=lambda item: item.slot))
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "pickup": self.pickup.to_dict(),
            "settled_frame": self.settled_frame,
            "active_slot": self.active_slot,
            "team_size": self.team_size,
            "recipients": tuple(item.to_dict() for item in self.recipients),
        }


def _subject_dict(ref: AttributeSubjectRef | None) -> dict[str, str] | None:
    return None if ref is None else {"kind": ref.kind.value, "entity_id": ref.entity_id}


def _source_dict(ref: RuntimeSourceRef | None) -> dict[str, str | None] | None:
    return (
        None
        if ref is None
        else {"kind": ref.kind.value, "source_key": ref.source_key, "instance_id": ref.instance_id}
    )
