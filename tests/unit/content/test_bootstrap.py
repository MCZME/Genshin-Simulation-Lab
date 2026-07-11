from __future__ import annotations

import pytest

from genshin_sim.content import (
    BARBARA_CHARACTER_HANDLER_KEY,
    BUILTIN_HANDLER_KEYS,
    BUILTIN_NOOP_HANDLER_KEYS,
    NOOP_HANDLER_KEY,
    RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
    CharacterRuntimeRequest,
    DuplicateHandlerError,
    HandlerRegistry,
    ImpactRuntimeRequest,
    create_default_registry,
    register_builtin_content,
)


def test_register_builtin_content_registers_noop_handler_explicitly():
    registry = HandlerRegistry()

    assert not registry.has_handler(NOOP_HANDLER_KEY)

    returned = register_builtin_content(registry)

    assert returned is registry
    assert registry.handler_keys == BUILTIN_HANDLER_KEYS
    for handler_key in BUILTIN_NOOP_HANDLER_KEYS:
        assert registry.has_handler(handler_key)


def test_default_registry_can_run_noop_handler():
    registry = create_default_registry()

    character_result = registry.create_character(
        CharacterRuntimeRequest(
            handler_key=NOOP_HANDLER_KEY,
            character_key="character:noop",
            slot=1,
            params={"reason": "placeholder"},
        )
    )
    impact_result = registry.create_impact(
        ImpactRuntimeRequest(
            handler_key=NOOP_HANDLER_KEY,
            owner_type="test",
            owner_key="test:noop",
            slot=None,
            impact_key="effect:noop",
            impact_kind="placeholder",
            params={"reason": "placeholder"},
        )
    )

    assert character_result is None
    assert impact_result is None


def test_default_registry_can_check_specific_noop_handlers():
    registry = create_default_registry()

    assert registry.has_character_handler(NOOP_HANDLER_KEY)
    assert registry.has_weapon_handler(NOOP_HANDLER_KEY)
    assert registry.has_artifact_handler(NOOP_HANDLER_KEY)
    assert registry.has_impact_handler(NOOP_HANDLER_KEY)
    assert registry.has_character_handler(BARBARA_CHARACTER_HANDLER_KEY)
    assert registry.has_character_handler(RUNTIME_PROBE_CHARACTER_HANDLER_KEY)


def test_builtin_bootstrap_does_not_silently_replace_existing_handler():
    registry = create_default_registry()

    with pytest.raises(DuplicateHandlerError, match=NOOP_HANDLER_KEY):
        register_builtin_content(registry)
