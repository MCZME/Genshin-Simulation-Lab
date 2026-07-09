from __future__ import annotations

import json

from genshin_sim.infrastructure.assets_project_amber import (
    build_asset_manifest_from_project_amber_cache,
)
from genshin_sim.infrastructure.assets_sqlite import (
    SQLiteAssetRepository,
    build_asset_database_from_manifest,
    load_asset_manifest,
)


def test_build_asset_manifest_from_project_amber_cache_writes_index_and_level_stats(tmp_path):
    cache_dir = tmp_path / "cache"
    manifest_path = tmp_path / "manifest.json"
    db_path = tmp_path / "assets.db"
    _write_project_amber_cache(cache_dir, include_details=True)

    summary = build_asset_manifest_from_project_amber_cache(cache_dir, manifest_path)

    assert summary.character_count == 1
    assert summary.character_level_stat_count == 98
    assert summary.weapon_count == 1
    assert summary.weapon_level_stat_count == 96

    manifest = load_asset_manifest(manifest_path)
    assert manifest.meta["source_name"] == "project-amber-yatta"
    assert manifest.meta["source_version"] == "default"
    assert manifest.characters[0].asset_key == "character:10000002"
    assert manifest.characters[0].element == "cryo"
    assert manifest.weapons[0].weapon_type == "sword"

    build_asset_database_from_manifest(db_path, manifest_path)
    repository = SQLiteAssetRepository(db_path)

    character_level_20_pre = repository.get_character_level_stats(
        "character:10000002",
        20,
        ascended=False,
    )
    character_level_20_post = repository.get_character_level_stats("character:10000002", 20)
    character_level_95 = repository.get_character_level_stats("character:10000002", 95)
    weapon_level_20_pre = repository.get_weapon_level_stats(
        "weapon:11512",
        20,
        ascended=False,
    )
    weapon_level_20_post = repository.get_weapon_level_stats("weapon:11512", 20)

    assert character_level_20_pre.ascension_phase == 0
    assert character_level_20_pre.base_hp == 200.0
    assert character_level_20_pre.ascension_value == 0.0
    assert character_level_20_post.ascension_phase == 1
    assert character_level_20_post.base_hp == 300.0
    assert character_level_20_post.ascension_stat == "crit_damage"
    assert character_level_20_post.ascension_value == 0.096
    assert character_level_95.ascension_phase == 6
    assert character_level_95.base_atk == 155.0
    assert weapon_level_20_pre.ascension_phase == 0
    assert weapon_level_20_pre.base_atk == 40.0
    assert weapon_level_20_post.ascension_phase == 1
    assert weapon_level_20_post.base_atk == 60.0
    assert weapon_level_20_post.secondary_stat == "crit_damage"
    assert weapon_level_20_post.secondary_value == 2.0


def test_build_asset_manifest_uses_weapon_unlock_max_level(tmp_path):
    cache_dir = tmp_path / "cache"
    manifest_path = tmp_path / "manifest.json"
    _write_project_amber_cache(cache_dir, include_details=True)
    weapon_index_path = cache_dir / "weapon" / "index.json"
    weapon_index = json.loads(weapon_index_path.read_text(encoding="utf-8"))
    weapon_index["data"]["items"]["11201"] = {
        "id": 11201,
        "rank": 2,
        "name": "银剑",
        "type": "WEAPON_SWORD_ONE_HAND",
    }
    _write_json(weapon_index_path, weapon_index)
    _write_json(
        cache_dir / "weapon" / "11201.json",
        {
            "response": 200,
            "data": {
                "id": 11201,
                "rank": 2,
                "name": "银剑",
                "type": "WEAPON_SWORD_ONE_HAND",
                "upgrade": {
                    "prop": [
                        {
                            "propType": "FIGHT_PROP_BASE_ATTACK",
                            "initValue": 1.5,
                            "type": "w_atk",
                        }
                    ],
                    "promote": _low_rarity_weapon_promotes(),
                },
            },
        },
    )

    summary = build_asset_manifest_from_project_amber_cache(cache_dir, manifest_path)
    manifest = load_asset_manifest(manifest_path)

    low_rarity_rows = [
        row for row in manifest.weapon_level_stats if row.weapon_key == "weapon:11201"
    ]
    assert summary.weapon_count == 2
    assert summary.weapon_level_stat_count == 170
    assert len(low_rarity_rows) == 74
    assert {row.level for row in low_rarity_rows} == set(range(1, 71))
    assert [row.ascension_phase for row in low_rarity_rows if row.level == 70] == [4]


def test_build_asset_manifest_skips_level_stats_without_detail_files(tmp_path):
    cache_dir = tmp_path / "cache"
    manifest_path = tmp_path / "manifest.json"
    _write_project_amber_cache(cache_dir, include_details=False)

    summary = build_asset_manifest_from_project_amber_cache(cache_dir, manifest_path)
    manifest = load_asset_manifest(manifest_path)

    assert summary.character_count == 1
    assert summary.character_level_stat_count == 0
    assert summary.weapon_count == 1
    assert summary.weapon_level_stat_count == 0
    assert manifest.characters[0].name == "神里绫华"
    assert manifest.weapons[0].name == "静水流涌之辉"


def _write_project_amber_cache(cache_dir, *, include_details: bool) -> None:
    _write_json(
        cache_dir / "fetch_manifest.json",
        {
            "schema_version": 1,
            "kind": "project_amber_source_cache",
            "source_name": "project-amber-yatta",
            "source_version": "default",
            "language": "chs",
            "fetched_at": "2026-07-09T00:00:00+00:00",
            "content_hash": "fixturehash",
            "counts": {"characters": 1, "weapons": 1},
            "files": [],
        },
    )
    _write_json(
        cache_dir / "avatar" / "index.json",
        {
            "response": 200,
            "data": {
                "items": {
                    "10000002": {
                        "id": 10000002,
                        "rank": 5,
                        "name": "神里绫华",
                        "element": "Ice",
                        "weaponType": "WEAPON_SWORD_ONE_HAND",
                    },
                    "10000117": {
                        "id": 10000117,
                        "rank": 5,
                        "name": "奇偶·男性",
                        "element": None,
                        "weaponType": "WEAPON_SWORD_ONE_HAND",
                    }
                }
            },
        },
    )
    _write_json(
        cache_dir / "weapon" / "index.json",
        {
            "response": 200,
            "data": {
                "items": {
                    "11512": {
                        "id": 11512,
                        "rank": 5,
                        "name": "静水流涌之辉",
                        "type": "WEAPON_SWORD_ONE_HAND",
                    },
                    "310001": {
                        "id": 310001,
                        "rank": 4,
                        "name": "蛇噬",
                        "type": "WEAPON_SWORD_ONE_HAND",
                        "isWeaponSkin": True,
                    }
                }
            },
        },
    )
    _write_json(cache_dir / "static" / "avatarCurve.json", _curve_payload("hp", "atk", "def"))
    _write_json(cache_dir / "static" / "weaponCurve.json", _curve_payload("w_atk", "w_crit"))

    if not include_details:
        return

    _write_json(
        cache_dir / "avatar" / "10000002.json",
        {
            "response": 200,
            "data": {
                "id": 10000002,
                "rank": 5,
                "name": "神里绫华",
                "element": "Ice",
                "weaponType": "WEAPON_SWORD_ONE_HAND",
                "specialProp": "FIGHT_PROP_CRITICAL_HURT",
                "upgrade": {
                    "prop": [
                        {
                            "propType": "FIGHT_PROP_BASE_HP",
                            "initValue": 10.0,
                            "type": "hp",
                        },
                        {
                            "propType": "FIGHT_PROP_BASE_ATTACK",
                            "initValue": 1.0,
                            "type": "atk",
                        },
                        {
                            "propType": "FIGHT_PROP_BASE_DEFENSE",
                            "initValue": 2.0,
                            "type": "def",
                        },
                    ],
                    "promote": _character_promotes(),
                },
            },
        },
    )
    _write_json(
        cache_dir / "weapon" / "11512.json",
        {
            "response": 200,
            "data": {
                "id": 11512,
                "rank": 5,
                "name": "静水流涌之辉",
                "type": "WEAPON_SWORD_ONE_HAND",
                "upgrade": {
                    "prop": [
                        {
                            "propType": "FIGHT_PROP_BASE_ATTACK",
                            "initValue": 2.0,
                            "type": "w_atk",
                        },
                        {
                            "propType": "FIGHT_PROP_CRITICAL_HURT",
                            "initValue": 0.1,
                            "type": "w_crit",
                        },
                    ],
                    "promote": _weapon_promotes(),
                },
            },
        },
    )


def _curve_payload(*curve_names: str) -> dict[str, object]:
    return {
        "response": 200,
        "data": {
            str(level): {"curveInfos": {curve_name: float(level) for curve_name in curve_names}}
            for level in (*range(1, 91), 95, 100)
        },
    }


def _character_promotes() -> list[dict[str, object]]:
    return [
        {"unlockMaxLevel": 20, "addProps": {}},
        {
            "unlockMaxLevel": 40,
            "addProps": {
                "FIGHT_PROP_BASE_HP": 100.0,
                "FIGHT_PROP_BASE_ATTACK": 10.0,
                "FIGHT_PROP_BASE_DEFENSE": 20.0,
                "FIGHT_PROP_CRITICAL_HURT": 0.096,
            }
        },
        {"unlockMaxLevel": 50, "addProps": {"FIGHT_PROP_BASE_HP": 200.0}},
        {"unlockMaxLevel": 60, "addProps": {"FIGHT_PROP_BASE_HP": 300.0}},
        {"unlockMaxLevel": 70, "addProps": {"FIGHT_PROP_BASE_HP": 400.0}},
        {"unlockMaxLevel": 80, "addProps": {"FIGHT_PROP_BASE_HP": 500.0}},
        {
            "unlockMaxLevel": 90,
            "addProps": {
                "FIGHT_PROP_BASE_HP": 600.0,
                "FIGHT_PROP_BASE_ATTACK": 60.0,
                "FIGHT_PROP_BASE_DEFENSE": 120.0,
                "FIGHT_PROP_CRITICAL_HURT": 0.384,
            }
        },
    ]


def _weapon_promotes() -> list[dict[str, object]]:
    return [
        {"unlockMaxLevel": 20, "addProps": {}},
        {"unlockMaxLevel": 40, "addProps": {"FIGHT_PROP_BASE_ATTACK": 20.0}},
        {"unlockMaxLevel": 50, "addProps": {"FIGHT_PROP_BASE_ATTACK": 40.0}},
        {"unlockMaxLevel": 60, "addProps": {"FIGHT_PROP_BASE_ATTACK": 60.0}},
        {"unlockMaxLevel": 70, "addProps": {"FIGHT_PROP_BASE_ATTACK": 80.0}},
        {"unlockMaxLevel": 80, "addProps": {"FIGHT_PROP_BASE_ATTACK": 100.0}},
        {"unlockMaxLevel": 90, "addProps": {"FIGHT_PROP_BASE_ATTACK": 120.0}},
    ]


def _low_rarity_weapon_promotes() -> list[dict[str, object]]:
    return [
        {"unlockMaxLevel": 20, "addProps": {}},
        {"unlockMaxLevel": 40, "addProps": {"FIGHT_PROP_BASE_ATTACK": 20.0}},
        {"unlockMaxLevel": 50, "addProps": {"FIGHT_PROP_BASE_ATTACK": 40.0}},
        {"unlockMaxLevel": 60, "addProps": {"FIGHT_PROP_BASE_ATTACK": 60.0}},
        {"unlockMaxLevel": 70, "addProps": {"FIGHT_PROP_BASE_ATTACK": 80.0}},
    ]


def _write_json(path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
