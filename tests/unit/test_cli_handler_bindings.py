from __future__ import annotations

from pathlib import Path

from genshin_sim.assets import (
    CharacterAsset,
    EffectPayload,
    WeaponAsset,
)
from genshin_sim.cli.main import main
from genshin_sim.infrastructure.assets_sqlite import SQLiteAssetDataWriter


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
