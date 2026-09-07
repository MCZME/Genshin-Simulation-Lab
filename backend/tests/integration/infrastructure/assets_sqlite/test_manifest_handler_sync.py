from __future__ import annotations

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
from tests.helpers.asset_manifest import asset_manifest_handler_sync_payload, write_asset_manifest


def test_apply_handler_binding_to_manifest_updates_character(tmp_path):
    manifest_path = write_asset_manifest(tmp_path, asset_manifest_handler_sync_payload())

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
    manifest_path = write_asset_manifest(tmp_path, asset_manifest_handler_sync_payload())

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
    manifest_path = write_asset_manifest(tmp_path, asset_manifest_handler_sync_payload())
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
    manifest_path = write_asset_manifest(tmp_path, asset_manifest_handler_sync_payload())

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
    manifest_path = write_asset_manifest(tmp_path, asset_manifest_handler_sync_payload())
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
    manifest_path = write_asset_manifest(tmp_path, asset_manifest_handler_sync_payload())
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
