"""共享的内存资产仓库替身，实现结构化 AssetRepository 协议。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from genshin_sim.assets import (
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

_DEFAULT_CHARACTER = CharacterAsset(
    asset_key="character:75",
    source_id="75",
    name="test",
    element="hydro",
    weapon_type="sword",
    rarity=5,
    burst_energy_cost=60.0,
    handler_key="generic.test_character",
)
_DEFAULT_WEAPON = WeaponAsset(
    asset_key="weapon:11512",
    source_id="11512",
    name="test weapon",
    weapon_type="sword",
    rarity=5,
    handler_key="generic.test_weapon",
)
_DEFAULT_ARTIFACT_SET = ArtifactSetAsset(
    asset_key="artifact_set:15032",
    source_id="15032",
    name="test set",
    handler_key="generic.test_artifact_set",
)


class FakeAssetRepository:
    """可配置的内存资产仓库。

    用数据构造；未提供记录或未配置工厂的查询抛 ``LookupError``。
    """

    def __init__(
        self,
        *,
        meta: Mapping[str, str] | None = None,
        characters: Sequence[CharacterAsset] | None = None,
        weapons: Sequence[WeaponAsset] | None = None,
        artifact_sets: Sequence[ArtifactSetAsset] | None = None,
        character_level_stats: Sequence[CharacterLevelStats] = (),
        weapon_level_stats: Sequence[WeaponLevelStats] = (),
        artifact_set_bonuses: Sequence[ArtifactSetBonus] | None = None,
        talent_scalings: Sequence[TalentScalingEntry] = (),
        effect_payloads: Sequence[EffectPayload] | None = None,
        character_level_stats_factory: (
            Callable[[str, int, bool], CharacterLevelStats] | None
        ) = None,
        weapon_level_stats_factory: Callable[[str, int, bool], WeaponLevelStats] | None = None,
        missing_error: type[Exception] = LookupError,
    ) -> None:
        self._meta = dict(meta if meta is not None else {"schema_version": "2"})
        self.characters = {
            asset.asset_key: asset
            for asset in (characters if characters is not None else (_DEFAULT_CHARACTER,))
        }
        self.weapons = {
            asset.asset_key: asset
            for asset in (weapons if weapons is not None else (_DEFAULT_WEAPON,))
        }
        self.artifact_sets = {
            asset.asset_key: asset
            for asset in (artifact_sets if artifact_sets is not None else (_DEFAULT_ARTIFACT_SET,))
        }
        self.character_level_stats = tuple(character_level_stats)
        self.weapon_level_stats = tuple(weapon_level_stats)
        self.artifact_set_bonuses = tuple(
            artifact_set_bonuses
            if artifact_set_bonuses is not None
            else (
                ArtifactSetBonus(
                    artifact_set_key="artifact_set:15032",
                    piece_count=4,
                    handler_key="generic.static_modifiers",
                    params={"schema_version": 1},
                ),
            )
        )
        self.talent_scalings = tuple(talent_scalings)
        self.effect_payloads = tuple(
            effect_payloads
            if effect_payloads is not None
            else (
                EffectPayload(
                    effect_key="effect:char",
                    owner_type="character",
                    owner_key="character:75",
                    effect_kind="passive",
                    handler_key="generic.static_modifiers",
                    params={"schema_version": 1},
                ),
            )
        )
        self._character_level_stats_factory = (
            character_level_stats_factory or _default_character_level_stats
        )
        self._weapon_level_stats_factory = weapon_level_stats_factory or _default_weapon_level_stats
        self._missing_error = missing_error

    def get_meta(self) -> dict[str, str]:
        return dict(self._meta)

    def get_info(self) -> AssetDbInfo:
        return AssetDbInfo(
            meta=self.get_meta(),
            character_count=len(self.characters),
            weapon_count=len(self.weapons),
            artifact_set_count=len(self.artifact_sets),
        )

    def list_characters(self) -> tuple[CharacterAsset, ...]:
        return tuple(self.characters.values())

    def get_character(self, character_key: str) -> CharacterAsset:
        try:
            return self.characters[character_key]
        except KeyError as exc:
            raise self._missing_error(f"missing character {character_key}") from exc

    def get_character_level_stats(
        self,
        character_key: str,
        level: int,
        *,
        ascended: bool = True,
    ) -> CharacterLevelStats:
        for stats in self.character_level_stats:
            if stats.character_key == character_key and stats.level == level:
                return stats
        if self._character_level_stats_factory is not None:
            return self._character_level_stats_factory(character_key, level, ascended)
        raise self._missing_error(f"missing character stats {character_key}")

    def list_weapons(self, weapon_type: str | None = None) -> tuple[WeaponAsset, ...]:
        if weapon_type is None:
            return tuple(self.weapons.values())
        return tuple(
            weapon for weapon in self.weapons.values() if weapon.weapon_type == weapon_type
        )

    def get_weapon(self, weapon_key: str) -> WeaponAsset:
        try:
            return self.weapons[weapon_key]
        except KeyError as exc:
            raise self._missing_error(f"missing weapon {weapon_key}") from exc

    def get_weapon_level_stats(
        self,
        weapon_key: str,
        level: int,
        *,
        ascended: bool = True,
    ) -> WeaponLevelStats:
        for stats in self.weapon_level_stats:
            if stats.weapon_key == weapon_key and stats.level == level:
                return stats
        if self._weapon_level_stats_factory is not None:
            return self._weapon_level_stats_factory(weapon_key, level, ascended)
        raise self._missing_error(f"missing weapon stats {weapon_key}")

    def list_artifact_sets(self) -> tuple[ArtifactSetAsset, ...]:
        return tuple(self.artifact_sets.values())

    def get_artifact_set(self, artifact_set_key: str) -> ArtifactSetAsset:
        try:
            return self.artifact_sets[artifact_set_key]
        except KeyError as exc:
            raise self._missing_error(f"missing artifact set {artifact_set_key}") from exc

    def get_artifact_set_bonuses(
        self,
        artifact_set_key: str,
        piece_count: int | None = None,
    ) -> tuple[ArtifactSetBonus, ...]:
        return tuple(
            bonus
            for bonus in self.artifact_set_bonuses
            if bonus.artifact_set_key == artifact_set_key
            and (piece_count is None or bonus.piece_count == piece_count)
        )

    def get_talent_scalings(
        self,
        character_key: str,
        talent_key: str,
    ) -> tuple[TalentScalingEntry, ...]:
        return tuple(
            entry
            for entry in self.talent_scalings
            if entry.character_key == character_key and entry.talent_key == talent_key
        )

    def get_effect_payloads(
        self,
        owner_key: str,
        effect_kind: str | None = None,
    ) -> tuple[EffectPayload, ...]:
        return tuple(
            payload
            for payload in self.effect_payloads
            if payload.owner_key == owner_key
            and (effect_kind is None or payload.effect_kind == effect_kind)
        )


def _default_character_level_stats(
    character_key: str,
    level: int,
    ascended: bool,
) -> CharacterLevelStats:
    if level != 90 or not ascended:
        raise LookupError(f"missing character stats {character_key}")
    return CharacterLevelStats(
        character_key=character_key,
        level=level,
        ascension_phase=6,
        base_hp=10000,
        base_atk=1000,
        base_def=700,
    )


def _default_weapon_level_stats(
    weapon_key: str,
    level: int,
    ascended: bool,
) -> WeaponLevelStats:
    if level != 90 or not ascended:
        raise LookupError(f"missing weapon stats {weapon_key}")
    return WeaponLevelStats(
        weapon_key=weapon_key,
        level=level,
        ascension_phase=6,
        base_atk=500,
    )
