from __future__ import annotations

from genshin_sim.assets import (
    ArtifactSetAsset,
    ArtifactSetBonus,
    AssetDbInfo,
    AssetRepository,
    CharacterAsset,
    CharacterLevelStats,
    EffectPayload,
    TalentScalingEntry,
    WeaponAsset,
    WeaponLevelStats,
)


class MemoryAssetRepository:
    def __init__(self) -> None:
        self.character = CharacterAsset(
            asset_key="character:75",
            source_id="75",
            name="Furina",
            element="hydro",
            weapon_type="sword",
            rarity=5,
            handler_key="character.furina",
        )
        self.character_stats = CharacterLevelStats(
            character_key="character:75",
            level=90,
            ascension_phase=6,
            base_hp=15307.0,
            base_atk=244.0,
            base_def=696.0,
        )
        self.weapon = WeaponAsset(
            asset_key="weapon:11512",
            source_id="11512",
            name="Splendor of Tranquil Waters",
            weapon_type="sword",
            rarity=5,
            handler_key="weapon.splendor_of_tranquil_waters",
        )
        self.weapon_stats = WeaponLevelStats(
            weapon_key="weapon:11512",
            level=90,
            ascension_phase=6,
            base_atk=542.0,
            secondary_stat="crit_damage",
            secondary_value=0.882,
        )
        self.artifact_set = ArtifactSetAsset(
            asset_key="artifact_set:15032",
            source_id="15032",
            name="Golden Troupe",
            handler_key="artifact.golden_troupe",
        )
        self.artifact_bonus = ArtifactSetBonus(
            artifact_set_key="artifact_set:15032",
            piece_count=4,
            handler_key="artifact.golden_troupe.4pc",
            params={"schema_version": 1, "params": {}},
        )
        self.scaling = TalentScalingEntry(
            character_key="character:75",
            talent_key="elemental_skill",
            entry_key="salon_member_damage",
            label="Salon Member Damage",
            scaling={"schema_version": 1, "mode": "constant", "components": []},
        )
        self.effect = EffectPayload(
            effect_key="weapon:11512:passive",
            owner_type="weapon",
            owner_key="weapon:11512",
            effect_kind="passive",
            handler_key="weapon.splendor_of_tranquil_waters",
            params={"schema_version": 1, "params": {}},
        )

    def get_meta(self) -> dict[str, str]:
        return {"schema_version": "1", "data_version": "test"}

    def get_info(self) -> AssetDbInfo:
        return AssetDbInfo(
            meta=self.get_meta(),
            character_count=1,
            weapon_count=1,
            artifact_set_count=1,
        )

    def list_characters(self) -> tuple[CharacterAsset, ...]:
        return (self.character,)

    def get_character(self, character_key: str) -> CharacterAsset:
        assert character_key == "character:75"
        return self.character

    def get_character_level_stats(
        self,
        character_key: str,
        level: int,
    ) -> CharacterLevelStats:
        assert character_key == "character:75"
        assert level == 90
        return self.character_stats

    def list_weapons(self, weapon_type: str | None = None) -> tuple[WeaponAsset, ...]:
        assert weapon_type in {None, "sword"}
        return (self.weapon,)

    def get_weapon(self, weapon_key: str) -> WeaponAsset:
        assert weapon_key == "weapon:11512"
        return self.weapon

    def get_weapon_level_stats(self, weapon_key: str, level: int) -> WeaponLevelStats:
        assert weapon_key == "weapon:11512"
        assert level == 90
        return self.weapon_stats

    def list_artifact_sets(self) -> tuple[ArtifactSetAsset, ...]:
        return (self.artifact_set,)

    def get_artifact_set(self, artifact_set_key: str) -> ArtifactSetAsset:
        assert artifact_set_key == "artifact_set:15032"
        return self.artifact_set

    def get_artifact_set_bonuses(
        self,
        artifact_set_key: str,
        piece_count: int | None = None,
    ) -> tuple[ArtifactSetBonus, ...]:
        assert artifact_set_key == "artifact_set:15032"
        assert piece_count in {None, 4}
        return (self.artifact_bonus,)

    def get_talent_scalings(
        self,
        character_key: str,
        talent_key: str,
    ) -> tuple[TalentScalingEntry, ...]:
        assert character_key == "character:75"
        assert talent_key == "elemental_skill"
        return (self.scaling,)

    def get_effect_payloads(
        self,
        owner_key: str,
        effect_kind: str | None = None,
    ) -> tuple[EffectPayload, ...]:
        assert owner_key == "weapon:11512"
        assert effect_kind in {None, "passive"}
        return (self.effect,)


def test_asset_repository_protocol_accepts_structural_implementation():
    repository: AssetRepository = MemoryAssetRepository()

    assert isinstance(repository, AssetRepository)
    assert repository.get_info().character_count == 1
    assert repository.get_character("character:75").handler_key == "character.furina"
    assert repository.get_character_level_stats("character:75", 90).base_hp == 15307.0
    assert repository.list_weapons("sword")[0].asset_key == "weapon:11512"
    assert repository.get_weapon_level_stats("weapon:11512", 90).secondary_value == 0.882
    assert repository.get_artifact_set_bonuses("artifact_set:15032", 4)[0].piece_count == 4
    assert repository.get_talent_scalings("character:75", "elemental_skill")[0].entry_key
    assert repository.get_effect_payloads("weapon:11512", "passive")[0].handler_key
