"""角色生命变化请求与结果模型。"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum

from genshin_sim.core.attributes import (
    AttributeSubjectKind,
    AttributeSubjectRef,
    RuntimeSourceRef,
)
from genshin_sim.core.systems.health.errors import HealthValidationError


class HealthChangeKind(StrEnum):
    DAMAGE = "damage"
    HEALING = "healing"
    HP_DEDUCTION = "hp_deduction"


def validate_health_float(value: float | int, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise HealthValidationError(f"{field_name} 必须是数字")
    result = float(value)
    if not math.isfinite(result):
        raise HealthValidationError(f"{field_name} 必须是有限数字")
    if result == 0.0:
        return 0.0
    return result


def validate_non_negative_health_float(value: float | int, field_name: str) -> float:
    result = validate_health_float(value, field_name)
    if result < 0:
        raise HealthValidationError(f"{field_name} 不能为负数")
    return result


def _validate_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise HealthValidationError(f"{field_name} 必须是非空字符串")


def _validate_frame(frame: int) -> None:
    if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
        raise HealthValidationError("frame 必须是非负整数")


def _validate_character_target(target_ref: AttributeSubjectRef) -> None:
    if target_ref.kind is not AttributeSubjectKind.CHARACTER:
        raise HealthValidationError("生命变化目标必须是角色主体")


def _normalize_tags(tags: frozenset[str]) -> frozenset[str]:
    normalized = frozenset(tags)
    for tag in normalized:
        _validate_non_empty_text(tag, "生命变化标签")
    return normalized


@dataclass(frozen=True, slots=True)
class CharacterDamageApplication:
    change_id: str
    frame: int
    target_ref: AttributeSubjectRef
    amount: float
    source_ref: AttributeSubjectRef | None = None
    source_context: RuntimeSourceRef | None = None
    tags: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        _validate_non_empty_text(self.change_id, "change_id")
        _validate_frame(self.frame)
        _validate_character_target(self.target_ref)
        object.__setattr__(
            self,
            "amount",
            validate_non_negative_health_float(self.amount, "amount"),
        )
        object.__setattr__(self, "tags", _normalize_tags(self.tags))


@dataclass(frozen=True, slots=True)
class CharacterHealingApplication:
    change_id: str
    frame: int
    target_ref: AttributeSubjectRef
    amount: float
    source_ref: AttributeSubjectRef | None = None
    source_context: RuntimeSourceRef | None = None
    tags: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        _validate_non_empty_text(self.change_id, "change_id")
        _validate_frame(self.frame)
        _validate_character_target(self.target_ref)
        object.__setattr__(
            self,
            "amount",
            validate_non_negative_health_float(self.amount, "amount"),
        )
        object.__setattr__(self, "tags", _normalize_tags(self.tags))


@dataclass(frozen=True, slots=True)
class CharacterHpDeduction:
    change_id: str
    frame: int
    target_ref: AttributeSubjectRef
    amount: float
    minimum_remaining_hp: float
    source_ref: AttributeSubjectRef | None = None
    source_context: RuntimeSourceRef | None = None
    tags: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        _validate_non_empty_text(self.change_id, "change_id")
        _validate_frame(self.frame)
        _validate_character_target(self.target_ref)
        object.__setattr__(
            self,
            "amount",
            validate_non_negative_health_float(self.amount, "amount"),
        )
        object.__setattr__(
            self,
            "minimum_remaining_hp",
            validate_non_negative_health_float(self.minimum_remaining_hp, "minimum_remaining_hp"),
        )
        object.__setattr__(self, "tags", _normalize_tags(self.tags))


@dataclass(frozen=True, slots=True)
class CharacterHealthChangeResult:
    change_id: str
    frame: int
    change_kind: HealthChangeKind
    target_ref: AttributeSubjectRef
    source_ref: AttributeSubjectRef | None
    requested_amount: float
    effective_amount: float
    unapplied_amount: float
    hp_before: float
    hp_after: float
    max_hp: float
    minimum_remaining_hp: float | None = None
    source_context: RuntimeSourceRef | None = None
    tags: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        _validate_non_empty_text(self.change_id, "change_id")
        _validate_frame(self.frame)
        if not isinstance(self.change_kind, HealthChangeKind):
            raise HealthValidationError("change_kind 不受支持")
        _validate_character_target(self.target_ref)
        for field_name in (
            "requested_amount",
            "effective_amount",
            "unapplied_amount",
            "hp_before",
            "hp_after",
        ):
            object.__setattr__(
                self,
                field_name,
                validate_non_negative_health_float(getattr(self, field_name), field_name),
            )
        max_hp = validate_health_float(self.max_hp, "max_hp")
        if max_hp <= 0:
            raise HealthValidationError("max_hp 必须是正数")
        object.__setattr__(self, "max_hp", max_hp)
        if self.minimum_remaining_hp is not None:
            object.__setattr__(
                self,
                "minimum_remaining_hp",
                validate_non_negative_health_float(
                    self.minimum_remaining_hp,
                    "minimum_remaining_hp",
                ),
            )
        if not math.isclose(
            self.requested_amount,
            self.effective_amount + self.unapplied_amount,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise HealthValidationError(
                "requested_amount 必须等于 effective_amount + unapplied_amount"
            )
        object.__setattr__(self, "tags", _normalize_tags(self.tags))

    def to_dict(self) -> dict[str, object]:
        source_ref = None
        if self.source_ref is not None:
            source_ref = _subject_ref_to_dict(self.source_ref)
        source_context = None
        if self.source_context is not None:
            source_context = _runtime_source_ref_to_dict(self.source_context)
        return {
            "change_id": self.change_id,
            "frame": self.frame,
            "change_kind": self.change_kind.value,
            "target_ref": _subject_ref_to_dict(self.target_ref),
            "source_ref": source_ref,
            "source_context": source_context,
            "requested_amount": self.requested_amount,
            "effective_amount": self.effective_amount,
            "unapplied_amount": self.unapplied_amount,
            "hp_before": self.hp_before,
            "hp_after": self.hp_after,
            "max_hp": self.max_hp,
            "minimum_remaining_hp": self.minimum_remaining_hp,
            "tags": tuple(sorted(self.tags)),
        }


@dataclass(frozen=True, slots=True)
class CharacterMaxHpReconcileResult:
    frame: int
    target_ref: AttributeSubjectRef
    old_max_hp: float
    new_max_hp: float
    hp_before: float
    hp_after: float

    def __post_init__(self) -> None:
        _validate_frame(self.frame)
        _validate_character_target(self.target_ref)
        for field_name in ("old_max_hp", "new_max_hp", "hp_before", "hp_after"):
            object.__setattr__(
                self,
                field_name,
                validate_non_negative_health_float(getattr(self, field_name), field_name),
            )
        if self.old_max_hp <= 0 or self.new_max_hp <= 0:
            raise HealthValidationError("old_max_hp 和 new_max_hp 必须是正数")

    def to_dict(self) -> dict[str, object]:
        return {
            "frame": self.frame,
            "target_ref": _subject_ref_to_dict(self.target_ref),
            "old_max_hp": self.old_max_hp,
            "new_max_hp": self.new_max_hp,
            "hp_before": self.hp_before,
            "hp_after": self.hp_after,
        }


def _subject_ref_to_dict(ref: AttributeSubjectRef) -> dict[str, str]:
    return {"kind": ref.kind.value, "entity_id": ref.entity_id}


def _runtime_source_ref_to_dict(ref: RuntimeSourceRef) -> dict[str, str | None]:
    return {
        "kind": ref.kind.value,
        "source_key": ref.source_key,
        "instance_id": ref.instance_id,
    }
