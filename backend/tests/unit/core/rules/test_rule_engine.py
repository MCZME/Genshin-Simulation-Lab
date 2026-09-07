"""规则引擎测试。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from genshin_sim.core.rules import (
    DuplicateRuleTypeError,
    RuleActivation,
    RuleEngine,
    RuleRegistry,
    RuleResolutionContext,
    RuleValidationError,
    UnknownRuleKeyError,
)
from genshin_sim.core.systems.energy.policies import (
    FullInitialEnergyPolicy,
    InitialEnergyPolicy,
)


class _FullEnergyStub:
    rule_key = "stub.full_energy"
    rule_type: type = InitialEnergyPolicy

    def validate_params(self, params: Mapping[str, Any]) -> None:
        del params

    def resolve_activation(self, activation, context) -> InitialEnergyPolicy:
        del activation, context
        return FullInitialEnergyPolicy()


class _AnotherFullEnergyStub:
    rule_key = "stub.another_full_energy"
    rule_type: type = InitialEnergyPolicy

    def validate_params(self, params: Mapping[str, Any]) -> None:
        del params

    def resolve_activation(self, activation, context) -> InitialEnergyPolicy:
        del activation, context
        return FullInitialEnergyPolicy()


class _BrokenProductStub:
    rule_key = "stub.broken_product"
    rule_type: type = InitialEnergyPolicy

    def validate_params(self, params: Mapping[str, Any]) -> None:
        del params

    def resolve_activation(self, activation, context) -> Any:
        del activation, context
        return object()


class _RejectingParamsStub(_FullEnergyStub):
    rule_key = "stub.rejecting_params"

    def validate_params(self, params: Mapping[str, Any]) -> None:
        raise RuleValidationError("参数非法")


def _engine(*definitions) -> RuleEngine:
    return RuleEngine(RuleRegistry(definitions))


def _context() -> RuleResolutionContext:
    return RuleResolutionContext(seed=7)


def test_engine_resolves_activated_rules_into_type_bundle():
    bundle = _engine(_FullEnergyStub()).resolve(
        (RuleActivation(rule_key="stub.full_energy", params={}),),
        _context(),
    )

    assert set(bundle) == {InitialEnergyPolicy}
    assert isinstance(bundle[InitialEnergyPolicy], FullInitialEnergyPolicy)


def test_engine_rejects_unknown_rule_key():
    with pytest.raises(UnknownRuleKeyError, match="missing.rule"):
        _engine().resolve(
            (RuleActivation(rule_key="missing.rule", params={}),),
            _context(),
        )


def test_engine_rejects_duplicate_activation():
    with pytest.raises(RuleValidationError, match="规则重复激活：stub.full_energy"):
        _engine(_FullEnergyStub()).resolve(
            (
                RuleActivation(rule_key="stub.full_energy", params={}),
                RuleActivation(rule_key="stub.full_energy", params={}),
            ),
            _context(),
        )


def test_engine_rejects_duplicate_rule_type_producers():
    with pytest.raises(DuplicateRuleTypeError) as excinfo:
        _engine(_FullEnergyStub(), _AnotherFullEnergyStub()).resolve(
            (
                RuleActivation(rule_key="stub.full_energy", params={}),
                RuleActivation(rule_key="stub.another_full_energy", params={}),
            ),
            _context(),
        )

    assert "stub.full_energy" in str(excinfo.value)
    assert "stub.another_full_energy" in str(excinfo.value)


def test_engine_propagates_param_validation_error():
    with pytest.raises(RuleValidationError, match="参数非法"):
        _engine(_RejectingParamsStub()).resolve(
            (RuleActivation(rule_key="stub.rejecting_params", params={}),),
            _context(),
        )


def test_engine_rejects_product_not_matching_declared_rule_type():
    with pytest.raises(RuleValidationError, match="不符合声明的规则类型"):
        _engine(_BrokenProductStub()).resolve(
            (RuleActivation(rule_key="stub.broken_product", params={}),),
            _context(),
        )


def test_engine_empty_activations_produce_empty_bundle():
    assert _engine(_FullEnergyStub()).resolve((), _context()) == {}
