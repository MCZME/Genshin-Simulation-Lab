from __future__ import annotations

import json

from genshin_sim.infrastructure.assets_sqlite import audit_asset_manifest


def test_asset_manifest_audit_accepts_complete_level_coverage(tmp_path):
    manifest_path = tmp_path / "assets.json"
    manifest_path.write_text(json.dumps(_manifest_payload()), encoding="utf-8")

    report = audit_asset_manifest(manifest_path)

    assert report.ok
    assert report.issue_count == 0
    assert report.character_count == 1
    assert report.character_level_stat_count == 98
    assert report.character_level_complete_count == 1
    assert report.weapon_count == 1
    assert report.weapon_level_stat_count == 96
    assert report.weapon_level_complete_count == 1


def test_asset_manifest_audit_accepts_low_rarity_weapon_level_70_coverage(tmp_path):
    manifest_path = tmp_path / "assets.json"
    payload = _manifest_payload()
    payload["weapons"][0]["rarity"] = 2
    payload["weapon_level_stats"] = _low_rarity_weapon_level_stats("weapon:audit_weapon")
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    report = audit_asset_manifest(manifest_path)

    assert report.ok
    assert report.weapon_level_stat_count == 74
    assert report.weapon_level_complete_count == 1


def test_asset_manifest_audit_reports_common_data_issues(tmp_path):
    manifest_path = tmp_path / "assets.json"
    payload = _manifest_payload()
    payload["characters"].append(dict(payload["characters"][0]))
    payload["character_level_stats"].pop()
    payload["character_level_stats"].append(dict(payload["character_level_stats"][0]))
    payload["weapons"][0]["weapon_type"] = "blade"
    payload["weapon_level_stats"].append(
        {
            "weapon_key": "weapon:missing",
            "level": 1,
            "ascension_phase": 0,
            "base_atk": 40.0,
        }
    )
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    report = audit_asset_manifest(manifest_path)

    assert not report.ok
    codes = {issue.code for issue in report.issues}
    assert "duplicate_character_asset_key" in codes
    assert "duplicate_character_level_stats" in codes
    assert "incomplete_character_level_stats" in codes
    assert "invalid_weapon_type" in codes
    assert "orphan_weapon_level_stats" in codes


def _manifest_payload():
    return {
        "schema_version": 1,
        "kind": "asset_manifest",
        "meta": {"data_version": "audit-fixture-1"},
        "characters": [
            {
                "asset_key": "character:audit_char",
                "source_id": "audit_char",
                "name": "Audit Character",
                "element": "pyro",
                "weapon_type": "polearm",
                "rarity": 5,
            }
        ],
        "character_level_stats": _character_level_stats("character:audit_char"),
        "weapons": [
            {
                "asset_key": "weapon:audit_weapon",
                "source_id": "audit_weapon",
                "name": "Audit Weapon",
                "weapon_type": "polearm",
                "rarity": 4,
            }
        ],
        "weapon_level_stats": _weapon_level_stats("weapon:audit_weapon"),
        "artifact_sets": [],
        "artifact_set_bonuses": [],
        "talent_scalings": [],
        "effect_payloads": [],
    }


def _character_level_stats(character_key: str) -> list[dict[str, object]]:
    return [
        {
            "character_key": character_key,
            "level": level,
            "ascension_phase": phase,
            "base_hp": 1000.0 + level,
            "base_atk": 20.0 + level,
            "base_def": 60.0 + level,
            "ascension_stat": "pyro_damage_bonus",
            "ascension_value": 0.0,
        }
        for level in (*range(1, 91), 95, 100)
        for phase in _phases_for_level(level)
    ]


def _weapon_level_stats(weapon_key: str) -> list[dict[str, object]]:
    return [
        {
            "weapon_key": weapon_key,
            "level": level,
            "ascension_phase": phase,
            "base_atk": 30.0 + level,
            "secondary_stat": "atk_percent",
            "secondary_value": 0.1,
        }
        for level in range(1, 91)
        for phase in _phases_for_level(level)
    ]


def _low_rarity_weapon_level_stats(weapon_key: str) -> list[dict[str, object]]:
    return [
        {
            "weapon_key": weapon_key,
            "level": level,
            "ascension_phase": phase,
            "base_atk": 30.0 + level,
        }
        for level in range(1, 71)
        for phase in _low_rarity_weapon_phases_for_level(level)
    ]


def _low_rarity_weapon_phases_for_level(level: int) -> tuple[int, ...]:
    if level < 20:
        return (0,)
    if level == 20:
        return (0, 1)
    if level == 40:
        return (1, 2)
    if level == 50:
        return (2, 3)
    if level == 60:
        return (3, 4)
    if level <= 40:
        return (1,)
    if level <= 50:
        return (2,)
    if level <= 60:
        return (3,)
    return (4,)


def _phases_for_level(level: int) -> tuple[int, ...]:
    if level < 20:
        return (0,)
    if level == 20:
        return (0, 1)
    if level == 40:
        return (1, 2)
    if level == 50:
        return (2, 3)
    if level == 60:
        return (3, 4)
    if level == 70:
        return (4, 5)
    if level == 80:
        return (5, 6)
    if level <= 40:
        return (1,)
    if level <= 50:
        return (2,)
    if level <= 60:
        return (3,)
    if level <= 70:
        return (4,)
    if level <= 80:
        return (5,)
    return (6,)
