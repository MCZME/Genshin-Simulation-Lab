from __future__ import annotations

from typing import Protocol, runtime_checkable

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


@runtime_checkable
class AssetRepository(Protocol):
    """Read-only access to assembled asset data."""

    def get_meta(self) -> dict[str, str]: ...

    def get_info(self) -> AssetDbInfo: ...

    def list_characters(self) -> tuple[CharacterAsset, ...]: ...

    def get_character(self, character_key: str) -> CharacterAsset: ...

    def get_character_level_stats(
        self,
        character_key: str,
        level: int,
        *,
        ascended: bool = True,
    ) -> CharacterLevelStats: ...

    def list_weapons(self, weapon_type: str | None = None) -> tuple[WeaponAsset, ...]: ...

    def get_weapon(self, weapon_key: str) -> WeaponAsset: ...

    def get_weapon_level_stats(
        self,
        weapon_key: str,
        level: int,
        *,
        ascended: bool = True,
    ) -> WeaponLevelStats: ...

    def list_artifact_sets(self) -> tuple[ArtifactSetAsset, ...]: ...

    def get_artifact_set(self, artifact_set_key: str) -> ArtifactSetAsset: ...

    def get_artifact_set_bonuses(
        self,
        artifact_set_key: str,
        piece_count: int | None = None,
    ) -> tuple[ArtifactSetBonus, ...]: ...

    def get_talent_scalings(
        self,
        character_key: str,
        talent_key: str,
    ) -> tuple[TalentScalingEntry, ...]: ...

    def get_effect_payloads(
        self,
        owner_key: str,
        effect_kind: str | None = None,
    ) -> tuple[EffectPayload, ...]: ...
