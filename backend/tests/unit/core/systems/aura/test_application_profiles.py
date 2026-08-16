from __future__ import annotations

from fractions import Fraction

import pytest

from genshin_sim.core.elements import AuraAmount
from genshin_sim.core.systems.aura import (
    AuraApplicationProfile,
    AuraApplicationProfileRegistry,
    AuraDecayProfilePolicy,
    AuraLossPolicy,
    AuraStrength,
    regular_application_duration,
)
from genshin_sim.core.systems.aura.profiles import profile_for


def test_application_profile_registry_resolves_regular_decay_from_raw_amount():
    profile = AuraApplicationProfile(
        profile_key="aura_application_profile.test.generated",
        decay_profile_policy=AuraDecayProfilePolicy.REGULAR_FROM_RAW_AMOUNT,
        loss_policy=AuraLossPolicy.STANDARD_20_PERCENT,
    )
    registry = AuraApplicationProfileRegistry((profile,))

    assert registry.require(profile.profile_key) is profile
    resolved = profile.resolve_decay_profile(
        base_strength=AuraStrength.WEAK,
        effective_raw_amount=AuraAmount(Fraction(11, 5)),
    )
    assert resolved.strength is None
    assert resolved.attached_amount == AuraAmount(Fraction(44, 25))
    assert resolved.decay_per_second == AuraAmount(Fraction(88, 625))


@pytest.mark.parametrize(
    ("raw_amount", "duration", "decay_per_second"),
    (
        (Fraction(11, 5), Fraction(25, 2), Fraction(88, 625)),
        (Fraction(39, 20), Fraction(95, 8), Fraction(312, 2375)),
        (Fraction(69, 20), Fraction(125, 8), Fraction(552, 3125)),
    ),
)
def test_regular_decay_formula_supports_nonstandard_emitted_amounts(
    raw_amount: Fraction,
    duration: Fraction,
    decay_per_second: Fraction,
):
    resolved = AuraApplicationProfile(
        profile_key="aura_application_profile.test.regular",
        decay_profile_policy=AuraDecayProfilePolicy.REGULAR_FROM_RAW_AMOUNT,
    ).resolve_decay_profile(
        base_strength=AuraStrength.WEAK,
        effective_raw_amount=AuraAmount(raw_amount),
    )

    assert regular_application_duration(AuraAmount(raw_amount)) == duration
    assert resolved.attached_amount == AuraAmount(raw_amount * Fraction(4, 5))
    assert resolved.decay_per_second == AuraAmount(decay_per_second)


def test_standard_medium_profile_uses_the_regular_decay_formula():
    profile = profile_for(AuraStrength.MEDIUM)

    assert regular_application_duration(profile.raw_amount) == Fraction(43, 4)
    assert profile.decay_per_second == AuraAmount(Fraction(24, 215))


def test_application_profile_registry_rejects_unknown_profile_key():
    registry = AuraApplicationProfileRegistry()

    with pytest.raises(ValueError, match="缺少 Aura application profile"):
        registry.require("aura_application_profile.unknown")
