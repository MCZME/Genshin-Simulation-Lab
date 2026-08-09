from __future__ import annotations

import pytest

from genshin_sim.content import (
    ContentUnitRegistry,
    DuplicateContentUnitFactoryError,
    EffectContentUnitRequest,
    HandlerImplementationStatus,
)


def _effect_request(handler_key: str) -> EffectContentUnitRequest:
    return EffectContentUnitRequest(
        handler_key=handler_key,
        effect_key=f"character:test:{handler_key}",
        effect_kind="passive",
        owner_type="character",
        owner_key="character:test",
    )


def test_empty_effect_handler_registration_is_visible_and_contributes_nothing():
    registry = ContentUnitRegistry()
    registry.register_empty_effect_handler("character.test.empty")

    assert registry.has_effect_handler("character.test.empty")
    assert registry.handler_status("character.test.empty") is HandlerImplementationStatus.EMPTY
    assert registry.create_effect(_effect_request("character.test.empty")) is None
    assert registry.empty_handler_keys == ("character.test.empty",)
    assert registry.unimplemented_handler_keys == ()


def test_unimplemented_effect_handler_registration_is_visible_and_contributes_nothing():
    registry = ContentUnitRegistry()
    registry.register_unimplemented_effect_handler("character.test.pending")

    assert registry.has_effect_handler("character.test.pending")
    assert (
        registry.handler_status("character.test.pending")
        is HandlerImplementationStatus.UNIMPLEMENTED
    )
    assert registry.create_effect(_effect_request("character.test.pending")) is None
    assert registry.unimplemented_handler_keys == ("character.test.pending",)
    assert registry.empty_handler_keys == ()


def test_registered_factory_is_implemented():
    registry = ContentUnitRegistry()
    registry.register_effect_factory("character.test.real", lambda request: None)

    assert (
        registry.handler_status("character.test.real")
        is HandlerImplementationStatus.IMPLEMENTED
    )
    assert registry.empty_handler_keys == ()
    assert registry.unimplemented_handler_keys == ()


def test_noop_placeholder_is_not_added():
    registry = ContentUnitRegistry()
    registry.register_noop_handler("character.unimplemented_constellation")

    assert (
        registry.handler_status("character.unimplemented_constellation")
        is HandlerImplementationStatus.NOT_ADDED
    )


def test_duplicate_empty_registration_raises():
    registry = ContentUnitRegistry()
    registry.register_empty_effect_handler("character.test.empty")

    with pytest.raises(DuplicateContentUnitFactoryError):
        registry.register_unimplemented_effect_handler("character.test.empty")


def test_unknown_handler_status_is_none():
    registry = ContentUnitRegistry()

    assert registry.handler_status("character.test.missing") is None
