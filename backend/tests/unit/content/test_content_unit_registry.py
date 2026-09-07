from __future__ import annotations

import pytest

from genshin_sim.content.definitions.content_unit import ContentUnit, ContentUnitOwnerType
from genshin_sim.content.registries import (
    ArtifactContentUnitRequest,
    CharacterContentUnitRequest,
    ContentUnitFactoryNotFoundError,
    ContentUnitRegistry,
    ContentUnitRegistryError,
    DuplicateContentUnitFactoryError,
    WeaponContentUnitRequest,
)


def _character_unit(handler_key: str) -> ContentUnit:
    return ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key="character:1",
        handler_key=handler_key,
        version="dev-m3",
        slot=1,
    )


def test_registry_creates_character_content_unit():
    registry = ContentUnitRegistry()

    def factory(request: CharacterContentUnitRequest) -> ContentUnit:
        return _character_unit(request.handler_key)

    registry.register_character_factory("character.test", factory)

    unit = registry.create_character(
        CharacterContentUnitRequest(
            handler_key="character.test",
            character_key="character:1",
            slot=1,
        )
    )
    assert unit is not None
    assert unit.handler_key == "character.test"


def test_registry_requests_carry_compile_evidence():
    request = CharacterContentUnitRequest(
        handler_key="character.test",
        character_key="character:1",
        slot=1,
        constellation=4,
        talent_levels={"normal_attack": 10},
    )
    weapon_request = WeaponContentUnitRequest(
        handler_key="weapon.test",
        weapon_key="weapon:1",
        slot=1,
        refinement=5,
    )
    artifact_request = ArtifactContentUnitRequest(
        handler_key="artifact.test",
        artifact_key="artifact_set:1",
        slot=1,
        artifact_kind="artifact_set_bonus",
        piece_count=4,
    )

    assert request.constellation == 4
    assert request.talent_levels == {"normal_attack": 10}
    assert weapon_request.refinement == 5
    assert artifact_request.piece_count == 4


def test_registry_rejects_duplicate_handler_key_across_types():
    registry = ContentUnitRegistry()
    registry.register_character_factory(
        "character.test",
        lambda request: _character_unit(request.handler_key),
    )

    with pytest.raises(DuplicateContentUnitFactoryError, match="character.test"):
        registry.register_weapon_factory("character.test", lambda request: None)


def test_registry_reports_missing_factory():
    registry = ContentUnitRegistry()

    with pytest.raises(ContentUnitFactoryNotFoundError, match="角色"):
        registry.create_character(
            CharacterContentUnitRequest(
                handler_key="character.missing",
                character_key="character:1",
                slot=1,
            )
        )


def test_registry_handler_keys_are_sorted_and_unique():
    registry = ContentUnitRegistry()
    registry.register_character_factory(
        "character.b",
        lambda request: _character_unit(request.handler_key),
    )
    registry.register_weapon_factory(
        "weapon.a",
        lambda request: None,
    )

    assert registry.handler_keys == ("character.b", "weapon.a")
    assert registry.has_character_handler("character.b")
    assert registry.has_weapon_handler("weapon.a")


def test_request_rejects_invalid_constellation_and_talent_levels():
    with pytest.raises(ContentUnitRegistryError, match="constellation"):
        CharacterContentUnitRequest(
            handler_key="character.test",
            character_key="character:1",
            slot=1,
            constellation=7,
        )
    with pytest.raises(ContentUnitRegistryError, match="talent_levels"):
        CharacterContentUnitRequest(
            handler_key="character.test",
            character_key="character:1",
            slot=1,
            talent_levels={"normal_attack": 0},
        )
