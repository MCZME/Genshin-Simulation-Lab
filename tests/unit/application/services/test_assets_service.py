from __future__ import annotations

import pytest

from genshin_sim.application.services import AssetDatabaseService, AssetsService
from genshin_sim.assets import AssetDbInfo, CharacterAsset, WeaponAsset


class MemoryAssetRepository:
    def get_meta(self) -> dict[str, str]:
        return {"schema_version": "1"}

    def get_info(self) -> AssetDbInfo:
        return AssetDbInfo(meta={"schema_version": "1"}, character_count=1, weapon_count=1)

    def list_characters(self):
        return (
            CharacterAsset(
                asset_key="character:test",
                source_id="test",
                name="Test Character",
                element="anemo",
                weapon_type="sword",
                rarity=5,
            ),
        )

    def get_character(self, character_key: str):
        assert character_key == "character:test"
        return self.list_characters()[0]

    def get_character_level_stats(self, character_key: str, level: int):
        raise LookupError((character_key, level))

    def list_weapons(self, weapon_type: str | None = None):
        return (
            WeaponAsset(
                asset_key="weapon:test",
                source_id="test",
                name="Test Weapon",
                weapon_type=weapon_type or "sword",
                rarity=4,
            ),
        )

    def get_weapon(self, weapon_key: str):
        assert weapon_key == "weapon:test"
        return self.list_weapons()[0]

    def get_weapon_level_stats(self, weapon_key: str, level: int):
        raise LookupError((weapon_key, level))

    def list_artifact_sets(self):
        return ()

    def get_artifact_set(self, artifact_set_key: str):
        raise LookupError(artifact_set_key)

    def get_artifact_set_bonuses(
        self,
        artifact_set_key: str,
        piece_count: int | None = None,
    ):
        return ()

    def get_talent_scalings(self, character_key: str, talent_key: str):
        return ()

    def get_effect_payloads(self, owner_key: str, effect_kind: str | None = None):
        return ()


def test_assets_service_lists_asset_summaries():
    service = AssetsService(MemoryAssetRepository())

    items = service.list_assets("characters")

    assert items[0].asset_key == "character:test"
    assert items[0].name == "Test Character"


def test_assets_service_inspects_by_asset_key_prefix():
    service = AssetsService(MemoryAssetRepository())

    item = service.inspect_asset("weapon:test")

    assert item.name == "Test Weapon"


def test_assets_service_rejects_unknown_asset_key_type():
    service = AssetsService(MemoryAssetRepository())

    with pytest.raises(ValueError, match="不支持的 asset_key 类型"):
        service.inspect_asset("enemy:test")


def test_asset_database_service_delegates_maintenance_operations(tmp_path):
    calls: list[tuple[str, str]] = []

    def init_database(path):
        calls.append(("init", str(path)))
        return path

    def build_database(path):
        calls.append(("build", str(path)))
        return path

    def validate_database(path):
        calls.append(("validate", str(path)))

    service = AssetDatabaseService(
        init_database=init_database,
        build_database=build_database,
        validate_database=validate_database,
    )
    db_path = tmp_path / "assets.db"

    assert service.init_database(db_path) == db_path
    assert service.build_database(db_path) == db_path
    service.validate_database(db_path)

    assert calls == [
        ("init", str(db_path)),
        ("build", str(db_path)),
        ("validate", str(db_path)),
    ]
