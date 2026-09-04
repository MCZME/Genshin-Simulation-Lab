"""资产 manifest 测试共享构造器。"""

from __future__ import annotations

import json
from pathlib import Path


def write_asset_manifest(tmp_path: Path, payload: dict) -> Path:
    """把 manifest payload 写入临时目录并返回路径。"""

    manifest_path = tmp_path / "assets.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    return manifest_path


def asset_manifest_fixture_payload() -> dict:
    """全类型 manifest fixture（角色/等级/武器/圣遗物/倍率/效果）。"""

    return {
        "schema_version": 1,
        "kind": "asset_manifest",
        "meta": {
            "data_version": "fixture-1",
            "source_name": "pytest-manifest",
            "source_version": "2026.07",
        },
        "characters": [
            {
                "asset_key": "character:fixture_char",
                "source_id": "fixture_char",
                "name": "Fixture Character",
                "element": "hydro",
                "weapon_type": "sword",
                "rarity": 5,
                "burst_energy_cost": 60.0,
            }
        ],
        "character_level_stats": [
            {
                "character_key": "character:fixture_char",
                "level": 20,
                "ascension_phase": 0,
                "base_hp": 2000.0,
                "base_atk": 40.0,
                "base_def": 120.0,
            },
            {
                "character_key": "character:fixture_char",
                "level": 20,
                "ascension_phase": 1,
                "base_hp": 2200.0,
                "base_atk": 44.0,
                "base_def": 132.0,
                "ascension_stat": "hydro_damage_bonus",
                "ascension_value": 0.072,
            },
        ],
        "weapons": [
            {
                "asset_key": "weapon:fixture_sword",
                "source_id": "fixture_sword",
                "name": "Fixture Sword",
                "weapon_type": "sword",
                "rarity": 4,
            }
        ],
        "weapon_level_stats": [
            {
                "weapon_key": "weapon:fixture_sword",
                "level": 90,
                "ascension_phase": 6,
                "base_atk": 510.0,
                "secondary_stat": "atk_percent",
                "secondary_value": 0.413,
            }
        ],
        "artifact_sets": [
            {
                "asset_key": "artifact_set:fixture_set",
                "source_id": "fixture_set",
                "name": "Fixture Set",
            }
        ],
        "artifact_set_bonuses": [
            {
                "artifact_set_key": "artifact_set:fixture_set",
                "piece_count": 2,
                "handler_key": "generic.static_modifiers",
                "params": {
                    "schema_version": 1,
                    "params": {"stat": "atk_percent", "value": 0.18},
                },
            }
        ],
        "talent_scalings": [
            {
                "character_key": "character:fixture_char",
                "talent_key": "normal_attack",
                "entry_key": "hit_1",
                "label": "Normal Attack Hit 1",
                "scaling": {
                    "schema_version": 1,
                    "mode": "constant",
                    "components": [{"kind": "plain_ratio", "values": [1.0]}],
                },
                "tags": ["damage"],
            }
        ],
        "effect_payloads": [
            {
                "effect_key": "weapon:fixture_sword:passive",
                "owner_type": "weapon",
                "owner_key": "weapon:fixture_sword",
                "effect_kind": "passive",
                "handler_key": "generic.static_modifiers",
                "params": {"schema_version": 1, "params": {"stat": "atk_percent", "value": 0.2}},
            }
        ],
    }


def asset_manifest_handler_sync_payload() -> dict:
    """handler 绑定同步用的 manifest fixture（角色/武器/圣遗物/效果）。"""

    return {
        "schema_version": 1,
        "kind": "asset_manifest",
        "meta": {
            "schema_version": "2",
            "data_version": "sync-fixture-1",
            "source_name": "pytest-manifest",
        },
        "characters": [
            {
                "asset_key": "character:test",
                "source_id": "test",
                "name": "Test",
                "element": "anemo",
                "weapon_type": "sword",
                "rarity": 4,
                "burst_energy_cost": 40.0,
            }
        ],
        "weapons": [
            {
                "asset_key": "weapon:test",
                "source_id": "test",
                "name": "Test",
                "weapon_type": "sword",
                "rarity": 4,
            }
        ],
        "artifact_sets": [
            {
                "asset_key": "artifact_set:test",
                "source_id": "test",
                "name": "Test",
            }
        ],
        "artifact_set_bonuses": [
            {
                "artifact_set_key": "artifact_set:test",
                "piece_count": 2,
                "handler_key": "artifact.unimplemented_set_bonus",
                "params": {"schema_version": 1},
            }
        ],
        "effect_payloads": [
            {
                "effect_key": "character:test:passive:1",
                "owner_type": "character",
                "owner_key": "character:test",
                "effect_kind": "passive",
                "unlock_key": "passive:1",
                "handler_key": "character.unimplemented_passive",
                "params": {"schema_version": 1},
            }
        ],
    }
