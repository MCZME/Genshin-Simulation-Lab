from __future__ import annotations

import pytest

from genshin_sim.assets import AssetValidationError
from genshin_sim.infrastructure.assets_sqlite import (
    SQLiteAssetRepository,
    build_asset_database_from_manifest,
    load_asset_manifest,
    validate_asset_database,
)
from tests.helpers.asset_manifest import asset_manifest_fixture_payload, write_asset_manifest


def test_asset_manifest_builds_valid_database(tmp_path):
    manifest_path = write_asset_manifest(tmp_path, asset_manifest_fixture_payload())
    db_path = tmp_path / "assets.db"

    build_asset_database_from_manifest(db_path, manifest_path)
    validate_asset_database(db_path)

    repository = SQLiteAssetRepository(db_path)
    info = repository.get_info()

    assert info.meta["data_version"] == "fixture-1"
    assert info.meta["source_name"] == "pytest-manifest"
    assert info.character_count == 1
    assert info.weapon_count == 1
    assert info.artifact_set_count == 1
    assert repository.get_character("character:fixture_char").handler_key is None
    assert repository.get_character("character:fixture_char").burst_energy_cost == 60.0
    assert repository.get_character_level_stats("character:fixture_char", 20).base_hp == 2200.0
    assert repository.get_weapon_level_stats("weapon:fixture_sword", 90).secondary_value == 0.413
    assert repository.get_artifact_set_bonuses("artifact_set:fixture_set", 2)[0].params == {
        "schema_version": 1,
        "params": {"stat": "atk_percent", "value": 0.18},
    }
    assert repository.get_talent_scalings("character:fixture_char", "normal_attack")[0].tags == (
        "damage",
    )
    assert repository.get_effect_payloads("weapon:fixture_sword")[0].effect_key == (
        "weapon:fixture_sword:passive"
    )


def test_asset_manifest_rejects_unknown_fields(tmp_path):
    payload = asset_manifest_fixture_payload()
    payload["characters"][0]["display_name"] = "Fixture Character"
    manifest_path = write_asset_manifest(tmp_path, payload)

    with pytest.raises(AssetValidationError, match="未知字段"):
        load_asset_manifest(manifest_path)
