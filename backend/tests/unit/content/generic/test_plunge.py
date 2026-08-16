from __future__ import annotations

from genshin_sim.content.generic.plunge import (
    PLUNGE_COLLISION_AOE_RADIUS,
    PLUNGE_COLLISION_ELEMENTAL_AMOUNT,
    PLUNGE_HIGH_AIR_HEIGHT,
    PLUNGE_LANDING_ELEMENTAL_AMOUNT,
    PLUNGE_LANDING_HIGH_AOE_RADIUS,
    PLUNGE_LANDING_LOW_AOE_RADIUS,
    PLUNGE_LOW_AIR_HEIGHT,
)


def test_plunge_thresholds_are_temporary_global_data():
    assert PLUNGE_LOW_AIR_HEIGHT == 1.5
    assert PLUNGE_HIGH_AIR_HEIGHT == 2.0


def test_plunge_catalyst_attack_data():
    assert PLUNGE_COLLISION_AOE_RADIUS == 1.5
    assert PLUNGE_COLLISION_ELEMENTAL_AMOUNT == 0
    assert PLUNGE_LANDING_LOW_AOE_RADIUS == 3.0
    assert PLUNGE_LANDING_HIGH_AOE_RADIUS == 3.5
    assert PLUNGE_LANDING_ELEMENTAL_AMOUNT == 1
