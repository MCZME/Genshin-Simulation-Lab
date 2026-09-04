"""只读资产仓库的组合视图。

主仓库优先、回退仓库兜底：实体资产与等级数值按"主库命中否则回退"取数
（主库以 AssetNotFoundError 表示未命中）；列表、套装加成、天赋倍率与
effect payload 采用合并去重——这些查询对不存在的键返回空结果而非报错，
空是合法值。元信息始终取主仓库。用于开发者模式把代码定义的测试资产
叠加在正式资产库之上。
"""

from __future__ import annotations

from collections.abc import Callable

from genshin_sim.assets.errors import AssetError
from genshin_sim.assets.models import (
    ArtifactSetAsset,
    ArtifactSetBonus,
    AssetDbInfo,
    CharacterAsset,
    CharacterLevelStats,
    EffectPayload,
    TalentScalingEntry,
    WeaponAsset,
    WeaponLevelStats,
)
from genshin_sim.assets.repository import AssetRepository


class CompositeAssetRepository:
    """按 asset_key 组合两个只读资产仓库。"""

    def __init__(self, primary: AssetRepository, fallback: AssetRepository) -> None:
        self._primary = primary
        self._fallback = fallback

    def get_meta(self) -> dict[str, str]:
        return self._primary.get_meta()

    def get_info(self) -> AssetDbInfo:
        return self._primary.get_info()

    def list_characters(self) -> tuple[CharacterAsset, ...]:
        return self._merge(
            self._primary.list_characters(),
            self._fallback.list_characters(),
            key=lambda asset: asset.asset_key,
        )

    def get_character(self, character_key: str) -> CharacterAsset:
        return self._get(
            lambda: self._primary.get_character(character_key),
            lambda: self._fallback.get_character(character_key),
        )

    def get_character_level_stats(
        self,
        character_key: str,
        level: int,
        *,
        ascended: bool = True,
    ) -> CharacterLevelStats:
        return self._get(
            lambda: self._primary.get_character_level_stats(
                character_key,
                level,
                ascended=ascended,
            ),
            lambda: self._fallback.get_character_level_stats(
                character_key,
                level,
                ascended=ascended,
            ),
        )

    def list_weapons(self, weapon_type: str | None = None) -> tuple[WeaponAsset, ...]:
        return self._merge(
            self._primary.list_weapons(weapon_type),
            self._fallback.list_weapons(weapon_type),
            key=lambda asset: asset.asset_key,
        )

    def get_weapon(self, weapon_key: str) -> WeaponAsset:
        return self._get(
            lambda: self._primary.get_weapon(weapon_key),
            lambda: self._fallback.get_weapon(weapon_key),
        )

    def get_weapon_level_stats(
        self,
        weapon_key: str,
        level: int,
        *,
        ascended: bool = True,
    ) -> WeaponLevelStats:
        return self._get(
            lambda: self._primary.get_weapon_level_stats(
                weapon_key,
                level,
                ascended=ascended,
            ),
            lambda: self._fallback.get_weapon_level_stats(
                weapon_key,
                level,
                ascended=ascended,
            ),
        )

    def list_artifact_sets(self) -> tuple[ArtifactSetAsset, ...]:
        return self._merge(
            self._primary.list_artifact_sets(),
            self._fallback.list_artifact_sets(),
            key=lambda asset: asset.asset_key,
        )

    def get_artifact_set(self, artifact_set_key: str) -> ArtifactSetAsset:
        return self._get(
            lambda: self._primary.get_artifact_set(artifact_set_key),
            lambda: self._fallback.get_artifact_set(artifact_set_key),
        )

    def get_artifact_set_bonuses(
        self,
        artifact_set_key: str,
        piece_count: int | None = None,
    ) -> tuple[ArtifactSetBonus, ...]:
        # 套装加成允许为空（存在无加成行的套装），用合并去重而不是空即回退。
        return self._merge(
            self._primary.get_artifact_set_bonuses(artifact_set_key, piece_count),
            self._fallback.get_artifact_set_bonuses(artifact_set_key, piece_count),
            key=lambda bonus: bonus.piece_count,
        )

    def get_talent_scalings(
        self,
        character_key: str,
        talent_key: str,
    ) -> tuple[TalentScalingEntry, ...]:
        # SQLite 对未知角色返回空元组而非报错，因此用合并去重而不是异常回退。
        return self._merge(
            self._primary.get_talent_scalings(character_key, talent_key),
            self._fallback.get_talent_scalings(character_key, talent_key),
            key=lambda entry: entry.entry_key,
        )

    def get_effect_payloads(
        self,
        owner_key: str,
        effect_kind: str | None = None,
    ) -> tuple[EffectPayload, ...]:
        # effect payload 按 owner 叠加：主库与回退库的声明合并生效。
        return self._merge(
            self._primary.get_effect_payloads(owner_key, effect_kind),
            self._fallback.get_effect_payloads(owner_key, effect_kind),
            key=lambda payload: (payload.effect_key, payload.effect_kind),
        )

    def _get[AssetT](
        self,
        primary_lookup: Callable[[], AssetT],
        fallback_lookup: Callable[[], AssetT],
    ) -> AssetT:
        try:
            return primary_lookup()
        except AssetError:
            return fallback_lookup()

    def _merge[AssetT](
        self,
        primary_items: tuple[AssetT, ...],
        fallback_items: tuple[AssetT, ...],
        *,
        key,
    ) -> tuple[AssetT, ...]:
        primary_keys = {key(item) for item in primary_items}
        merged = tuple(primary_items) + tuple(
            item for item in fallback_items if key(item) not in primary_keys
        )
        return merged
