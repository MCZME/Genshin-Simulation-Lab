from __future__ import annotations

import pytest

from genshin_sim.content import (
    CharacterRuntimeRequest,
    ContentRuntimeContribution,
    HandlerNotFoundError,
    HandlerRegistry,
    ImpactRuntimeRequest,
    create_default_registry,
)


def test_default_registry_exposes_noop_handler():
    registry = create_default_registry()

    assert "generic.noop" in registry


def test_registry_rejects_duplicate_handler_key_for_same_content_type():
    registry = HandlerRegistry()
    registry.register_character_factory("generic.test", lambda request: None)

    with pytest.raises(ValueError, match="重复 handler_key"):
        registry.register_character_factory("generic.test", lambda request: None)


def test_registry_rejects_duplicate_handler_key_across_content_types():
    registry = HandlerRegistry()
    registry.register_character_factory("generic.test", lambda request: None)

    with pytest.raises(ValueError, match="重复 handler_key"):
        registry.register_weapon_factory("generic.test", lambda request: None)


def test_registry_creates_character_contribution():
    registry = HandlerRegistry()

    def create_character(request: CharacterRuntimeRequest) -> ContentRuntimeContribution:
        return ContentRuntimeContribution(
            owner_type="character",
            owner_key=request.character_key,
            handler_key=request.handler_key,
            slot=request.slot,
            metadata={"source": "test"},
        )

    registry.register_character_factory("character.test", create_character)

    contribution = registry.create_character(
        CharacterRuntimeRequest(
            handler_key="character.test",
            character_key="character:75",
            slot=1,
        )
    )

    assert contribution is not None
    assert contribution.owner_type == "character"
    assert contribution.owner_key == "character:75"
    assert contribution.metadata == {"source": "test"}


def test_registry_creates_impact_contribution():
    registry = HandlerRegistry()
    registry.register_impact_factory(
        "impact.test",
        lambda request: ContentRuntimeContribution(
            owner_type=request.owner_type,
            owner_key=request.owner_key,
            handler_key=request.handler_key,
            slot=request.slot,
            metadata={"impact_key": request.impact_key},
        ),
    )

    contribution = registry.create_impact(
        ImpactRuntimeRequest(
            handler_key="impact.test",
            owner_type="character",
            owner_key="character:75",
            slot=1,
            impact_key="effect:char",
            impact_kind="passive",
        )
    )

    assert contribution is not None
    assert contribution.metadata == {"impact_key": "effect:char"}


def test_registry_raises_when_missing_specific_handler():
    registry = HandlerRegistry()

    with pytest.raises(HandlerNotFoundError, match="缺少角色 handler：missing"):
        registry.create_character(
            CharacterRuntimeRequest(
                handler_key="missing",
                character_key="character:75",
                slot=1,
            )
        )
