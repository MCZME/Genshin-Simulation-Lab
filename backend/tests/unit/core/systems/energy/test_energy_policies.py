"""元素能量装配期策略测试。"""

from __future__ import annotations

from genshin_sim.core.systems.energy.policies import (
    FullInitialEnergyPolicy,
    InitialEnergyPolicy,
    ZeroInitialEnergyPolicy,
)


def test_zero_policy_returns_zero_for_any_capacity():
    assert ZeroInitialEnergyPolicy().initial_energy(60.0) == 0.0
    assert ZeroInitialEnergyPolicy().initial_energy(0.0) == 0.0


def test_full_policy_returns_capacity():
    assert FullInitialEnergyPolicy().initial_energy(60.0) == 60.0


def test_full_policy_keeps_zero_capacity_at_zero():
    assert FullInitialEnergyPolicy().initial_energy(0.0) == 0.0


def test_policies_satisfy_initial_energy_policy_protocol():
    assert isinstance(ZeroInitialEnergyPolicy(), InitialEnergyPolicy)
    assert isinstance(FullInitialEnergyPolicy(), InitialEnergyPolicy)
