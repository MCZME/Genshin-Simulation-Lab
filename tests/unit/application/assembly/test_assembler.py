from __future__ import annotations

from typing import Any, cast

import pytest

from genshin_sim.application.assembly import (
    MissingRuntimeAssetError,
    MissingRuntimeHandlerError,
    SimulationAssembler,
)
from genshin_sim.application.config import SimulationConfig
from genshin_sim.assets import AssetDbInfo
from genshin_sim.assets.models import (
    ArtifactSetAsset,
    ArtifactSetBonus,
    CharacterAsset,
    CharacterLevelStats,
    EffectPayload,
    WeaponAsset,
    WeaponLevelStats,
)
from genshin_sim.content import create_default_registry


class BrokenRegistry:
    def create(self, target):
        raise LookupError("missing handler")


class FakeAssetRepository:
    def __init__(self) -> None:
        self.character = CharacterAsset(
            asset_key="character:75",
            source_id="75",
            name="test",
            element="hydro",
            weapon_type="sword",
            rarity=5,
            handler_key="generic.test_character",
        )
        self.weapon = WeaponAsset(
            asset_key="weapon:11512",
            source_id="11512",
            name="test weapon",
            weapon_type="sword",
            rarity=5,
            handler_key="generic.test_weapon",
        )
        self.artifact_set = ArtifactSetAsset(
            asset_key="artifact_set:15032",
            source_id="15032",
            name="test set",
            handler_key="generic.test_artifact_set",
        )

    def get_meta(self) -> dict[str, str]:
        return {"schema_version": "1"}

    def get_info(self) -> AssetDbInfo:
        return AssetDbInfo(meta={"schema_version": "1"})

    def list_characters(self):
        return (self.character,)

    def get_character(self, character_key: str):
        assert character_key == self.character.asset_key
        return self.character

    def get_character_level_stats(self, character_key: str, level: int):
        assert character_key == self.character.asset_key
        assert level == 90
        return CharacterLevelStats(
            character_key=character_key,
            level=level,
            ascension_phase=6,
            base_hp=10000,
            base_atk=1000,
            base_def=700,
        )

    def list_weapons(self, weapon_type: str | None = None):
        return (self.weapon,)

    def get_weapon(self, weapon_key: str):
        assert weapon_key == self.weapon.asset_key
        return self.weapon

    def get_weapon_level_stats(self, weapon_key: str, level: int):
        assert weapon_key == self.weapon.asset_key
        assert level == 90
        return WeaponLevelStats(
            weapon_key=weapon_key,
            level=level,
            ascension_phase=6,
            base_atk=500,
        )

    def list_artifact_sets(self):
        return (self.artifact_set,)

    def get_artifact_set(self, artifact_set_key: str):
        assert artifact_set_key == self.artifact_set.asset_key
        return self.artifact_set

    def get_artifact_set_bonuses(self, artifact_set_key: str, piece_count: int | None = None):
        assert artifact_set_key == self.artifact_set.asset_key
        return (
            ArtifactSetBonus(
                artifact_set_key=artifact_set_key,
                piece_count=4,
                handler_key="generic.static_modifiers",
                params={"schema_version": 1},
            ),
        )

    def get_talent_scalings(self, character_key: str, talent_key: str):
        return ()

    def get_effect_payloads(self, owner_key: str, effect_kind: str | None = None):
        if owner_key == self.character.asset_key:
            return (
                EffectPayload(
                    effect_key="effect:char",
                    owner_type="character",
                    owner_key=owner_key,
                    effect_kind="passive",
                    handler_key="generic.static_modifiers",
                    params={"schema_version": 1},
                ),
            )
        return ()


def _minimal_config() -> SimulationConfig:
    return SimulationConfig.from_mapping(
        {
            "schema_version": 1,
            "kind": "simulation_config",
            "meta": {"name": "demo", "description": ""},
            "team": [
                {
                    "slot": 1,
                    "character": {
                        "asset_key": "character:75",
                        "level": 90,
                        "constellation": 2,
                        "talents": {"normal_attack": 1},
                    },
                    "weapon": {
                        "asset_key": "weapon:11512",
                        "level": 90,
                        "refinement": 1,
                    },
                    "artifacts": {
                        "sets": [
                            {"asset_key": "artifact_set:15032", "pieces": 4},
                        ],
                        "stats": {},
                    },
                }
            ],
            "scene": {
                "targets": [
                    {
                        "id": "target_1",
                        "level": 90,
                        "position": {"x": 0, "y": 0, "z": 0},
                        "resistance": {},
                    }
                ]
            },
            "input_trace": [
                {"frame": 1, "events": [{"key": "keyboard.e", "phase": "press"}]},
                {"frame": 2, "events": [{"key": "keyboard.e", "phase": "release"}]},
            ],
            "rules": {"enabled": []},
            "run_options": {"max_frames": 10},
        }
    )


def test_assembler_builds_minimal_runtime_graph():
    assembler = SimulationAssembler(FakeAssetRepository(), create_default_registry())
    assembled = assembler.assemble(_minimal_config())

    assert assembled.context.space is not None
    assert assembled.simulator.max_frames == 10
    assert assembled.action_manager.is_idle()


def test_assembler_raises_for_missing_asset():
    class BrokenRepository(FakeAssetRepository):
        def get_character(self, character_key: str):
            raise LookupError(character_key)

    assembler = SimulationAssembler(BrokenRepository(), create_default_registry())

    with pytest.raises(MissingRuntimeAssetError):
        assembler.assemble(_minimal_config())


def test_assembler_raises_for_missing_handler():
    assembler = SimulationAssembler(
        FakeAssetRepository(),
        cast(Any, BrokenRegistry()),
    )

    with pytest.raises(MissingRuntimeHandlerError):
        assembler.assemble(_minimal_config())
