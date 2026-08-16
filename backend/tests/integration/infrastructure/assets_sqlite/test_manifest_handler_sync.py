from __future__ import annotations

import json
from pathlib import Path

import pytest

from genshin_sim.assets import AssetValidationError, HandlerBinding
from genshin_sim.infrastructure.assets_sqlite import (
    HANDLER_OVERLAY_UPDATED_AT,
    SQLiteAssetRepository,
    apply_handler_binding_to_manifest,
    build_asset_database_from_manifest,
    load_asset_manifest,
    sync_asset_manifest_handler_bindings,
    validate_handler_binding_in_manifest,
)


def test_apply_handler_binding_to_manifest_updates_character(tmp_path):
    manifest_path = _write_manifest(tmp_path)

    apply_handler_binding_to_manifest(
        manifest_path,
        HandlerBinding(
            kind="character",
            key="character:test",
            handler_key="character.test.real",
        ),
    )

    manifest = load_asset_manifest(manifest_path)
    assert manifest.characters[0].handler_key == "character.test.real"
    assert manifest.weapons[0].handler_key is None
    assert HANDLER_OVERLAY_UPDATED_AT in manifest.meta


def test_apply_handler_binding_to_manifest_supports_effect_and_bonus(tmp_path):
    manifest_path = _write_manifest(tmp_path)

    apply_handler_binding_to_manifest(
        manifest_path,
        HandlerBinding(
            kind="artifact-bonus",
            key="artifact_set:test",
            handler_key="artifact.test.real",
            pieces=2,
        ),
    )
    apply_handler_binding_to_manifest(
        manifest_path,
        HandlerBinding(
            kind="effect",
            key="character:test:passive:1",
            handler_key="character.test.passive",
        ),
    )

    manifest = load_asset_manifest(manifest_path)
    assert manifest.artifact_set_bonuses[0].handler_key == "artifact.test.real"
    assert manifest.effect_payloads[0].handler_key == "character.test.passive"


def test_apply_handler_binding_to_manifest_resets_character_to_null(tmp_path):
    manifest_path = _write_manifest(tmp_path)
    apply_handler_binding_to_manifest(
        manifest_path,
        HandlerBinding(kind="character", key="character:test", handler_key="character.test.real"),
    )

    apply_handler_binding_to_manifest(
        manifest_path,
        HandlerBinding(kind="character", key="character:test", handler_key=None),
    )

    manifest = load_asset_manifest(manifest_path)
    assert manifest.characters[0].handler_key is None


def test_validate_handler_binding_in_manifest_raises_for_missing_target(tmp_path):
    manifest_path = _write_manifest(tmp_path)

    with pytest.raises(AssetValidationError, match="不存在"):
        validate_handler_binding_in_manifest(
            manifest_path,
            HandlerBinding(
                kind="effect",
                key="character:missing:passive:1",
                handler_key="character.test.passive",
            ),
        )


def test_sync_asset_manifest_handler_bindings_updates_batch(tmp_path):
    manifest_path = _write_manifest(tmp_path)
    bindings = (
        HandlerBinding(
            kind="character",
            key="character:test",
            handler_key="character.test.real",
        ),
        HandlerBinding(
            kind="weapon",
            key="weapon:test",
            handler_key="weapon.test.real",
        ),
        HandlerBinding(
            kind="artifact-set",
            key="artifact_set:test",
            handler_key="artifact.test.real",
        ),
        HandlerBinding(
            kind="artifact-bonus",
            key="artifact_set:test",
            handler_key="artifact.bonus.real",
            pieces=2,
        ),
        HandlerBinding(
            kind="effect",
            key="character:test:passive:1",
            handler_key="character.test.passive",
        ),
    )

    sync_asset_manifest_handler_bindings(manifest_path, bindings)

    manifest = load_asset_manifest(manifest_path)
    assert manifest.characters[0].handler_key == "character.test.real"
    assert manifest.weapons[0].handler_key == "weapon.test.real"
    assert manifest.artifact_sets[0].handler_key == "artifact.test.real"
    assert manifest.artifact_set_bonuses[0].handler_key == "artifact.bonus.real"
    assert manifest.effect_payloads[0].handler_key == "character.test.passive"


def test_manifest_handler_sync_preserves_binding_across_rebuild(tmp_path):
    manifest_path = _write_manifest(tmp_path)
    db_path = tmp_path / "first.db"
    rebuilt_path = tmp_path / "rebuilt.db"
    build_asset_database_from_manifest(db_path, manifest_path)
    repository = SQLiteAssetRepository(db_path)
    binding = repository.get_handler_binding("character", "character:test")

    updated = HandlerBinding(
        kind=binding.kind,
        key=binding.key,
        handler_key="character.test.real",
    )
    repository.set_handler_binding(updated.kind, updated.key, updated.handler_key)
    apply_handler_binding_to_manifest(manifest_path, updated)

    build_asset_database_from_manifest(rebuilt_path, manifest_path)

    assert (
        SQLiteAssetRepository(rebuilt_path).get_character("character:test").handler_key
        == "character.test.real"
    )


def _write_manifest(tmp_path: Path) -> Path:
    manifest_path = tmp_path / "assets.json"
    manifest_path.write_text(json.dumps(_manifest_payload()), encoding="utf-8")
    return manifest_path


def _manifest_payload() -> dict:
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
