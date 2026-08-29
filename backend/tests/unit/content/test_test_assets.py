"""开发者测试资产内存仓库与注册入口的单元测试。"""

from __future__ import annotations

import pytest

from genshin_sim.assets import AssetNotFoundError
from genshin_sim.content import create_default_content_unit_registry
from genshin_sim.content.test import register_test_content_units
from genshin_sim.content.test.asset_repository import TestAssetRepository
from genshin_sim.content.test.characters.runtime_probe import (
    RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
)


def test_test_asset_repository_resolves_code_defined_assets():
    repository = TestAssetRepository()

    character = repository.get_character("character:test_character")
    assert character.handler_key == RUNTIME_PROBE_CHARACTER_HANDLER_KEY
    assert repository.get_weapon("weapon:test_sword").weapon_type == "sword"
    assert repository.get_artifact_set("artifact_set:test_set").name == "Test Set"


def test_test_asset_repository_level_stats_match_sqlite_semantics():
    repository = TestAssetRepository()

    ascended = repository.get_character_level_stats("character:test_character", 90)
    assert (ascended.base_hp, ascended.base_atk, ascended.base_def) == (10000.0, 200.0, 600.0)
    # 90 非可突破等级：ascended=False 也返回已有（最高相位）行
    not_ascending = repository.get_character_level_stats(
        "character:test_character",
        90,
        ascended=False,
    )
    assert not_ascending.ascension_phase == 6

    weapon = repository.get_weapon_level_stats("weapon:test_sword", 90)
    assert weapon.base_atk == 510.0


def test_test_asset_repository_missing_keys_raise_asset_error():
    repository = TestAssetRepository()

    with pytest.raises(AssetNotFoundError):
        repository.get_character("character:missing")
    with pytest.raises(AssetNotFoundError):
        repository.get_character_level_stats("character:test_character", 1)
    with pytest.raises(AssetNotFoundError):
        repository.get_weapon("weapon:missing")


def test_test_asset_repository_scalings_and_empty_payloads():
    repository = TestAssetRepository()

    scalings = repository.get_talent_scalings("character:test_character", "normal_attack")
    assert [entry.entry_key for entry in scalings] == ["hit_1"]
    # 测试资产未定义 effect payload：返回空而不是报错
    assert repository.get_effect_payloads("character:test_character") == ()


def test_register_test_content_units_is_idempotent_across_fresh_registries():
    first = create_default_content_unit_registry(developer_mode=True)
    second = create_default_content_unit_registry(developer_mode=True)

    assert first.handler_keys == second.handler_keys


def test_register_test_content_units_rejects_duplicate_registration():
    registry = create_default_content_unit_registry(developer_mode=True)

    with pytest.raises(Exception, match="重复 handler_key"):
        register_test_content_units(registry)
