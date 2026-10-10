"""套装效果行绑定的单元必须有所属单元。

对应 D-079 与 ``docs/架构/内容系统设计.md`` 第 4.4 节：套装索引行绑定「这个套装
是什么」的单元，它拥有该套装件数效果行绑定的单元。索引行未绑定时，件数效果行
只应绑定占位键（不产出单元）；一旦产出了单元，说明该套装已接入，索引行必须同时
绑定单元键。
"""

from __future__ import annotations

import pytest

from genshin_sim.application.assembly.errors import InvalidRuntimePayloadError
from genshin_sim.application.assembly.stages import (
    AssetBundleLoader,
    ConfigTranslator,
    ContentCompiler,
)
from genshin_sim.assets.models import ArtifactSetAsset, ArtifactSetBonus, CharacterAsset
from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
)
from genshin_sim.content.registries import (
    ArtifactContentUnitRequest,
    ContentUnitRegistry,
)
from tests.helpers.asset_repository import FakeAssetRepository

_CHARACTER_KEY = "character:ownership_fixture"
_SET_KEY = "artifact_set:ownership_fixture"
_SET_ROW_KEY = "artifact.ownership_fixture"
_BONUS_KEY = "artifact.ownership_fixture.2p"

_CONTENT_VERSION = "dev-ownership"


def _unit(handler_key: str, owner_key: str) -> ContentUnit:
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=owner_key,
        handler_key=handler_key,
        version=_CONTENT_VERSION,
        slot=1,
    )


def test_bonus_unit_without_set_row_unit_is_rejected():
    with pytest.raises(InvalidRuntimePayloadError, match="没有绑定索引行单元"):
        ContentCompiler._validate_artifact_unit_ownership(
            (),
            (_unit(_BONUS_KEY, _SET_KEY),),
        )


def test_bonus_unit_with_set_row_unit_passes():
    ContentCompiler._validate_artifact_unit_ownership(
        (_unit(_SET_ROW_KEY, _SET_KEY),),
        (_unit(_BONUS_KEY, _SET_KEY),),
    )


def test_set_row_unit_of_another_set_does_not_own_the_bonus_unit():
    with pytest.raises(InvalidRuntimePayloadError, match="没有绑定索引行单元"):
        ContentCompiler._validate_artifact_unit_ownership(
            (_unit(_SET_ROW_KEY, "artifact_set:another_fixture"),),
            (_unit(_BONUS_KEY, _SET_KEY),),
        )


def test_units_without_bonus_row_are_not_checked():
    ContentCompiler._validate_artifact_unit_ownership((), ())


def _artifact_factory(request: ArtifactContentUnitRequest) -> ContentUnit:
    return _unit(request.handler_key, request.artifact_key)


def _compile(*, set_row_key: str | None) -> None:
    registry = ContentUnitRegistry()
    registry.register_artifact_factory(_SET_ROW_KEY, _artifact_factory)
    registry.register_artifact_factory(_BONUS_KEY, _artifact_factory)

    repository = FakeAssetRepository(
        characters=(
            CharacterAsset(
                asset_key=_CHARACTER_KEY,
                source_id="ownership_fixture",
                name="ownership fixture",
                element="hydro",
                weapon_type="sword",
                rarity=5,
                burst_energy_cost=60.0,
                handler_key=None,
            ),
        ),
        weapons=(),
        artifact_sets=(
            ArtifactSetAsset(
                asset_key=_SET_KEY,
                source_id="ownership_fixture",
                name="ownership fixture",
                handler_key=set_row_key,
            ),
        ),
        artifact_set_bonuses=(
            ArtifactSetBonus(
                artifact_set_key=_SET_KEY,
                piece_count=2,
                handler_key=_BONUS_KEY,
                params={"schema_version": 1},
            ),
        ),
        effect_payloads=(),
    )
    config = ConfigTranslator().translate_mapping(
        {
            "schema_version": 2,
            "kind": "simulation_input",
            "meta": {"name": "artifact ownership test", "description": ""},
            "team": [
                {
                    "slot": 1,
                    "character": {
                        "asset_key": _CHARACTER_KEY,
                        "level": 90,
                        "constellation": 0,
                        "talents": {"normal_attack": 1},
                    },
                    "artifacts": {
                        "sets": [{"asset_key": _SET_KEY, "pieces": 2}],
                        "stats": {},
                    },
                }
            ],
            "scene": {"targets": []},
            "input_trace": [],
            "rules": {"active": []},
            "run_options": {"max_frames": 10},
        }
    )
    assets = AssetBundleLoader(repository).load(config)
    ContentCompiler(registry).compile(config, assets)


def test_compiler_rejects_bonus_unit_without_bound_set_row():
    with pytest.raises(InvalidRuntimePayloadError, match="没有绑定索引行单元"):
        _compile(set_row_key=None)


def test_compiler_accepts_bonus_unit_with_bound_set_row():
    _compile(set_row_key=_SET_ROW_KEY)
