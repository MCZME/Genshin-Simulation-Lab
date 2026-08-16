from __future__ import annotations

import json
from pathlib import Path

import pytest

from genshin_sim.assets import (
    CharacterAsset,
    EffectPayload,
    WeaponAsset,
)
from genshin_sim.cli.main import main
from genshin_sim.infrastructure.assets_sqlite import (
    SQLiteAssetDataWriter,
    SQLiteAssetRepository,
    load_asset_manifest,
)


@pytest.fixture(autouse=True)
def _project_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(
        'schema_version = 1\n\n[workspace]\ndata_dir = "data"\n',
        encoding="utf-8",
    )


def _build_db(tmp_path: Path) -> str:
    db_path = tmp_path / "assets.db"
    SQLiteAssetDataWriter(db_path).replace_all(
        characters=(
            CharacterAsset(
                asset_key="character:test",
                source_id="test",
                name="Test",
                element="anemo",
                weapon_type="sword",
                rarity=4,
                burst_energy_cost=40.0,
                handler_key=None,
            ),
        ),
        weapons=(
            WeaponAsset(
                asset_key="weapon:test",
                source_id="test",
                name="Test",
                weapon_type="sword",
                rarity=4,
                handler_key=None,
            ),
        ),
        effect_payloads=(
            EffectPayload(
                effect_key="character:test:passive:1",
                owner_type="character",
                owner_key="character:test",
                effect_kind="passive",
                unlock_key="passive:1",
                handler_key="character.unimplemented_passive",
                params={"schema_version": 1},
            ),
        ),
    )
    return str(db_path)


def test_cli_set_handler_and_show(tmp_path, capsys):
    db_path = _build_db(tmp_path)

    assert (
        main(
            [
                "assets",
                "set-handler",
                "--db",
                db_path,
                "--kind",
                "effect",
                "--key",
                "character:test:passive:1",
                "--handler-key",
                "generic.noop",
            ]
        )
        == 0
    )
    assert main(["assets", "show-handlers", "--db", db_path, "--kind", "effect"]) == 0

    captured = capsys.readouterr()
    assert "character:test:passive:1 -> generic.noop" in captured.out
    assert "character:test:passive:1\t\tgeneric.noop" in captured.out


def test_cli_reset_handler_restores_placeholder(tmp_path, capsys):
    db_path = _build_db(tmp_path)

    assert (
        main(
            [
                "assets",
                "reset-handler",
                "--db",
                db_path,
                "--kind",
                "effect",
                "--key",
                "character:test:passive:1",
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    assert "character:test:passive:1 -> character.unimplemented_passive" in captured.out


def test_cli_set_handler_rejects_unregistered_handler(tmp_path, capsys):
    db_path = _build_db(tmp_path)

    assert (
        main(
            [
                "assets",
                "set-handler",
                "--db",
                db_path,
                "--kind",
                "effect",
                "--key",
                "character:test:passive:1",
                "--handler-key",
                "character.not_registered",
            ]
        )
        == 1
    )

    captured = capsys.readouterr()
    assert "handler 未注册：character.not_registered" in captured.err


def test_cli_set_handler_rejects_missing_target(tmp_path, capsys):
    db_path = _build_db(tmp_path)

    assert (
        main(
            [
                "assets",
                "set-handler",
                "--db",
                db_path,
                "--kind",
                "effect",
                "--key",
                "character:missing:passive:1",
                "--handler-key",
                "generic.noop",
            ]
        )
        == 1
    )

    captured = capsys.readouterr()
    assert "effect payload not found" in captured.err


def test_cli_set_handler_with_manifest_updates_manifest(tmp_path, capsys):
    db_path = _build_db(tmp_path)
    manifest_path = tmp_path / "assets.json"
    manifest_path.write_text(json.dumps(_manifest_payload()), encoding="utf-8")

    assert (
        main(
            [
                "assets",
                "set-handler",
                "--db",
                str(db_path),
                "--manifest",
                str(manifest_path),
                "--kind",
                "effect",
                "--key",
                "character:test:passive:1",
                "--handler-key",
                "generic.noop",
            ]
        )
        == 0
    )

    manifest = load_asset_manifest(manifest_path)
    assert manifest.effect_payloads[0].handler_key == "generic.noop"
    captured = capsys.readouterr()
    assert "character:test:passive:1 -> generic.noop" in captured.out


def test_cli_reset_handler_with_manifest_restores_placeholder(tmp_path, capsys):
    db_path = _build_db(tmp_path)
    manifest_path = tmp_path / "assets.json"
    manifest_path.write_text(json.dumps(_manifest_payload()), encoding="utf-8")
    main(
        [
            "assets",
            "set-handler",
            "--db",
            str(db_path),
            "--manifest",
            str(manifest_path),
            "--kind",
            "effect",
            "--key",
            "character:test:passive:1",
            "--handler-key",
            "generic.noop",
        ]
    )

    assert (
        main(
            [
                "assets",
                "reset-handler",
                "--db",
                str(db_path),
                "--manifest",
                str(manifest_path),
                "--kind",
                "effect",
                "--key",
                "character:test:passive:1",
            ]
        )
        == 0
    )

    manifest = load_asset_manifest(manifest_path)
    assert manifest.effect_payloads[0].handler_key == "character.unimplemented_passive"
    captured = capsys.readouterr()
    assert "character:test:passive:1 -> character.unimplemented_passive" in captured.out


def test_cli_sync_handlers_updates_manifest(tmp_path, capsys):
    db_path = _build_db(tmp_path)
    manifest_path = tmp_path / "assets.json"
    manifest_path.write_text(json.dumps(_manifest_payload()), encoding="utf-8")

    SQLiteAssetRepository(db_path).set_handler_binding(
        "character",
        "character:test",
        "generic.noop",
    )

    assert (
        main(
            [
                "assets",
                "sync-handlers",
                "--db",
                str(db_path),
                "--manifest",
                str(manifest_path),
                "--kind",
                "character",
            ]
        )
        == 0
    )

    manifest = load_asset_manifest(manifest_path)
    assert manifest.characters[0].handler_key == "generic.noop"
    captured = capsys.readouterr()
    assert "synced 1 handler bindings" in captured.out


def test_cli_set_handler_with_manifest_missing_target_fails_before_db_update(tmp_path, capsys):
    db_path = _build_db(tmp_path)
    manifest_path = tmp_path / "assets.json"
    payload = _manifest_payload()
    payload["effect_payloads"] = []
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    assert (
        main(
            [
                "assets",
                "set-handler",
                "--db",
                str(db_path),
                "--manifest",
                str(manifest_path),
                "--kind",
                "effect",
                "--key",
                "character:test:passive:1",
                "--handler-key",
                "generic.noop",
            ]
        )
        == 1
    )

    captured = capsys.readouterr()
    assert "manifest 中不存在 effect handler 绑定目标" in captured.err


def _manifest_payload() -> dict:
    return {
        "schema_version": 1,
        "kind": "asset_manifest",
        "meta": {"schema_version": "2", "data_version": "cli-handler-sync"},
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
