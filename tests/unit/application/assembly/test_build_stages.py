from __future__ import annotations

import pytest

from genshin_sim.application.assembly.errors import (
    MissingRuntimeAssetError,
    MissingRuntimeHandlerError,
)
from genshin_sim.application.assembly.stages import (
    AssetBundleLoader,
    ConfigTranslator,
    ContentCompiler,
)
from genshin_sim.application.config import SimulationConfig
from genshin_sim.assets import AssetDbInfo
from genshin_sim.assets.models import (
    ArtifactSetAsset,
    CharacterAsset,
    CharacterLevelStats,
    WeaponAsset,
    WeaponLevelStats,
)
from genshin_sim.content.bootstrap_content_units import (
    create_default_content_unit_registry,
)
from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
)
from genshin_sim.content.registries import (
    CharacterContentUnitRequest,
    ContentUnitRegistry,
)
from genshin_sim.core.contracts.state_schema import (
    StateField,
    StateFieldType,
    StateSchema,
)


def _minimal_config_payload(*, team: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "simulation_config",
        "meta": {"name": "stage test", "description": ""},
        "team": team,
        "scene": {"targets": []},
        "input_trace": [],
        "rules": {"enabled": []},
        "run_options": {"max_frames": 10},
    }


def _single_character_team(asset_key: str) -> list[dict[str, object]]:
    return [
        {
            "slot": 1,
            "character": {
                "asset_key": asset_key,
                "level": 90,
                "constellation": 0,
                "talents": {"normal_attack": 1},
            },
        }
    ]


class StageAssetRepository:
    def __init__(self, *, raise_on_character: bool = False) -> None:
        self.raise_on_character = raise_on_character

    def get_character(self, character_key: str) -> CharacterAsset:
        if self.raise_on_character:
            raise LookupError(f"missing character {character_key}")
        return CharacterAsset(
            asset_key=character_key,
            source_id="stage_test",
            name="stage",
            element="hydro",
            weapon_type="sword",
            rarity=5,
            burst_energy_cost=60.0,
        )

    def get_meta(self) -> dict[str, str]:
        return {}

    def get_info(self) -> AssetDbInfo:
        return AssetDbInfo(meta={})

    def list_characters(self) -> tuple[CharacterAsset, ...]:
        return ()

    def get_character_level_stats(
        self,
        character_key: str,
        level: int,
        *,
        ascended: bool = True,
    ) -> CharacterLevelStats:
        del ascended
        return CharacterLevelStats(
            character_key=character_key,
            level=level,
            ascension_phase=0,
            base_hp=1000,
            base_atk=100,
            base_def=50,
        )

    def list_weapons(self, weapon_type: str | None = None) -> tuple[()]:
        del weapon_type
        return ()

    def get_weapon(self, weapon_key: str) -> WeaponAsset:
        raise LookupError(f"missing weapon {weapon_key}")

    def get_weapon_level_stats(
        self,
        weapon_key: str,
        level: int,
        *,
        ascended: bool = True,
    ) -> WeaponLevelStats:
        del ascended
        raise LookupError(f"missing weapon stats {weapon_key}")

    def list_artifact_sets(self) -> tuple[()]:
        return ()

    def get_artifact_set(self, artifact_set_key: str) -> ArtifactSetAsset:
        raise LookupError(f"missing artifact set {artifact_set_key}")

    def get_artifact_set_bonuses(
        self,
        artifact_set_key: str,
        piece_count: int | None = None,
    ) -> tuple[()]:
        del artifact_set_key, piece_count
        return ()

    def get_talent_scalings(self, character_key: str, talent_key: str) -> tuple[()]:
        del character_key, talent_key
        return ()

    def get_effect_payloads(
        self,
        owner_key: str,
        effect_kind: str | None = None,
    ) -> tuple[()]:
        del owner_key, effect_kind
        return ()


class StageAssetRepositoryWithHandler(StageAssetRepository):
    def get_character(self, character_key: str) -> CharacterAsset:
        return CharacterAsset(
            asset_key=character_key,
            source_id="stage_test",
            name="stage",
            element="hydro",
            weapon_type="sword",
            rarity=5,
            burst_energy_cost=60.0,
            handler_key="character.stage_contributed",
        )


def _single_character_config() -> SimulationConfig:
    return ConfigTranslator().translate_mapping(
        _minimal_config_payload(team=_single_character_team("character:stage_test"))
    )


def test_config_translator_translates_mapping_and_keeps_identity():
    translator = ConfigTranslator()
    config = translator.translate_mapping(
        _minimal_config_payload(team=_single_character_team("character:stage_test"))
    )

    assert translator.translate(config) is config
    assert config.team[0].character.asset_key == "character:stage_test"


def test_config_translator_rejects_empty_team():
    translator = ConfigTranslator()

    with pytest.raises(MissingRuntimeAssetError, match="队伍槽位"):
        translator.translate_mapping(_minimal_config_payload(team=[]))


def test_asset_loader_loads_single_character_bundle():
    loader = AssetBundleLoader(StageAssetRepository())

    bundles = loader.load(_single_character_config())

    assert len(bundles) == 1
    assert bundles[0].slot == 1
    assert bundles[0].weapon is None
    assert bundles[0].artifact_sets == ()
    assert bundles[0].artifact_bonuses == ()
    assert bundles[0].effect_payloads == ()


def test_asset_loader_reports_missing_asset_at_query_stage():
    loader = AssetBundleLoader(StageAssetRepository(raise_on_character=True))

    with pytest.raises(MissingRuntimeAssetError, match="槽位 1"):
        loader.load(_single_character_config())


def test_content_compiler_compiles_empty_content_units():
    compiler = ContentCompiler(ContentUnitRegistry())

    assets = AssetBundleLoader(StageAssetRepository()).load(_single_character_config())
    bundle = compiler.compile(_single_character_config(), assets)

    assert bundle.content_units == ()
    assert bundle.action_interpreters == {}
    assert bundle.actions == ()
    assert bundle.impact_factories == {}


def test_content_compiler_missing_handler_fails_at_compile_stage():
    compiler = ContentCompiler(ContentUnitRegistry())
    assets = AssetBundleLoader(StageAssetRepositoryWithHandler()).load(_single_character_config())

    with pytest.raises(MissingRuntimeHandlerError, match="handler"):
        compiler.compile(_single_character_config(), assets)


def test_content_compiler_instantiates_state_container_from_unit_schema():
    unit_registry = ContentUnitRegistry()

    def factory(request: CharacterContentUnitRequest) -> ContentUnit:
        return ContentUnit(
            owner_type=ContentUnitOwnerType.CHARACTER,
            owner_key=request.character_key,
            handler_key=request.handler_key,
            version="dev-m3c",
            slot=request.slot,
            state_schema=StateSchema(
                owner_ref=f"character:slot_{request.slot}",
                fields=(
                    StateField(
                        name="stacks",
                        field_type=StateFieldType.INT,
                        default=0,
                        non_negative=True,
                        max_value=3,
                    ),
                ),
            ),
        )

    unit_registry.register_character_factory("character.stage_contributed", factory)
    compiler = ContentCompiler(unit_registry)
    assets = AssetBundleLoader(StageAssetRepositoryWithHandler()).load(_single_character_config())

    bundle = compiler.compile(_single_character_config(), assets)

    assert len(bundle.content_units) == 1
    assert len(bundle.content_state_mounts) == 1
    mount = bundle.content_state_mounts[0]
    assert mount.owner == "character:slot_1"
    assert mount.state_key == "character.stage_contributed"
    assert mount.values == {"stacks": 0}


def test_content_compiler_uses_default_content_unit_registry_path():
    class RuntimeProbeRepository(StageAssetRepositoryWithHandler):
        def get_character(self, character_key: str) -> CharacterAsset:
            return CharacterAsset(
                asset_key=character_key,
                source_id="stage_test",
                name="runtime probe",
                element="hydro",
                weapon_type="catalyst",
                rarity=5,
                burst_energy_cost=60.0,
                handler_key="character.testing.runtime_probe",
            )

    compiler = ContentCompiler(create_default_content_unit_registry())
    assets = AssetBundleLoader(RuntimeProbeRepository()).load(_single_character_config())

    bundle = compiler.compile(_single_character_config(), assets)

    assert len(bundle.content_units) == 1
    assert bundle.content_units[0].handler_key == "character.testing.runtime_probe"
    assert 1 in bundle.action_interpreters
    assert bundle.content_state_mounts == ()
