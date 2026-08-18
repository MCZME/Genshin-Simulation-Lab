from __future__ import annotations

import pytest

from genshin_sim.application.services import AssetDatabaseService, AssetsService
from genshin_sim.assets import CharacterAsset, WeaponAsset
from genshin_sim.content import create_default_content_unit_registry
from tests.helpers.asset_repository import FakeAssetRepository


class MemoryAssetRepository(FakeAssetRepository):
    def __init__(self) -> None:
        super().__init__(
            meta={"schema_version": "1"},
            artifact_sets=(),
            artifact_set_bonuses=(),
            effect_payloads=(),
            characters=(
                CharacterAsset(
                    asset_key="character:test",
                    source_id="test",
                    name="Test Character",
                    element="anemo",
                    weapon_type="sword",
                    rarity=5,
                ),
            ),
            weapons=(
                WeaponAsset(
                    asset_key="weapon:test",
                    source_id="test",
                    name="Test Weapon",
                    weapon_type="sword",
                    rarity=4,
                ),
            ),
        )


def test_assets_service_lists_asset_summaries():
    service = AssetsService(MemoryAssetRepository())

    items = service.list_assets("characters")

    assert items[0].asset_key == "character:test"
    assert items[0].name == "Test Character"
    assert items[0].source_id == "test"
    assert items[0].usable is False
    assert items[0].status == "角色实现未接入"


def test_assets_service_filters_and_paginates():
    service = AssetsService(MemoryAssetRepository())

    items = service.list_assets("weapons", q="TEST WEAPON", limit=1, offset=0)

    assert len(items) == 1
    assert items[0].source_id == "test"
    assert service.list_assets("weapons", q="missing") == ()


def test_assets_service_returns_detail_by_source_id():
    service = AssetsService(MemoryAssetRepository())

    item = service.get_asset("characters", "test")

    assert item.asset_key == "character:test"
    assert item.name == "Test Character"


def test_assets_service_marks_registered_assets_usable():
    repository = FakeAssetRepository(
        meta={"schema_version": "1"},
        characters=(
            CharacterAsset(
                asset_key="character:ready",
                source_id="ready",
                name="Ready Character",
                element="hydro",
                weapon_type="catalyst",
                rarity=4,
                handler_key="generic.test_character",
            ),
        ),
        weapons=(
            WeaponAsset(
                asset_key="weapon:ready",
                source_id="ready",
                name="Ready Weapon",
                weapon_type="catalyst",
                rarity=4,
                handler_key="generic.test_weapon",
            ),
        ),
    )
    service = AssetsService(
        repository,
        content_unit_registry=create_default_content_unit_registry(),
    )

    character = service.get_asset("characters", "ready")
    weapon = service.get_asset("weapons", "ready")

    assert character.usable is True
    assert character.status is None
    assert weapon.usable is True


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
