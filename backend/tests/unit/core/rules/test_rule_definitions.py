"""内置规则定义测试。"""

from __future__ import annotations

import pytest

from genshin_sim.core.rules import (
    RuleActivation,
    RuleResolutionContext,
    RuleValidationError,
)
from genshin_sim.core.rules.definitions import (
    CritModeDefinition,
    StartWithFullEnergyDefinition,
)
from genshin_sim.core.systems.damage.enums import CritOutcome
from genshin_sim.core.systems.damage.policies import (
    CriticalDecisionProvider,
    FixedCriticalDecisionProvider,
    SeededRandomCriticalDecisionProvider,
)
from genshin_sim.core.systems.energy.policies import (
    FullInitialEnergyPolicy,
    InitialEnergyPolicy,
)


def test_start_with_full_energy_rejects_any_params():
    with pytest.raises(RuleValidationError, match="不接受参数"):
        StartWithFullEnergyDefinition().validate_params({"mode": "on"})


def test_start_with_full_energy_accepts_empty_params():
    StartWithFullEnergyDefinition().validate_params({})


def test_start_with_full_energy_produces_full_policy():
    product = StartWithFullEnergyDefinition().resolve_activation(
        RuleActivation(rule_key="start_with_full_energy", params={}),
        RuleResolutionContext(seed=0),
    )

    assert isinstance(product, FullInitialEnergyPolicy)
    assert product.initial_energy(60.0) == 60.0
    assert product.initial_energy(0.0) == 0.0
    assert StartWithFullEnergyDefinition.rule_type is InitialEnergyPolicy


@pytest.mark.parametrize(
    "params",
    [
        {"mode": "always"},
        {"mode": 1},
        {"unknown": True},
    ],
    ids=("bad-mode", "non-string-mode", "unknown-param"),
)
def test_crit_mode_rejects_invalid_params(params):
    with pytest.raises(RuleValidationError, match="crit_mode"):
        CritModeDefinition().validate_params(params)


@pytest.mark.parametrize("params", [{}, {"mode": "off"}, {"mode": "random"}])
def test_crit_mode_accepts_valid_params(params):
    CritModeDefinition().validate_params(params)


def test_crit_mode_off_produces_fixed_non_critical_provider():
    product = CritModeDefinition().resolve_activation(
        RuleActivation(rule_key="crit_mode", params={}),
        RuleResolutionContext(seed=42),
    )

    assert isinstance(product, FixedCriticalDecisionProvider)
    assert product.outcome is CritOutcome.NON_CRITICAL
    assert CritModeDefinition.rule_type is CriticalDecisionProvider


def test_crit_mode_random_uses_run_options_seed():
    product = CritModeDefinition().resolve_activation(
        RuleActivation(rule_key="crit_mode", params={"mode": "random"}),
        RuleResolutionContext(seed=42),
    )

    assert isinstance(product, SeededRandomCriticalDecisionProvider)
    assert product.seed == 42
