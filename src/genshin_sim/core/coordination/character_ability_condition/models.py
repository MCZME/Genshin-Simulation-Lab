from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from genshin_sim.core.attributes import AttributeSubjectKind
from genshin_sim.core.coordination.character_ability_condition.errors import (
    CharacterAbilityConditionValidationError,
)
from genshin_sim.core.systems.cooldown import AbilityKind, CooldownConditionResult
from genshin_sim.core.systems.energy import (
    BurstEnergyConditionResult,
    BurstEnergyConditionStatus,
)


class AbilityConditionBlockingReason(StrEnum):
    COOLDOWN_UNAVAILABLE = "cooldown_unavailable"
    STANDARD_ENERGY_UNAVAILABLE = "standard_energy_unavailable"


class AbilityConditionDelegation(StrEnum):
    CONTENT_PRIVATE_RESOURCE = "content_private_resource"


@dataclass(frozen=True, slots=True)
class CharacterAbilityConditionQuery:
    frame: int
    character_id: str
    ability_key: str

    def __post_init__(self) -> None:
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise CharacterAbilityConditionValidationError("frame 必须是非负整数")
        for name in ("character_id", "ability_key"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or value != value.strip():
                raise CharacterAbilityConditionValidationError(
                    f"{name} 必须是非空且无首尾空白的字符串"
                )


@dataclass(frozen=True, slots=True)
class CharacterAbilityConditionResult:
    query: CharacterAbilityConditionQuery
    ability_kind: AbilityKind
    shared_conditions_satisfied: bool
    cooldown_condition: CooldownConditionResult
    burst_energy_condition: BurstEnergyConditionResult | None
    blocking_reasons: tuple[AbilityConditionBlockingReason, ...]
    delegated_conditions: tuple[AbilityConditionDelegation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.query, CharacterAbilityConditionQuery):
            raise CharacterAbilityConditionValidationError(
                "query 必须是 CharacterAbilityConditionQuery"
            )
        if not isinstance(self.ability_kind, AbilityKind):
            raise CharacterAbilityConditionValidationError("ability_kind 不受支持")
        condition_query = self.cooldown_condition.query
        condition_key = condition_query.key
        if (
            condition_key.subject.subject_id != self.query.character_id
            or condition_key.ability_key != self.query.ability_key
            or condition_query.frame != self.query.frame
        ):
            raise CharacterAbilityConditionValidationError("冷却条件证据与公共查询不一致")
        if self.cooldown_condition.view.key != condition_key:
            raise CharacterAbilityConditionValidationError("冷却条件 view key 与 query 不一致")
        if self.ability_kind is not self.cooldown_condition.view.ability_kind:
            raise CharacterAbilityConditionValidationError("ability_kind 与冷却条件证据不一致")

        blocking = tuple(self.blocking_reasons)
        delegations = tuple(self.delegated_conditions)
        if not all(isinstance(item, AbilityConditionBlockingReason) for item in blocking):
            raise CharacterAbilityConditionValidationError(
                "blocking_reasons 必须由 AbilityConditionBlockingReason 构成"
            )
        if not all(isinstance(item, AbilityConditionDelegation) for item in delegations):
            raise CharacterAbilityConditionValidationError(
                "delegated_conditions 必须由 AbilityConditionDelegation 构成"
            )
        ordered_blocking = tuple(
            item
            for item in (
                AbilityConditionBlockingReason.COOLDOWN_UNAVAILABLE,
                AbilityConditionBlockingReason.STANDARD_ENERGY_UNAVAILABLE,
            )
            if item in blocking
        )
        if blocking != ordered_blocking:
            raise CharacterAbilityConditionValidationError("blocking_reasons 必须去重并按固定顺序")
        ordered_delegations = tuple(
            item
            for item in (AbilityConditionDelegation.CONTENT_PRIVATE_RESOURCE,)
            if item in delegations
        )
        if delegations != ordered_delegations:
            raise CharacterAbilityConditionValidationError(
                "delegated_conditions 必须去重并按固定顺序"
            )
        expected_blocking: list[AbilityConditionBlockingReason] = []
        if not self.cooldown_condition.satisfied:
            expected_blocking.append(AbilityConditionBlockingReason.COOLDOWN_UNAVAILABLE)

        if self.ability_kind is AbilityKind.ELEMENTAL_SKILL:
            if self.burst_energy_condition is not None:
                raise CharacterAbilityConditionValidationError("元素战技不能携带爆发能量条件")
            evidence_delegations: tuple[AbilityConditionDelegation, ...] = ()
        else:
            energy = self.burst_energy_condition
            if energy is None:
                raise CharacterAbilityConditionValidationError("元素爆发必须携带爆发能量条件")
            if (
                energy.character_ref.kind is not AttributeSubjectKind.CHARACTER
                or energy.character_ref.entity_id != self.query.character_id
                or energy.frame != self.query.frame
            ):
                raise CharacterAbilityConditionValidationError("爆发能量条件证据与公共查询不一致")
            if energy.status is BurstEnergyConditionStatus.INSUFFICIENT_ENERGY:
                expected_blocking.append(AbilityConditionBlockingReason.STANDARD_ENERGY_UNAVAILABLE)
                evidence_delegations = ()
            elif energy.status is BurstEnergyConditionStatus.NONSTANDARD_RESOURCE:
                evidence_delegations = (AbilityConditionDelegation.CONTENT_PRIVATE_RESOURCE,)
            else:
                evidence_delegations = ()

        if blocking != tuple(expected_blocking):
            raise CharacterAbilityConditionValidationError("blocking_reasons 与领域条件证据不一致")
        if delegations != evidence_delegations:
            raise CharacterAbilityConditionValidationError(
                "delegated_conditions 与领域条件证据不一致"
            )
        if self.shared_conditions_satisfied != (not expected_blocking):
            raise CharacterAbilityConditionValidationError(
                "shared_conditions_satisfied 与阻塞原因不一致"
            )
        object.__setattr__(self, "blocking_reasons", blocking)
        object.__setattr__(self, "delegated_conditions", delegations)

    def to_dict(self) -> dict[str, object]:
        return {
            "query": {
                "frame": self.query.frame,
                "character_id": self.query.character_id,
                "ability_key": self.query.ability_key,
            },
            "ability_kind": self.ability_kind.value,
            "shared_conditions_satisfied": self.shared_conditions_satisfied,
            "blocking_reasons": tuple(item.value for item in self.blocking_reasons),
            "delegated_conditions": tuple(item.value for item in self.delegated_conditions),
        }
