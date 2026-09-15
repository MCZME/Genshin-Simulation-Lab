# 单一关注点：已有 manifest 作为基线的 handler 覆盖继承与差异计算。
from __future__ import annotations

from genshin_sim.assets import (
    ArtifactSetAsset,
    ArtifactSetBonus,
    CharacterAsset,
    CharacterLevelStats,
    EffectPayload,
    WeaponAsset,
    WeaponLevelStats,
)
from genshin_sim.infrastructure.assets_sqlite import (
    AssetManifest,
    apply_manifest_baseline,
    dump_asset_manifest,
)

_WEAPON_KEY = "weapon:11512"
_ARTIFACT_SET_KEY = "artifact_set:15032"
_WEAPON_BONUS_HANDLER_KEY = "artifact.unimplemented_set_bonus"
_CONSTELLATION_PLACEHOLDER = "character.unimplemented_constellation"


def _rows(
    *,
    character_id: str = "10000002",
    character_handler: str | None = None,
    weapon_handler: str | None = None,
    artifact_set_handler: str | None = None,
    effect_handler: str = _CONSTELLATION_PLACEHOLDER,
    bonus_handler: str = _WEAPON_BONUS_HANDLER_KEY,
    base_hp: float = 1000.0,
    include_weapon: bool = True,
    include_effect: bool = True,
) -> AssetManifest:
    character_key = f"character:{character_id}"
    return AssetManifest(
        meta={"schema_version": "2", "data_version": "test:1"},
        characters=(
            CharacterAsset(
                asset_key=character_key,
                source_id=character_id,
                name="测试角色",
                element="cryo",
                weapon_type="sword",
                rarity=5,
                burst_energy_cost=80.0,
                handler_key=character_handler,
            ),
        ),
        character_level_stats=(
            CharacterLevelStats(
                character_key=character_key,
                level=90,
                ascension_phase=6,
                base_hp=base_hp,
                base_atk=100.0,
                base_def=50.0,
            ),
        ),
        weapons=(
            (
                WeaponAsset(
                    asset_key=_WEAPON_KEY,
                    source_id="11512",
                    name="测试武器",
                    weapon_type="sword",
                    rarity=5,
                    handler_key=weapon_handler,
                ),
            )
            if include_weapon
            else ()
        ),
        weapon_level_stats=(
            (
                WeaponLevelStats(
                    weapon_key=_WEAPON_KEY,
                    level=90,
                    ascension_phase=6,
                    base_atk=500.0,
                ),
            )
            if include_weapon
            else ()
        ),
        artifact_sets=(
            ArtifactSetAsset(
                asset_key=_ARTIFACT_SET_KEY,
                source_id="15032",
                name="测试套装",
                handler_key=artifact_set_handler,
            ),
        ),
        artifact_set_bonuses=(
            ArtifactSetBonus(
                artifact_set_key=_ARTIFACT_SET_KEY,
                piece_count=2,
                handler_key=bonus_handler,
                params={"schema_version": 1},
            ),
        ),
        talent_scalings=(),
        effect_payloads=(
            (
                EffectPayload(
                    effect_key=f"{character_key}:constellation:c1",
                    owner_type="character",
                    owner_key=character_key,
                    effect_kind="constellation",
                    handler_key=effect_handler,
                    params={"schema_version": 1},
                    unlock_key="c1",
                ),
            )
            if include_effect
            else ()
        ),
    )


def _write_baseline(tmp_path, manifest: AssetManifest):
    baseline_path = tmp_path / "manifest.json"
    dump_asset_manifest(manifest, baseline_path)
    return baseline_path


def test_apply_manifest_baseline_without_baseline_keeps_rows(tmp_path):
    rows = _rows()

    merged, diff = apply_manifest_baseline(tmp_path / "missing.json", rows)

    assert merged == rows
    assert diff.baseline_available is False
    assert diff.baseline_error is None
    assert diff.carried_bindings == ()
    assert diff.has_asset_changes is False


def test_apply_manifest_baseline_ignores_unreadable_baseline(tmp_path):
    baseline_path = tmp_path / "manifest.json"
    baseline_path.write_text("{ 不是合法 JSON", encoding="utf-8")
    rows = _rows()

    merged, diff = apply_manifest_baseline(baseline_path, rows)

    assert merged == rows
    assert diff.baseline_available is False
    assert diff.baseline_error is not None
    assert diff.carried_bindings == ()


def test_apply_manifest_baseline_carries_handler_overlay(tmp_path):
    baseline_path = _write_baseline(
        tmp_path,
        _rows(
            character_handler="character.test",
            weapon_handler="weapon.test",
            artifact_set_handler="artifact.test_set",
            effect_handler="character.test.constellation.c1",
            bonus_handler="artifact.test_bonus",
        ),
    )

    merged, diff = apply_manifest_baseline(baseline_path, _rows())

    assert diff.baseline_available is True
    assert merged.characters[0].handler_key == "character.test"
    assert merged.weapons[0].handler_key == "weapon.test"
    assert merged.artifact_sets[0].handler_key == "artifact.test_set"
    assert merged.effect_payloads[0].handler_key == "character.test.constellation.c1"
    assert merged.artifact_set_bonuses[0].handler_key == "artifact.test_bonus"
    assert len(diff.carried_bindings) == 5
    assert diff.binding_conflicts == ()
    assert diff.has_asset_changes is False


def test_apply_manifest_baseline_keeps_new_build_value_on_conflict(tmp_path):
    baseline_path = _write_baseline(tmp_path, _rows(weapon_handler="weapon.old"))

    merged, diff = apply_manifest_baseline(baseline_path, _rows(weapon_handler="weapon.new"))

    assert merged.weapons[0].handler_key == "weapon.new"
    assert diff.carried_bindings == ()
    assert len(diff.binding_conflicts) == 1
    assert "weapon.old" in diff.binding_conflicts[0]


def test_apply_manifest_baseline_reports_added_removed_and_changed(tmp_path):
    baseline_path = _write_baseline(tmp_path, _rows())

    merged, diff = apply_manifest_baseline(
        baseline_path,
        _rows(character_id="10000003", base_hp=1200.0),
    )

    assert merged.characters[0].asset_key == "character:10000003"
    assert diff.characters.added == ("character:10000003",)
    assert diff.characters.removed == ("character:10000002",)
    assert diff.characters.changed == ()
    assert diff.has_asset_changes is True


def test_apply_manifest_baseline_reports_changed_asset_rows(tmp_path):
    baseline_path = _write_baseline(tmp_path, _rows(base_hp=1000.0))

    _merged, diff = apply_manifest_baseline(baseline_path, _rows(base_hp=1200.0))

    assert diff.characters.added == ()
    assert diff.characters.removed == ()
    assert diff.characters.changed == ("character:10000002",)


def test_apply_manifest_baseline_reports_dropped_bindings(tmp_path):
    baseline_path = _write_baseline(
        tmp_path,
        _rows(
            character_handler="character.test",
            weapon_handler="weapon.test",
            effect_handler="character.test.constellation.c1",
        ),
    )

    merged, diff = apply_manifest_baseline(
        baseline_path,
        _rows(character_id="10000003", include_weapon=False, include_effect=False),
    )

    assert merged == _rows(character_id="10000003", include_weapon=False, include_effect=False)
    assert diff.carried_bindings == ()
    dropped = "\n".join(diff.dropped_bindings)
    assert "character character:10000002 -> character.test" in dropped
    assert "weapon weapon:11512 -> weapon.test" in dropped
    assert "effect character:10000002:constellation:c1" in dropped


def test_apply_manifest_baseline_carries_overlay_updated_at(tmp_path):
    baseline = _rows(character_handler="character.test")
    baseline = AssetManifest(
        meta={**baseline.meta, "handler_overlay_updated_at": "2026-09-01T00:00:00+00:00"},
        characters=baseline.characters,
        character_level_stats=baseline.character_level_stats,
        weapons=baseline.weapons,
        weapon_level_stats=baseline.weapon_level_stats,
        artifact_sets=baseline.artifact_sets,
        artifact_set_bonuses=baseline.artifact_set_bonuses,
        talent_scalings=baseline.talent_scalings,
        effect_payloads=baseline.effect_payloads,
    )
    baseline_path = _write_baseline(tmp_path, baseline)

    _merged, diff = apply_manifest_baseline(baseline_path, _rows())

    assert diff.baseline_handler_overlay_updated_at == "2026-09-01T00:00:00+00:00"
