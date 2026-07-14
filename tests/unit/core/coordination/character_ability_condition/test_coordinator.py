from dataclasses import dataclass
from typing import cast

import pytest

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.coordination.character_ability_condition import (
    AbilityConditionBlockingReason,
    AbilityConditionDelegation,
    CharacterAbilityConditionCoordinator,
    CharacterAbilityConditionQuery,
    CharacterAbilityConditionResult,
    CharacterAbilityConditionValidationError,
)
from genshin_sim.core.systems.cooldown import (
    AbilityKind,
    CooldownConditionReason,
    CooldownConditionResult,
    CooldownKey,
    CooldownQuery,
    CooldownSubjectRef,
    CooldownView,
)
from genshin_sim.core.systems.energy import (
    BurstEnergyConditionResult,
    BurstEnergyConditionStatus,
)


@dataclass
class _CooldownPort:
    kind: AbilityKind
    ready: bool
    calls: int = 0

    def query_condition(self, query: CooldownQuery) -> CooldownConditionResult:
        self.calls += 1
        return CooldownConditionResult(
            query,
            self.ready,
            CooldownConditionReason.CHARGE_AVAILABLE
            if self.ready
            else CooldownConditionReason.NO_AVAILABLE_CHARGE,
            CooldownView(query.key, self.kind, 1, int(self.ready), None, 0, 0, None, 0),
        )


@dataclass
class _EnergyPort:
    status: BurstEnergyConditionStatus
    calls: int = 0

    def query_burst_condition(
        self, character_ref: AttributeSubjectRef, frame: int
    ) -> BurstEnergyConditionResult:
        self.calls += 1
        capacity = 0 if self.status is BurstEnergyConditionStatus.NONSTANDARD_RESOURCE else 60
        current = 60 if self.status is BurstEnergyConditionStatus.READY else 0
        return BurstEnergyConditionResult(character_ref, frame, self.status, current, capacity)


def test_skill_only_queries_cooldown_and_preserves_blocking_reason():
    cooldown = _CooldownPort(AbilityKind.ELEMENTAL_SKILL, False)
    energy = _EnergyPort(BurstEnergyConditionStatus.READY)
    result = CharacterAbilityConditionCoordinator(cooldown, energy).evaluate(
        CharacterAbilityConditionQuery(20, "character:slot_1", "elemental_skill")
    )

    assert not result.shared_conditions_satisfied
    assert result.blocking_reasons == (AbilityConditionBlockingReason.COOLDOWN_UNAVAILABLE,)
    assert result.burst_energy_condition is None
    assert energy.calls == 0


def test_burst_collects_both_blockers_without_short_circuiting():
    cooldown = _CooldownPort(AbilityKind.ELEMENTAL_BURST, False)
    energy = _EnergyPort(BurstEnergyConditionStatus.INSUFFICIENT_ENERGY)
    result = CharacterAbilityConditionCoordinator(cooldown, energy).evaluate(
        CharacterAbilityConditionQuery(20, "character:slot_1", "elemental_burst")
    )

    assert result.blocking_reasons == (
        AbilityConditionBlockingReason.COOLDOWN_UNAVAILABLE,
        AbilityConditionBlockingReason.STANDARD_ENERGY_UNAVAILABLE,
    )
    assert energy.calls == 1


def test_nonstandard_burst_delegates_private_resource_without_standard_energy_blocker():
    result = CharacterAbilityConditionCoordinator(
        _CooldownPort(AbilityKind.ELEMENTAL_BURST, True),
        _EnergyPort(BurstEnergyConditionStatus.NONSTANDARD_RESOURCE),
    ).evaluate(CharacterAbilityConditionQuery(20, "character:slot_1", "elemental_burst"))

    assert result.shared_conditions_satisfied
    assert result.blocking_reasons == ()
    assert result.delegated_conditions == (AbilityConditionDelegation.CONTENT_PRIVATE_RESOURCE,)


def test_result_rejects_cross_field_evidence_that_cannot_satisfy_contract():
    query = CharacterAbilityConditionQuery(20, "character:slot_1", "elemental_skill")
    mismatched = _CooldownPort(AbilityKind.ELEMENTAL_SKILL, True).query_condition(
        CooldownQuery(
            CooldownKey(CooldownSubjectRef.character("character:slot_2"), query.ability_key),
            frame=query.frame,
        )
    )

    with pytest.raises(CharacterAbilityConditionValidationError):
        CharacterAbilityConditionResult(
            query,
            AbilityKind.ELEMENTAL_SKILL,
            True,
            mismatched,
            None,
            (),
            (),
        )


def test_result_rejects_string_reason_before_serialization():
    query = CharacterAbilityConditionQuery(20, "character:slot_1", "elemental_skill")
    condition = _CooldownPort(AbilityKind.ELEMENTAL_SKILL, False).query_condition(
        CooldownQuery(
            CooldownKey(CooldownSubjectRef.character(query.character_id), query.ability_key),
            query.frame,
        )
    )

    with pytest.raises(CharacterAbilityConditionValidationError):
        CharacterAbilityConditionResult(
            query,
            AbilityKind.ELEMENTAL_SKILL,
            False,
            condition,
            None,
            cast(tuple[AbilityConditionBlockingReason, ...], ("cooldown_unavailable",)),
            (),
        )
