from __future__ import annotations

import math

import pytest

from genshin_sim.core.elements import AuraAmount, ElementalStateLinkRef, ElementalSubjectRef
from genshin_sim.core.systems.reaction import (
    FreezeRecoveryState,
    FreezeResistanceObservation,
    FrozenState,
    ReactionStateInstanceRef,
)
from genshin_sim.core.systems.reaction.mechanics.frozen import (
    active_freeze_decay_rate_at,
    active_frozen_amount_at,
    base_freeze_duration_seconds,
    freeze_duration_frames,
    freeze_duration_seconds,
    freeze_expiry_frame,
    increase_freeze_decay_rate,
    recover_freeze_decay_rate,
    recovered_freeze_decay_rate_at,
)

TARGET = ElementalSubjectRef.target("target:target_1")


@pytest.mark.parametrize(
    ("frozen_amount", "expected"),
    (
        (AuraAmount(1), 2.0),
        (AuraAmount(2), 2 * math.sqrt(14) - 4),
        (AuraAmount(8), 2 * math.sqrt(44) - 4),
    ),
)
def test_base_freeze_duration_uses_confirmed_formula_without_resistance(
    frozen_amount: AuraAmount,
    expected: float,
):
    assert base_freeze_duration_seconds(frozen_amount) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("frozen_amount", "resistance", "expected"),
    (
        (AuraAmount(2), 0.0, 2 * math.sqrt(14) - 4),
        (AuraAmount(2), 0.5, 2.0),
        (AuraAmount(8), 1.0, 0.0),
    ),
)
def test_freeze_resistance_scales_base_duration(
    frozen_amount: AuraAmount,
    resistance: float,
    expected: float,
):
    assert freeze_duration_seconds(
        frozen_amount,
        FreezeResistanceObservation(TARGET, 0, resistance),
    ) == pytest.approx(expected)


def test_continuous_freeze_decay_rate_increases_while_frozen_and_recovers_after_thaw():
    active_rate = increase_freeze_decay_rate(0.4, 2.0)

    assert active_rate == pytest.approx(0.6)
    assert recover_freeze_decay_rate(active_rate, 0.5) == pytest.approx(0.5)
    assert recover_freeze_decay_rate(active_rate, 2.0) == pytest.approx(0.4)


def test_continuous_freeze_duration_uses_inherited_decay_rate():
    assert freeze_duration_seconds(
        AuraAmount(1),
        FreezeResistanceObservation(TARGET, 0, 0.0),
        initial_decay_rate=0.6,
    ) == pytest.approx((math.sqrt(0.56) - 0.6) / 0.1)


def test_freeze_duration_frames_uses_project_half_open_lifecycle_rounding():
    assert freeze_duration_frames(0.0) == 0
    assert freeze_duration_frames(2.0) == 120
    assert freeze_duration_frames(2.0001) == 121


def test_lifecycle_projections_use_frames_without_mutating_state():
    frozen = FrozenState(
        ReactionStateInstanceRef("state:frozen"),
        TARGET,
        ElementalStateLinkRef("link:frozen"),
        0,
    )
    recovery = FreezeRecoveryState(
        ReactionStateInstanceRef("state:recovery"),
        TARGET,
        0.6,
        120,
    )

    assert active_freeze_decay_rate_at(frozen, 120) == pytest.approx(0.6)
    assert active_frozen_amount_at(frozen, AuraAmount(2), 60) == AuraAmount("31/20")
    assert recovered_freeze_decay_rate_at(recovery, 150) == pytest.approx(0.5)
    assert (
        freeze_expiry_frame(
            frame=20,
            frozen_amount=AuraAmount(1),
            freeze_resistance=FreezeResistanceObservation(TARGET, 20, 0.0),
            initial_decay_rate=0.4,
        )
        == 140
    )


@pytest.mark.parametrize("value", (-0.01, 1.01))
def test_freeze_resistance_observation_rejects_values_outside_percentage_range(value: float):
    with pytest.raises(ValueError, match="0 到 1"):
        FreezeResistanceObservation(TARGET, 0, value)
