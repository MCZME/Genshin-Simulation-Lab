from __future__ import annotations

import pytest

from genshin_sim.assets import (
    ArtifactSetAsset,
    ArtifactSetBonus,
    AssetNotFoundError,
    AssetValidationError,
    CharacterAsset,
    EffectPayload,
    WeaponAsset,
)
from genshin_sim.infrastructure.assets_sqlite import SQLiteAssetDataWriter, SQLiteAssetRepository


def _build_db(tmp_path) -> str:
    db_path = tmp_path / "assets.db"
    SQLiteAssetDataWriter(db_path).replace_all(
        characters=(
            CharacterAsset(
                asset_key="character:test",
                source_id="test",
                name="Test",
                element="anemo",
                weapon_type="sword",
                rarity=4,
                burst_energy_cost=40.0,
                handler_key=None,
            ),
        ),
        weapons=(
            WeaponAsset(
                asset_key="weapon:test",
                source_id="test",
                name="Test",
                weapon_type="sword",
                rarity=4,
                handler_key=None,
            ),
        ),
        artifact_sets=(
            ArtifactSetAsset(
                asset_key="artifact_set:test",
                source_id="test",
                name="Test",
                handler_key=None,
            ),
        ),
        artifact_set_bonuses=(
            ArtifactSetBonus(
                artifact_set_key="artifact_set:test",
                piece_count=2,
                handler_key="artifact.unimplemented_set_bonus",
                params={"schema_version": 1},
            ),
        ),
        effect_payloads=(
            EffectPayload(
                effect_key="character:test:passive:1",
                owner_type="character",
                owner_key="character:test",
                effect_kind="passive",
                unlock_key="passive:1",
                handler_key="character.unimplemented_passive",
                params={"schema_version": 1},
            ),
        ),
    )
    return str(db_path)


def test_get_and_set_character_handler_binding(tmp_path):
    repository = SQLiteAssetRepository(_build_db(tmp_path))

    assert repository.get_handler_binding("character", "character:test").handler_key is None

    repository.set_handler_binding("character", "character:test", "character.test.real")

    assert (
        repository.get_handler_binding("character", "character:test").handler_key
        == "character.test.real"
    )


def test_set_effect_handler_binding_and_reset_placeholder(tmp_path):
    repository = SQLiteAssetRepository(_build_db(tmp_path))
    key = "character:test:passive:1"

    repository.set_handler_binding("effect", key, "character.test.real")
    binding = repository.get_handler_binding("effect", key)

    assert binding.handler_key == "character.test.real"
    assert binding.effect_kind == "passive"

    repository.set_handler_binding("effect", key, "character.unimplemented_passive")
    assert (
        repository.get_handler_binding("effect", key).handler_key
        == "character.unimplemented_passive"
    )


def test_set_artifact_bonus_handler_binding_requires_pieces(tmp_path):
    repository = SQLiteAssetRepository(_build_db(tmp_path))

    with pytest.raises(AssetValidationError, match="--pieces"):
        repository.set_handler_binding("artifact-bonus", "artifact_set:test", "artifact.test.real")

    repository.set_handler_binding(
        "artifact-bonus",
        "artifact_set:test",
        "artifact.test.real",
        pieces=2,
    )
    assert (
        repository.get_handler_binding("artifact-bonus", "artifact_set:test", pieces=2).handler_key
        == "artifact.test.real"
    )


def test_get_missing_handler_binding_raises(tmp_path):
    repository = SQLiteAssetRepository(_build_db(tmp_path))

    with pytest.raises(AssetNotFoundError):
        repository.get_handler_binding("character", "character:missing")


def test_list_effect_handler_bindings_filters_by_owner(tmp_path):
    repository = SQLiteAssetRepository(_build_db(tmp_path))

    assert repository.list_handler_bindings("effect", owner_key="character:test")[0].key == (
        "character:test:passive:1"
    )
    assert repository.list_handler_bindings("effect", owner_key="character:other") == ()
