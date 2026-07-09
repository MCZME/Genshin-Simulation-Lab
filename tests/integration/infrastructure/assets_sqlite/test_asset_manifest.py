from __future__ import annotations

import json

import pytest

from genshin_sim.assets import AssetValidationError
from genshin_sim.infrastructure.assets_sqlite import (
    SQLiteAssetRepository,
    build_asset_database_from_manifest,
    load_asset_manifest,
    validate_asset_database,
)


def test_asset_manifest_builds_valid_database(tmp_path):
    manifest_path = tmp_path / "assets.json"
    db_path = tmp_path / "assets.db"
    manifest_path.write_text(json.dumps(_manifest_payload()), encoding="utf-8")

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
    manifest_path = tmp_path / "assets.json"
    payload = _manifest_payload()
    payload["characters"][0]["display_name"] = "Fixture Character"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AssetValidationError, match="未知字段"):
        load_asset_manifest(manifest_path)


def _manifest_payload():
    return {
        "schema_version": 1,
        "kind": "asset_manifest",
        "meta": {
            "data_version": "fixture-1",
            "source_name": "pytest-manifest",
            "source_version": "2026.07",
        },
        "characters": [
            {
                "asset_key": "character:fixture_char",
                "source_id": "fixture_char",
                "name": "Fixture Character",
                "element": "hydro",
                "weapon_type": "sword",
                "rarity": 5,
            }
        ],
        "character_level_stats": [
            {
                "character_key": "character:fixture_char",
                "level": 20,
                "ascension_phase": 0,
                "base_hp": 2000.0,
                "base_atk": 40.0,
                "base_def": 120.0,
            },
            {
                "character_key": "character:fixture_char",
                "level": 20,
                "ascension_phase": 1,
                "base_hp": 2200.0,
                "base_atk": 44.0,
                "base_def": 132.0,
                "ascension_stat": "hydro_damage_bonus",
                "ascension_value": 0.072,
            },
        ],
        "weapons": [
            {
                "asset_key": "weapon:fixture_sword",
                "source_id": "fixture_sword",
                "name": "Fixture Sword",
                "weapon_type": "sword",
                "rarity": 4,
            }
        ],
        "weapon_level_stats": [
            {
                "weapon_key": "weapon:fixture_sword",
                "level": 90,
                "ascension_phase": 6,
                "base_atk": 510.0,
                "secondary_stat": "atk_percent",
                "secondary_value": 0.413,
            }
        ],
        "artifact_sets": [
            {
                "asset_key": "artifact_set:fixture_set",
                "source_id": "fixture_set",
                "name": "Fixture Set",
            }
        ],
        "artifact_set_bonuses": [
            {
                "artifact_set_key": "artifact_set:fixture_set",
                "piece_count": 2,
                "handler_key": "generic.static_modifiers",
                "params": {
                    "schema_version": 1,
                    "params": {"stat": "atk_percent", "value": 0.18},
                },
            }
        ],
        "talent_scalings": [
            {
                "character_key": "character:fixture_char",
                "talent_key": "normal_attack",
                "entry_key": "hit_1",
                "label": "Normal Attack Hit 1",
                "scaling": {
                    "schema_version": 1,
                    "mode": "constant",
                    "components": [{"kind": "plain_ratio", "values": [1.0]}],
                },
                "tags": ["damage"],
            }
        ],
        "effect_payloads": [
            {
                "effect_key": "weapon:fixture_sword:passive",
                "owner_type": "weapon",
                "owner_key": "weapon:fixture_sword",
                "effect_kind": "passive",
                "handler_key": "generic.static_modifiers",
                "params": {"schema_version": 1, "params": {"stat": "atk_percent", "value": 0.2}},
            }
        ],
    }
