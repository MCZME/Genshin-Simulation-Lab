from __future__ import annotations

import math

import pytest

from genshin_sim.core.entity_states import HealthState


def test_health_state_accepts_positive_and_zero_current_hp():
    health = HealthState(1000)

    assert health.current_hp == 1000.0
    assert not health.is_zero

    health.current_hp = 0

    assert health.current_hp == 0.0
    assert health.is_zero


@pytest.mark.parametrize("value", [True, -1, math.nan, math.inf, -math.inf, "100"])
def test_health_state_rejects_invalid_current_hp(value: object):
    with pytest.raises(ValueError):
        HealthState(value)  # type: ignore[arg-type]
