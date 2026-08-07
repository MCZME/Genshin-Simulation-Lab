from __future__ import annotations

import pytest

from genshin_sim.content import (
    BARBARA_CHARACTER_HANDLER_KEY,
    BUILTIN_NOOP_CONTENT_HANDLER_KEYS,
    RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
    CharacterContentUnitRequest,
    ContentUnitRegistry,
    DuplicateContentUnitFactoryError,
    create_default_content_unit_registry,
)


def test_default_content_unit_registry_registers_noop_handlers():
    registry = create_default_content_unit_registry()

    assert registry.handler_keys
    for handler_key in BUILTIN_NOOP_CONTENT_HANDLER_KEYS:
        assert registry.has_character_handler(handler_key)
        assert registry.has_weapon_handler(handler_key)
        assert registry.has_artifact_handler(handler_key)
        assert registry.has_effect_handler(handler_key)


def test_default_content_unit_registry_can_run_noop_handler():
    registry = create_default_content_unit_registry()

    character_result = registry.create_character(
        CharacterContentUnitRequest(
            handler_key="generic.noop",
            character_key="character:noop",
            slot=1,
        )
    )

    assert character_result is None


def test_default_content_unit_registry_exposes_builtin_characters():
    registry = create_default_content_unit_registry()

    assert registry.has_character_handler(BARBARA_CHARACTER_HANDLER_KEY)
    assert registry.has_character_handler(RUNTIME_PROBE_CHARACTER_HANDLER_KEY)


def test_default_registry_does_not_silently_replace_existing_factory():
    registry = create_default_content_unit_registry()
    registry.register_character_factory(
        BARBARA_CHARACTER_HANDLER_KEY,
        lambda request: None,
        replace=True,
    )

    with pytest.raises(DuplicateContentUnitFactoryError, match=BARBARA_CHARACTER_HANDLER_KEY):
        registry.register_character_factory(
            BARBARA_CHARACTER_HANDLER_KEY,
            lambda request: None,
        )


def test_default_registry_is_content_unit_registry():
    assert isinstance(create_default_content_unit_registry(), ContentUnitRegistry)
