from __future__ import annotations

from typing import Any

import pytest

from genshin_sim.content.definitions.components import (
    DuplicateGenericComponentKindError,
    GenericComponent,
    GenericComponentKindRegistry,
    InvalidGenericComponentError,
    UnknownGenericComponentKindError,
)


def test_component_normalizes_params():
    component = GenericComponent(
        kind="talent_level_boost",
        params={"skill": "elemental_skill", "amount": 3},
    )

    assert component.kind == "talent_level_boost"
    assert component.params == {"skill": "elemental_skill", "amount": 3}


def test_component_rejects_empty_kind():
    with pytest.raises(ValueError, match="kind"):
        GenericComponent(kind="", params={})


def test_component_rejects_non_json_params():
    bad_params: Any = {"bad": (1, 2)}

    with pytest.raises(TypeError, match="params"):
        GenericComponent(kind="talent_level_boost", params=bad_params)


def test_component_rejects_invalid_schema_version():
    with pytest.raises(ValueError, match="schema_version"):
        GenericComponent(kind="talent_level_boost", params={}, schema_version=0)


def test_registry_requires_registered_kind():
    registry = GenericComponentKindRegistry()

    with pytest.raises(UnknownGenericComponentKindError, match="talent_level_boost"):
        registry.validate(GenericComponent(kind="talent_level_boost", params={}))


def test_registry_runs_kind_validator():
    def validate_boost(params):
        if params.get("amount", 0) <= 0:
            raise ValueError("amount 必须为正数")

    registry = GenericComponentKindRegistry()
    registry.register("talent_level_boost", validate_boost)

    registry.validate(GenericComponent(kind="talent_level_boost", params={"amount": 3}))
    with pytest.raises(InvalidGenericComponentError, match="amount"):
        registry.validate(GenericComponent(kind="talent_level_boost", params={"amount": 0}))


def test_registry_rejects_duplicate_kind():
    registry = GenericComponentKindRegistry()
    registry.register("talent_level_boost", lambda params: None)

    with pytest.raises(DuplicateGenericComponentKindError, match="talent_level_boost"):
        registry.register("talent_level_boost", lambda params: None)

    registry.register("talent_level_boost", lambda params: None, replace=True)
    assert registry.kinds == ("talent_level_boost",)
