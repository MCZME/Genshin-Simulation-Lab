"""规则注册中心测试。"""

from __future__ import annotations

import pytest

from genshin_sim.core.rules import (
    DuplicateRuleKeyError,
    RuleRegistry,
    UnknownRuleKeyError,
    create_default_rule_registry,
)
from genshin_sim.core.rules.definitions import (
    CritModeDefinition,
    StartWithFullEnergyDefinition,
)


class _StubDefinition:
    rule_key = "stub.rule"
    rule_type: type = object

    def validate_params(self, params) -> None:
        del params

    def resolve_activation(self, activation, context):
        del activation, context
        return object()


def test_registry_registers_and_requires_definition():
    definition = _StubDefinition()
    registry = RuleRegistry((definition,))

    assert registry.require("stub.rule") is definition
    assert registry.rule_keys == ("stub.rule",)
    assert registry.definitions == (definition,)


def test_registry_rejects_duplicate_rule_key():
    registry = RuleRegistry((_StubDefinition(),))

    with pytest.raises(DuplicateRuleKeyError, match="stub.rule"):
        registry.register(_StubDefinition())


def test_registry_require_rejects_unknown_rule_key():
    registry = RuleRegistry()

    with pytest.raises(UnknownRuleKeyError, match="未注册的规则：missing.rule"):
        registry.require("missing.rule")


def test_default_registry_contains_builtin_rules():
    registry = create_default_rule_registry()

    assert set(registry.rule_keys) == {"crit_mode", "start_with_full_energy"}
    assert isinstance(registry.require("crit_mode"), CritModeDefinition)
    assert isinstance(
        registry.require("start_with_full_energy"),
        StartWithFullEnergyDefinition,
    )
