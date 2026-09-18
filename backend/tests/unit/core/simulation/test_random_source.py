"""仿真随机源测试。"""

from __future__ import annotations

import math

import pytest

from genshin_sim.core.simulation.random_source import RandomSource, RandomSourceError


@pytest.mark.parametrize(
    "seed",
    [1.5, True, "42"],
    ids=("float", "bool", "string"),
)
def test_source_rejects_non_integer_seed(seed):
    with pytest.raises(RandomSourceError, match="必须是整数"):
        RandomSource(seed)


def test_next_returns_values_in_unit_interval_and_counts_draws():
    source = RandomSource(7)

    values = [source.next() for _ in range(50)]

    assert all(0.0 <= value < 1.0 for value in values)
    assert source.draw_count == 50


def test_roll_boundaries_do_not_consume_sequence():
    source = RandomSource(7)

    assert source.roll(0.0) is False
    assert source.roll(1.0) is True
    assert source.draw_count == 0

    assert source.roll(0.5) in (True, False)
    assert source.draw_count == 1


@pytest.mark.parametrize(
    "probability",
    [True, "0.5"],
    ids=("bool", "non-numeric"),
)
def test_roll_rejects_non_numeric_probability(probability):
    with pytest.raises(RandomSourceError, match="必须是数字"):
        RandomSource(7).roll(probability)


@pytest.mark.parametrize(
    "probability",
    [-0.1, 1.1, math.nan, math.inf],
    ids=("below-zero", "above-one", "nan", "inf"),
)
def test_roll_rejects_out_of_range_probability(probability):
    with pytest.raises(RandomSourceError, match="0 到 1 之间"):
        RandomSource(7).roll(probability)