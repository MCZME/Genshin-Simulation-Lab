# 超 500 行说明：单一关注点（Project Amber 转换器），暂不拆分。
from __future__ import annotations

import json

import pytest

from genshin_sim.assets import AssetValidationError
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
    assert summary.artifact_set_count == 2
    assert summary.artifact_set_bonus_count == 3
    assert summary.talent_scaling_count == 8
    assert summary.effect_payload_count == 11

    manifest = load_asset_manifest(manifest_path)
    assert manifest.meta["source_name"] == "project-amber-yatta"
    assert manifest.meta["source_version"] == "default"
    assert manifest.characters[0].asset_key == "character:10000002"
    assert manifest.characters[0].element == "cryo"
    assert manifest.characters[0].burst_energy_cost == 80.0
    assert manifest.weapons[0].weapon_type == "sword"
    assert {item.asset_key for item in manifest.artifact_sets} == {
        "artifact_set:15009",
        "artifact_set:15032",
    }

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
    normal_attack_scalings = repository.get_talent_scalings(
        "character:10000002",
        "normal_attack",
    )
    burst_scalings = repository.get_talent_scalings("character:10000002", "elemental_burst")
    character_effects = repository.get_effect_payloads("character:10000002")
    weapon_effect = repository.get_effect_payloads("weapon:11512")[0]
    artifact_two_piece = repository.get_artifact_set_bonuses("artifact_set:15032", 2)[0]
    artifact_four_piece = repository.get_artifact_set_bonuses("artifact_set:15032", 4)[0]
    artifact_one_piece = repository.get_artifact_set_bonuses("artifact_set:15009", 1)[0]

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
    assert len(normal_attack_scalings) == 3
    assert normal_attack_scalings[1].entry_key == "line_02_param_2_param_3"
    assert normal_attack_scalings[1].scaling["components"][0]["values"][0] == 0.2
    assert normal_attack_scalings[1].scaling["components"][1]["source_param"] == "param3"
    assert burst_scalings[1].scaling["components"][0]["kind"] == "plain_ratio"
    assert burst_scalings[1].scaling["components"][1]["kind"] == "plain_value"
    assert len(character_effects) == 10
    character_effect_by_key = {effect.effect_key: effect for effect in character_effects}
    alternate_sprint = character_effect_by_key["character:10000002:alternate_sprint:2"]
    passive_5 = character_effect_by_key["character:10000002:passive:5"]
    passive_6 = character_effect_by_key["character:10000002:passive:6"]
    passive_7 = character_effect_by_key["character:10000002:passive_exploration:7"]
    constellation_1 = character_effect_by_key["character:10000002:constellation:c1"]
    assert alternate_sprint.handler_key == "character.unimplemented_special_talent"
    assert alternate_sprint.unlock_key == "talent:2"
    assert alternate_sprint.effect_kind == "alternate_sprint"
    assert alternate_sprint.params["promote_entries"][0]["components"][0]["values"] == [10.0]
    assert alternate_sprint.params["promote_entries"][2]["components"][0]["values"] == [5.0]
    assert passive_5.handler_key == "character.unimplemented_passive"
    assert passive_5.unlock_key == "passive:5"
    assert passive_5.params["components"][0]["values"] == [6.0]
    assert passive_6.effect_kind == "passive"
    assert passive_6.params["components"][0]["values"] == [10.0]
    assert passive_6.params["components"][1]["values"] == [0.18]
    assert passive_7.effect_kind == "passive_exploration"
    assert passive_7.params["source_talent_key"] == "7"
    assert constellation_1.handler_key == "character.unimplemented_constellation"
    assert constellation_1.unlock_key == "c1"
    assert constellation_1.params["source_constellation_key"] == "0"
    assert constellation_1.params["components"][0]["values"] == [0.5]
    assert weapon_effect.effect_key == "weapon:11512:passive:111512"
    assert weapon_effect.handler_key == "weapon.unimplemented_passive"
    assert weapon_effect.params["refinement_min"] == 1
    assert weapon_effect.params["refinement_max"] == 5
    assert weapon_effect.params["components"][0]["values"] == [0.12, 0.15, 0.18, 0.21, 0.24]
    assert weapon_effect.params["components"][1]["values"] == [12.0, 10.5, 9.0, 7.5, 6.0]
    assert artifact_two_piece.handler_key == "artifact.unimplemented_set_bonus"
    assert artifact_two_piece.params["source_affix_id"] == "2150320"
    assert artifact_two_piece.params["components"][0]["values"] == [0.2]
    assert artifact_four_piece.params["piece_count"] == 4
    assert artifact_four_piece.params["components"][0]["values"] == [0.25]
    assert artifact_four_piece.params["components"][1]["values"] == [0.25]
    assert artifact_four_piece.params["components"][2]["values"] == [2.0]
    assert artifact_one_piece.piece_count == 1
    assert artifact_one_piece.params["components"][0]["values"] == [0.4]


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
    assert summary.artifact_set_count == 2
    assert summary.artifact_set_bonus_count == 3
    assert summary.talent_scaling_count == 8
    assert summary.effect_payload_count == 11
    assert len(low_rarity_rows) == 74
    assert {row.level for row in low_rarity_rows} == set(range(1, 71))
    assert [row.ascension_phase for row in low_rarity_rows if row.level == 70] == [4]


def test_build_asset_manifest_rejects_characters_without_burst_cost_source(tmp_path):
    cache_dir = tmp_path / "cache"
    manifest_path = tmp_path / "manifest.json"
    _write_project_amber_cache(cache_dir, include_details=False)

    with pytest.raises(AssetValidationError, match="cache 文件"):
        build_asset_manifest_from_project_amber_cache(cache_dir, manifest_path)


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
            "counts": {"characters": 1, "weapons": 1, "artifact_sets": 2},
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
                    },
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
                    },
                }
            },
        },
    )
    _write_json(
        cache_dir / "reliquary" / "index.json",
        {
            "response": 200,
            "data": {
                "items": {
                    "15032": {
                        "id": 15032,
                        "name": "黄金剧团",
                        "levelList": [4, 5],
                        "affixList": {
                            "2150320": "元素战技造成的伤害提升20%。",
                            "2150321": (
                                "元素战技造成的伤害提升25%；此外，处于队伍后台时，"
                                "元素战技造成的伤害还将进一步提升25%，该效果将在登场后2秒移除。"
                            ),
                        },
                    },
                    "15009": {
                        "id": 15009,
                        "name": "祭火之人",
                        "levelList": [3, 4],
                        "affixList": {
                            "2150090": "受到的火元素附着效果的持续时间减少40%。",
                        },
                    },
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
                "talent": _character_talents(),
                "constellation": _character_constellations(),
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
                "affix": {
                    "111512": {
                        "name": "测试被动",
                        "upgrade": {
                            "0": (
                                "造成的伤害提高<color=#99FFFFFF>12%</color>。"
                                "该效果每<color=#99FFFFFF>12</color>秒触发一次。"
                            ),
                            "1": (
                                "造成的伤害提高<color=#99FFFFFF>15%</color>。"
                                "该效果每<color=#99FFFFFF>10.5</color>秒触发一次。"
                            ),
                            "2": (
                                "造成的伤害提高<color=#99FFFFFF>18%</color>。"
                                "该效果每<color=#99FFFFFF>9</color>秒触发一次。"
                            ),
                            "3": (
                                "造成的伤害提高<color=#99FFFFFF>21%</color>。"
                                "该效果每<color=#99FFFFFF>7.5</color>秒触发一次。"
                            ),
                            "4": (
                                "造成的伤害提高<color=#99FFFFFF>24%</color>。"
                                "该效果每<color=#99FFFFFF>6</color>秒触发一次。"
                            ),
                        },
                    }
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
            },
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
            },
        },
    ]


def _character_talents() -> dict[str, object]:
    return {
        "0": {
            "skillId": 10001,
            "name": "神里流·倾",
            "type": 0,
            "promote": _talent_promote(
                [
                    "一段伤害|{param1:F1P}",
                    "重击伤害|{param2:F1P}+{param3:F1P}",
                    "低空/高空坠地冲击伤害|{param4:P}/{param5:P}",
                ],
                [
                    lambda level: 0.1 * level,
                    lambda level: 0.2 * level,
                    lambda level: 0.3 * level,
                    lambda level: 0.4 * level,
                    lambda level: 0.5 * level,
                ],
            ),
        },
        "1": {
            "skillId": 10002,
            "name": "神里流·冰华",
            "type": 0,
            "promote": _talent_promote(
                [
                    "技能伤害|{param1:P}",
                    "冷却时间|{param2:F1}秒",
                ],
                [
                    lambda level: 1.0 + level,
                    lambda _level: 10.0,
                ],
            ),
        },
        "2": {
            "skillId": 10013,
            "name": "神里流·霰步",
            "type": 0,
            "description": "<color=#FFD780FF>替代冲刺</color>，结束时获得冰元素附魔。",
            "promote": {
                "1": {
                    "level": 1,
                    "description": [
                        "启动体力消耗|{param1:F1}点",
                        "持续体力消耗|每秒{param2:F1}点",
                        "附魔持续时间|{param3:F1}秒",
                    ],
                    "params": [10.0, 15.0, 5.0],
                }
            },
        },
        "4": {
            "skillId": 10003,
            "name": "神里流·霜灭",
            "type": 1,
            "cost": 80,
            "promote": _talent_promote(
                [
                    "切割伤害|{param1:P}",
                    "领域发动治疗量|{param2:P}攻击力+{param3:I}",
                    "元素能量|{param4:I}",
                ],
                [
                    lambda level: 2.0 + level,
                    lambda level: 0.05 * level,
                    lambda level: 100.0 + level,
                    lambda _level: 80.0,
                ],
            ),
        },
        "5": {
            "skillId": 221,
            "name": "天罪国罪镇词",
            "type": 2,
            "description": (
                "施放<color=#FFD780FF>神里流·冰华</color>后的6秒内，"
                "普通攻击与重击造成的伤害提升30%。"
            ),
        },
        "6": {
            "skillId": 222,
            "name": "寒天宣命祝词",
            "type": 2,
            "description": "恢复10点体力；获得18%冰元素伤害加成，持续10秒。",
        },
        "7": {
            "skillId": 223,
            "name": "鉴查心得",
            "type": 2,
            "description": "合成武器突破素材时，有10%概率获得2倍产出。",
        },
        "8": {
            "skillId": 224,
            "name": "",
            "type": 2,
            "description": "",
        },
    }


def _character_constellations() -> dict[str, object]:
    return {
        str(index): {
            "id": index,
            "talentId": 210 + index,
            "name": f"测试命座{index + 1}",
            "description": f"造成伤害时有50%概率触发第{index + 1}层效果。",
        }
        for index in range(6)
    }


def _talent_promote(
    description: list[str],
    param_factories,
) -> dict[str, object]:
    return {
        str(level): {
            "level": level,
            "description": description,
            "params": [factory(level) for factory in param_factories],
        }
        for level in range(1, 16)
    }


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
