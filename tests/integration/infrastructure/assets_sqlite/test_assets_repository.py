from __future__ import annotations

from genshin_sim.infrastructure.assets_sqlite import (
    SQLiteAssetRepository,
    validate_asset_database,
    write_minimal_static_asset_database,
)


def test_minimal_static_asset_database_round_trips(tmp_path):
    db_path = tmp_path / "assets.db"

    write_minimal_static_asset_database(db_path)
    validate_asset_database(db_path)

    repository = SQLiteAssetRepository(db_path)
    info = repository.get_info()

    assert info.meta["schema_version"] == "1"
    assert info.meta["data_version"] == "local-static-1"
    assert info.character_count == 1
    assert info.weapon_count == 1
    assert info.artifact_set_count == 1
    assert repository.list_characters()[0].asset_key == "character:test_character"
    character = repository.get_character("character:test_character")
    assert character.name == "Test Character"
    assert character.handler_key == "generic.test_character"
    assert repository.get_character_level_stats("character:test_character", 90).base_hp == 10000.0
    assert repository.list_weapons("sword")[0].asset_key == "weapon:test_sword"
    weapon = repository.get_weapon("weapon:test_sword")
    assert weapon.handler_key == "generic.test_weapon"
    assert repository.get_weapon_level_stats(weapon.asset_key, 90).secondary_value == 0.413
    artifact_set = repository.get_artifact_set("artifact_set:test_set")
    assert artifact_set.name == "Test Set"
    assert artifact_set.handler_key == "generic.test_artifact_set"
    bonuses = repository.get_artifact_set_bonuses(artifact_set.asset_key, 4)
    assert bonuses[0].handler_key == "generic.static_modifiers"
    assert repository.get_talent_scalings("character:test_character", "normal_attack")[0].tags == (
        "damage",
    )
