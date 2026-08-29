"""组合资产仓库的单元测试。"""

from __future__ import annotations

import pytest

from genshin_sim.assets import (
    CharacterAsset,
    CompositeAssetRepository,
    WeaponAsset,
)
from genshin_sim.assets.errors import AssetNotFoundError


class _SingleCharacterRepository:
    """只提供一个角色、其余查询为空/报错的最小仓库。"""

    def __init__(self, character: CharacterAsset | None) -> None:
        self._character = character

    def get_meta(self) -> dict[str, str]:
        return {"source_name": "stub"}

    def get_info(self):
        from genshin_sim.assets import AssetDbInfo

        count = 1 if self._character is not None else 0
        return AssetDbInfo(meta=self.get_meta(), character_count=count)

    def list_characters(self) -> tuple[CharacterAsset, ...]:
        return () if self._character is None else (self._character,)

    def get_character(self, character_key: str) -> CharacterAsset:
        if self._character is None or self._character.asset_key != character_key:
            raise AssetNotFoundError(f"character not found: {character_key}")
        return self._character

    def get_character_level_stats(self, character_key: str, level: int, *, ascended=True):
        raise AssetNotFoundError("no stats")

    def list_weapons(self, weapon_type=None) -> tuple[WeaponAsset, ...]:
        return ()

    def get_weapon(self, weapon_key: str) -> WeaponAsset:
        raise AssetNotFoundError(f"weapon not found: {weapon_key}")

    def get_weapon_level_stats(self, weapon_key: str, level: int, *, ascended=True):
        raise AssetNotFoundError("no stats")

    def list_artifact_sets(self):
        return ()

    def get_artifact_set(self, artifact_set_key: str):
        raise AssetNotFoundError(f"artifact set not found: {artifact_set_key}")

    def get_artifact_set_bonuses(self, artifact_set_key: str, piece_count=None):
        return ()

    def get_talent_scalings(self, character_key: str, talent_key: str):
        return ()

    def get_effect_payloads(self, owner_key: str, effect_kind=None):
        return ()


def _character(asset_key: str) -> CharacterAsset:
    return CharacterAsset(
        asset_key=asset_key,
        source_id=asset_key.split(":", 1)[1],
        name=asset_key,
        element="anemo",
        weapon_type="sword",
        rarity=5,
        burst_energy_cost=60.0,
        handler_key="generic.test_character",
    )


def test_composite_falls_back_to_secondary_for_missing_character():
    primary = _SingleCharacterRepository(_character("character:amber"))
    fallback = _SingleCharacterRepository(_character("character:test_character"))
    composite = CompositeAssetRepository(primary, fallback)

    assert composite.get_character("character:amber").asset_key == "character:amber"
    assert composite.get_character("character:test_character").asset_key == (
        "character:test_character"
    )
    with pytest.raises(AssetNotFoundError):
        composite.get_character("character:missing")


def test_composite_merges_lists_with_primary_priority():
    primary = _SingleCharacterRepository(_character("character:amber"))
    fallback = _SingleCharacterRepository(_character("character:amber"))
    composite = CompositeAssetRepository(primary, fallback)

    listed = composite.list_characters()
    assert [asset.asset_key for asset in listed] == ["character:amber"]


def test_composite_empty_scalings_fall_back_without_error():
    # SQLite 仓库对未知键返回空元组而非报错：组合仓库必须合并而不是只看主库
    primary = _SingleCharacterRepository(None)
    fallback = _SingleCharacterRepository(_character("character:test_character"))
    composite = CompositeAssetRepository(primary, fallback)

    assert composite.get_talent_scalings("character:test_character", "normal_attack") == ()
    # 主库完全没有角色时回退库兜底
    assert composite.get_character("character:test_character").asset_key == (
        "character:test_character"
    )
    with pytest.raises(AssetNotFoundError):
        composite.get_character("character:missing")


def test_composite_meta_and_info_come_from_primary():
    primary = _SingleCharacterRepository(None)
    fallback = _SingleCharacterRepository(_character("character:test_character"))
    composite = CompositeAssetRepository(primary, fallback)

    assert composite.get_meta() == {"source_name": "stub"}
    assert composite.get_info().character_count == 0
