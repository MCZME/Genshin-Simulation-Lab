from __future__ import annotations

import math
from dataclasses import dataclass

from genshin_sim.core.attributes import (
    AttributeSubjectKind,
    AttributeSubjectRef,
    RuntimeSourceRef,
)
from genshin_sim.core.coordination.character_damage_taken.errors import (
    CharacterDamageTakenTargetError,
    CharacterDamageTakenValidationError,
)
from genshin_sim.core.elements import Element
from genshin_sim.core.systems.health import (
    CharacterDamageApplication,
    CharacterDamagePlan,
    CharacterHealthChangeResult,
)
from genshin_sim.core.systems.shield import ShieldAbsorptionPlan, ShieldAbsorptionResult


def _text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise CharacterDamageTakenValidationError(f"{field_name} 必须是非空字符串")


def _subject(ref: AttributeSubjectRef) -> dict[str, str]:
    return {"kind": ref.kind.value, "entity_id": ref.entity_id}


def _source(ref: RuntimeSourceRef) -> dict[str, str | None]:
    return {"kind": ref.kind.value, "source_key": ref.source_key, "instance_id": ref.instance_id}


@dataclass(frozen=True, slots=True)
class CharacterIncomingDamage:
    damage_id: str
    frame: int
    target_ref: AttributeSubjectRef
    amount: float
    element: Element
    source_ref: AttributeSubjectRef | None = None
    source_context: RuntimeSourceRef | None = None
    tags: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        _text(self.damage_id, "damage_id")
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise CharacterDamageTakenValidationError("frame 必须是非负整数")
        if (
            not isinstance(self.target_ref, AttributeSubjectRef)
            or self.target_ref.kind is not AttributeSubjectKind.CHARACTER
        ):
            raise CharacterDamageTakenTargetError("角色受伤目标必须是角色主体")
        if isinstance(self.amount, bool) or not isinstance(self.amount, int | float):
            raise CharacterDamageTakenValidationError("amount 必须是数字")
        amount = float(self.amount)
        if not math.isfinite(amount) or amount < 0:
            raise CharacterDamageTakenValidationError("amount 必须是有限非负数")
        object.__setattr__(self, "amount", 0.0 if amount == 0 else amount)
        if not isinstance(self.element, Element):
            raise CharacterDamageTakenValidationError("element 不受支持")
        if self.source_ref is not None and not isinstance(self.source_ref, AttributeSubjectRef):
            raise CharacterDamageTakenValidationError(
                "source_ref 必须是 AttributeSubjectRef 或 None"
            )
        if self.source_context is not None and not isinstance(
            self.source_context, RuntimeSourceRef
        ):
            raise CharacterDamageTakenValidationError(
                "source_context 必须是 RuntimeSourceRef 或 None"
            )
        tags = frozenset(self.tags)
        for tag in tags:
            _text(tag, "tag")
        object.__setattr__(self, "tags", tags)

    def to_dict(self) -> dict[str, object]:
        return {
            "damage_id": self.damage_id,
            "frame": self.frame,
            "target_ref": _subject(self.target_ref),
            "amount": self.amount,
            "element": self.element.value,
            "source_ref": None if self.source_ref is None else _subject(self.source_ref),
            "source_context": None if self.source_context is None else _source(self.source_context),
            "tags": tuple(sorted(self.tags)),
        }


@dataclass(frozen=True, slots=True)
class CharacterDamageTakenPlan:
    """角色受伤的完整预校验单元，供跨领域协调器一并提交。"""

    incoming_damage: CharacterIncomingDamage
    shield_plan: ShieldAbsorptionPlan
    health_application: CharacterDamageApplication
    health_plan: CharacterDamagePlan


@dataclass(frozen=True, slots=True)
class CharacterDamageTakenRecord:
    incoming_damage: CharacterIncomingDamage
    shield_result: ShieldAbsorptionResult
    health_application: CharacterDamageApplication
    health_result: CharacterHealthChangeResult

    def __post_init__(self) -> None:
        if not math.isclose(
            self.incoming_damage.amount,
            self.shield_result.protected_damage + self.shield_result.health_bound_damage,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise CharacterDamageTakenValidationError("角色来伤记录的护盾分配不守恒")
        if self.health_application.amount != self.shield_result.health_bound_damage:
            raise CharacterDamageTakenValidationError("血量应用量必须等于穿透护盾的伤害")

    def to_dict(self) -> dict[str, object]:
        application = self.health_application
        return {
            "incoming_damage": self.incoming_damage.to_dict(),
            "shield_result": self.shield_result.to_dict(),
            "health_application": {
                "change_id": application.change_id,
                "frame": application.frame,
                "target_ref": _subject(application.target_ref),
                "amount": application.amount,
                "source_ref": None
                if application.source_ref is None
                else _subject(application.source_ref),
                "source_context": None
                if application.source_context is None
                else _source(application.source_context),
                "tags": tuple(sorted(application.tags)),
            },
            "health_result": self.health_result.to_dict(),
        }
