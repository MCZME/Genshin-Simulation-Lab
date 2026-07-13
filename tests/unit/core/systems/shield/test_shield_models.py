from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from genshin_sim.core.attributes import (
    STAT_HP_MAX,
    AttributeSubjectRef,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.systems.damage import DamageElement
from genshin_sim.core.systems.shield import (
    CharacterIncomingDamage,
    ShieldCapacityFormula,
    ShieldGrantPolicy,
    ShieldNativeMultiplierTerm,
    ShieldPolicyError,
    ShieldProtectionRef,
    ShieldScalingTerm,
    ShieldValidationError,
)

CHARACTER = AttributeSubjectRef.character("character:slot_1")
SOURCE = RuntimeSourceRef(RuntimeSourceKind.CONTENT, "test.shield")


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), float("-inf"), -1.0])
def test_shield_formula_rejects_invalid_numbers(value):
    with pytest.raises(ShieldValidationError):
        ShieldCapacityFormula(flat_absorption=value)


def test_shield_formula_rejects_duplicate_component_and_multiplier_keys():
    with pytest.raises(ShieldValidationError, match="component_key"):
        ShieldCapacityFormula(
            scaling_terms=(
                ShieldScalingTerm("hp", STAT_HP_MAX, 0.1),
                ShieldScalingTerm("hp", STAT_HP_MAX, 0.2),
            )
        )
    with pytest.raises(ShieldValidationError, match="multiplier_key"):
        ShieldCapacityFormula(
            flat_absorption=1,
            native_multipliers=(
                ShieldNativeMultiplierTerm("mode", 1.2, SOURCE),
                ShieldNativeMultiplierTerm("mode", 1.3, SOURCE),
            ),
        )


def test_grant_policy_requires_capacity_limit_only_for_capped_refresh(make_grant):
    with pytest.raises(ShieldPolicyError):
        make_grant(grant_policy=ShieldGrantPolicy.ADD_CAPPED_REFRESH)
    with pytest.raises(ShieldPolicyError):
        make_grant(
            grant_policy=ShieldGrantPolicy.REPLACE,
            capacity_limit=4_000,
        )

    request = make_grant(
        grant_policy=ShieldGrantPolicy.ADD_CAPPED_REFRESH,
        capacity_limit=4_000,
    )
    assert request.capacity_limit_formula is not None


@pytest.mark.parametrize("value", [True, -1, float("nan"), float("inf")])
def test_incoming_damage_rejects_invalid_mitigated_amount(value):
    with pytest.raises(ShieldValidationError):
        CharacterIncomingDamage(
            damage_id="damage:1",
            frame=1,
            protection_ref=ShieldProtectionRef.active_team(),
            target_ref=CHARACTER,
            mitigated_amount=value,
            element=DamageElement.PYRO,
        )


def test_models_are_immutable_and_serialize_stable_tags(make_grant):
    request = make_grant()
    with pytest.raises(FrozenInstanceError):
        request.frame = 2

    incoming = CharacterIncomingDamage(
        damage_id="damage:1",
        frame=1,
        protection_ref=ShieldProtectionRef.active_team(),
        target_ref=CHARACTER,
        mitigated_amount=100,
        element=DamageElement.PYRO,
        tags=frozenset({"z", "a"}),
    )
    assert incoming.to_dict()["tags"] == ("a", "z")
