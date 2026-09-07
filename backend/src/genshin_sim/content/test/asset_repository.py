"""开发者测试资产的内存仓库。

与 ``infrastructure.assets_sqlite.SQLiteAssetRepository`` 实现同一个
``AssetRepository`` 只读协议，数据来自 ``content.test.assets`` 的代码
定义，不访问任何数据库；查询语义（含突破前后等级数值的选择规则）与
SQLite 实现保持一致。
"""

from __future__ import annotations

from typing import Protocol

from genshin_sim.assets import (
    ArtifactSetAsset,
    ArtifactSetBonus,
    AssetDbInfo,
    AssetNotFoundError,
    CharacterAsset,
    CharacterLevelStats,
    EffectPayload,
    TalentScalingEntry,
    WeaponAsset,
    WeaponLevelStats,
)
from genshin_sim.content.test.assets import (
    TEST_ARTIFACT_SET_ASSETS,
    TEST_ARTIFACT_SET_BONUSES,
    TEST_CHARACTER_ASSETS,
    TEST_CHARACTER_LEVEL_STATS,
    TEST_META,
    TEST_TALENT_SCALINGS,
    TEST_WEAPON_ASSETS,
    TEST_WEAPON_LEVEL_STATS,
)

# 可选择突破前/突破后属性的等级，与 SQLite 资产仓库保持一致。
_ASCENDABLE_LEVELS = frozenset({20, 40, 50, 60, 70, 80})


class _LevelStatsLike(Protocol):
    """等级数值行的最小协议（角色与武器共用选择规则）。"""

    @property
    def ascension_phase(self) -> int: ...


class TestAssetRepository:
    """代码定义测试资产的只读内存仓库。"""

    def get_meta(self) -> dict[str, str]:
        return dict(TEST_META)

    def get_info(self) -> AssetDbInfo:
        return AssetDbInfo(
            meta=self.get_meta(),
            character_count=len(TEST_CHARACTER_ASSETS),
            weapon_count=len(TEST_WEAPON_ASSETS),
            artifact_set_count=len(TEST_ARTIFACT_SET_ASSETS),
        )

    def list_characters(self) -> tuple[CharacterAsset, ...]:
        return tuple(sorted(TEST_CHARACTER_ASSETS, key=lambda asset: asset.asset_key))

    def get_character(self, character_key: str) -> CharacterAsset:
        return self._find(
            self.list_characters(),
            lambda asset: asset.asset_key == character_key,
            f"character not found: {character_key}",
        )

    def get_character_level_stats(
        self,
        character_key: str,
        level: int,
        *,
        ascended: bool = True,
    ) -> CharacterLevelStats:
        return self._find_level_stats(
            tuple(
                stats
                for stats in TEST_CHARACTER_LEVEL_STATS
                if stats.character_key == character_key and stats.level == level
            ),
            level=level,
            ascended=ascended,
            missing=f"character level stats not found: {character_key} level {level}",
        )

    def list_weapons(self, weapon_type: str | None = None) -> tuple[WeaponAsset, ...]:
        assets = (
            asset
            for asset in TEST_WEAPON_ASSETS
            if weapon_type is None or asset.weapon_type == weapon_type
        )
        return tuple(sorted(assets, key=lambda asset: asset.asset_key))

    def get_weapon(self, weapon_key: str) -> WeaponAsset:
        return self._find(
            self.list_weapons(),
            lambda asset: asset.asset_key == weapon_key,
            f"weapon not found: {weapon_key}",
        )

    def get_weapon_level_stats(
        self,
        weapon_key: str,
        level: int,
        *,
        ascended: bool = True,
    ) -> WeaponLevelStats:
        return self._find_level_stats(
            tuple(
                stats
                for stats in TEST_WEAPON_LEVEL_STATS
                if stats.weapon_key == weapon_key and stats.level == level
            ),
            level=level,
            ascended=ascended,
            missing=f"weapon level stats not found: {weapon_key} level {level}",
        )

    def list_artifact_sets(self) -> tuple[ArtifactSetAsset, ...]:
        return tuple(sorted(TEST_ARTIFACT_SET_ASSETS, key=lambda asset: asset.asset_key))

    def get_artifact_set(self, artifact_set_key: str) -> ArtifactSetAsset:
        return self._find(
            self.list_artifact_sets(),
            lambda asset: asset.asset_key == artifact_set_key,
            f"artifact set not found: {artifact_set_key}",
        )

    def get_artifact_set_bonuses(
        self,
        artifact_set_key: str,
        piece_count: int | None = None,
    ) -> tuple[ArtifactSetBonus, ...]:
        bonuses = (
            bonus
            for bonus in TEST_ARTIFACT_SET_BONUSES
            if bonus.artifact_set_key == artifact_set_key
            and (piece_count is None or bonus.piece_count == piece_count)
        )
        return tuple(sorted(bonuses, key=lambda bonus: (bonus.piece_count, bonus.handler_key)))

    def get_talent_scalings(
        self,
        character_key: str,
        talent_key: str,
    ) -> tuple[TalentScalingEntry, ...]:
        return tuple(
            entry
            for entry in TEST_TALENT_SCALINGS
            if entry.character_key == character_key and entry.talent_key == talent_key
        )

    def get_effect_payloads(
        self,
        owner_key: str,
        effect_kind: str | None = None,
    ) -> tuple[EffectPayload, ...]:
        return ()

    def _find[AssetT](self, assets: tuple[AssetT, ...], match, missing: str) -> AssetT:
        for asset in assets:
            if match(asset):
                return asset
        raise AssetNotFoundError(missing)

    def _find_level_stats[StatsT: _LevelStatsLike](
        self,
        rows: tuple[StatsT, ...],
        *,
        level: int,
        ascended: bool,
        missing: str,
    ) -> StatsT:
        if not rows:
            raise AssetNotFoundError(missing)
        # 与 SQLite 仓库一致：可突破等级按突破状态取前/后相位，其余取最高相位。
        if ascended or level not in _ASCENDABLE_LEVELS:
            return max(rows, key=lambda stats: stats.ascension_phase)
        return min(rows, key=lambda stats: stats.ascension_phase)
