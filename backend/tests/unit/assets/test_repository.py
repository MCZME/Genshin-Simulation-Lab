from __future__ import annotations

from genshin_sim.assets import (
    ArtifactSetAsset,
    ArtifactSetBonus,
    AssetRepository,
    CharacterAsset,
    CharacterLevelStats,
    EffectPayload,
    TalentScalingEntry,
    WeaponAsset,
    WeaponLevelStats,
)
from tests.helpers.asset_repository import FakeAssetRepository


class MemoryAssetRepository(FakeAssetRepository):
    def __init__(self) -> None:
        super().__init__(
            meta={"schema_version": "1", "data_version": "test"},
            characters=(
                CharacterAsset(
                    asset_key="character:75",
                    source_id="75",
                    name="Furina",
                    element="hydro",
                    weapon_type="sword",
                    rarity=5,
                    handler_key="character.furina",
                ),
            ),
            weapons=(
                WeaponAsset(
                    asset_key="weapon:11512",
                    source_id="11512",
                    name="Splendor of Tranquil Waters",
                    weapon_type="sword",
                    rarity=5,
                    handler_key="weapon.splendor_of_tranquil_waters",
                ),
            ),
            artifact_sets=(
                ArtifactSetAsset(
                    asset_key="artifact_set:15032",
                    source_id="15032",
                    name="Golden Troupe",
                    handler_key="artifact.golden_troupe",
                ),
            ),
            character_level_stats=(
                CharacterLevelStats(
                    character_key="character:75",
                    level=90,
                    ascension_phase=6,
                    base_hp=15307.0,
                    base_atk=244.0,
                    base_def=696.0,
                ),
            ),
            weapon_level_stats=(
                WeaponLevelStats(
                    weapon_key="weapon:11512",
                    level=90,
                    ascension_phase=6,
                    base_atk=542.0,
                    secondary_stat="crit_damage",
                    secondary_value=0.882,
                ),
            ),
            artifact_set_bonuses=(
                ArtifactSetBonus(
                    artifact_set_key="artifact_set:15032",
                    piece_count=4,
                    handler_key="artifact.golden_troupe.4pc",
                    params={"schema_version": 1, "params": {}},
                ),
            ),
            talent_scalings=(
                TalentScalingEntry(
                    character_key="character:75",
                    talent_key="elemental_skill",
                    entry_key="salon_member_damage",
                    label="Salon Member Damage",
                    scaling={"schema_version": 1, "mode": "constant", "components": []},
                ),
            ),
            effect_payloads=(
                EffectPayload(
                    effect_key="weapon:11512:passive",
                    owner_type="weapon",
                    owner_key="weapon:11512",
                    effect_kind="passive",
                    handler_key="weapon.splendor_of_tranquil_waters",
                    params={"schema_version": 1, "params": {}},
                ),
            ),
        )


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
