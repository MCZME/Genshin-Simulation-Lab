from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Mapping
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from genshin_sim.assets import (
    ArtifactSetAsset,
    ArtifactSetBonus,
    CharacterAsset,
    CharacterLevelStats,
    EffectPayload,
    TalentScalingEntry,
    WeaponAsset,
    WeaponLevelStats,
)
from genshin_sim.infrastructure.assets_sqlite.schema import (
    ASSET_SCHEMA_VERSION,
    init_asset_database,
)


class SQLiteAssetDataWriter:
    """Small writer used by build scripts and tests to create asset databases."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def replace_all(
        self,
        *,
        meta: Mapping[str, str] | None = None,
        characters: Iterable[CharacterAsset] = (),
        character_level_stats: Iterable[CharacterLevelStats] = (),
        weapons: Iterable[WeaponAsset] = (),
        weapon_level_stats: Iterable[WeaponLevelStats] = (),
        artifact_sets: Iterable[ArtifactSetAsset] = (),
        artifact_set_bonuses: Iterable[ArtifactSetBonus] = (),
        talent_scalings: Iterable[TalentScalingEntry] = (),
        effect_payloads: Iterable[EffectPayload] = (),
    ) -> Path:
        init_asset_database(self.db_path, meta=meta)
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            _clear_tables(connection)
            _insert_meta(connection, meta)
            _insert_import_run(connection, meta)
            _insert_characters(connection, characters)
            _insert_character_stats(connection, character_level_stats)
            _insert_weapons(connection, weapons)
            _insert_weapon_stats(connection, weapon_level_stats)
            _insert_artifact_sets(connection, artifact_sets)
            _insert_artifact_bonuses(connection, artifact_set_bonuses)
            _insert_talent_scalings(connection, talent_scalings)
            _insert_effect_payloads(connection, effect_payloads)
            connection.commit()
        return self.db_path


def write_minimal_static_asset_database(db_path: str | Path) -> Path:
    """Create a tiny local asset database for smoke tests and CLI bootstrapping."""

    writer = SQLiteAssetDataWriter(db_path)
    return writer.replace_all(
        meta={
            "schema_version": ASSET_SCHEMA_VERSION,
            "data_version": "local-static-1",
            "importer_version": "sqlite-asset-writer-1",
            "source_name": "local-static",
            "source_version": "1",
            "content_hash": "local-static-1",
        },
        characters=(
            CharacterAsset(
                asset_key="character:test_character",
                source_id="test_character",
                name="Test Character",
                element="anemo",
                weapon_type="sword",
                rarity=5,
                handler_key="character.testing.runtime_probe",
            ),
        ),
        character_level_stats=(
            CharacterLevelStats(
                character_key="character:test_character",
                level=90,
                ascension_phase=6,
                base_hp=10000.0,
                base_atk=200.0,
                base_def=600.0,
            ),
        ),
        weapons=(
            WeaponAsset(
                asset_key="weapon:test_sword",
                source_id="test_sword",
                name="Test Sword",
                weapon_type="sword",
                rarity=4,
                handler_key="generic.test_weapon",
            ),
        ),
        weapon_level_stats=(
            WeaponLevelStats(
                weapon_key="weapon:test_sword",
                level=90,
                ascension_phase=6,
                base_atk=510.0,
                secondary_stat="atk_percent",
                secondary_value=0.413,
            ),
        ),
        artifact_sets=(
            ArtifactSetAsset(
                asset_key="artifact_set:test_set",
                source_id="test_set",
                name="Test Set",
                handler_key="generic.test_artifact_set",
            ),
        ),
        artifact_set_bonuses=(
            ArtifactSetBonus(
                artifact_set_key="artifact_set:test_set",
                piece_count=4,
                handler_key="generic.static_modifiers",
                params={"schema_version": 1},
            ),
        ),
        talent_scalings=(
            TalentScalingEntry(
                character_key="character:test_character",
                talent_key="normal_attack",
                entry_key="hit_1",
                label="Normal Attack Hit 1",
                scaling={
                    "schema_version": 1,
                    "mode": "constant",
                    "components": [{"kind": "plain_ratio", "values": [1.0]}],
                },
                tags=("damage",),
            ),
        ),
    )


def _clear_tables(connection: sqlite3.Connection) -> None:
    for table_name in (
        "effect_payloads",
        "talent_scaling_entries",
        "artifact_set_bonuses",
        "artifact_sets",
        "weapon_level_stats",
        "weapons",
        "character_level_stats",
        "characters",
        "asset_import_runs",
        "asset_db_meta",
    ):
        connection.execute(f"DELETE FROM {table_name}")


def _insert_meta(connection: sqlite3.Connection, meta: Mapping[str, str] | None) -> None:
    rows = {
        "schema_version": ASSET_SCHEMA_VERSION,
        "data_version": "empty",
        "importer_version": "manual",
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source_name": "manual",
        "source_version": "empty",
        "content_hash": "",
    }
    if meta is not None:
        rows.update({str(key): str(value) for key, value in meta.items()})
    rows["built_at"] = rows.get("built_at") or datetime.now(UTC).isoformat(timespec="seconds")
    connection.executemany(
        "INSERT INTO asset_db_meta(key, value) VALUES (?, ?)",
        sorted(rows.items()),
    )


def _insert_import_run(connection: sqlite3.Connection, meta: Mapping[str, str] | None) -> None:
    rows = {
        "schema_version": ASSET_SCHEMA_VERSION,
        "data_version": "empty",
        "importer_version": "manual",
        "source_name": "manual",
        "source_version": "empty",
        "imported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "note": None,
    }
    if meta is not None:
        rows.update({str(key): str(value) for key, value in meta.items()})
    connection.execute(
        """
        INSERT INTO asset_import_runs(
            source_name, source_version, schema_version, data_version,
            importer_version, imported_at, note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rows["source_name"],
            rows["source_version"],
            rows["schema_version"],
            rows["data_version"],
            rows["importer_version"],
            rows["imported_at"],
            rows["note"],
        ),
    )


def _insert_characters(
    connection: sqlite3.Connection,
    characters: Iterable[CharacterAsset],
) -> None:
    connection.executemany(
        """
        INSERT INTO characters(
            asset_key, source_id, name, element, weapon_type, rarity, handler_key
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                item.asset_key,
                item.source_id,
                item.name,
                item.element,
                item.weapon_type,
                item.rarity,
                item.handler_key,
            )
            for item in characters
        ),
    )


def _insert_character_stats(
    connection: sqlite3.Connection,
    stats: Iterable[CharacterLevelStats],
) -> None:
    connection.executemany(
        """
        INSERT INTO character_level_stats(
            character_key, level, ascension_phase, base_hp, base_atk, base_def,
            ascension_stat, ascension_value
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                item.character_key,
                item.level,
                item.ascension_phase,
                item.base_hp,
                item.base_atk,
                item.base_def,
                item.ascension_stat,
                item.ascension_value,
            )
            for item in stats
        ),
    )


def _insert_weapons(connection: sqlite3.Connection, weapons: Iterable[WeaponAsset]) -> None:
    connection.executemany(
        """
        INSERT INTO weapons(asset_key, source_id, name, weapon_type, rarity, handler_key)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            (
                item.asset_key,
                item.source_id,
                item.name,
                item.weapon_type,
                item.rarity,
                item.handler_key,
            )
            for item in weapons
        ),
    )


def _insert_weapon_stats(
    connection: sqlite3.Connection,
    stats: Iterable[WeaponLevelStats],
) -> None:
    connection.executemany(
        """
        INSERT INTO weapon_level_stats(
            weapon_key, level, ascension_phase, base_atk, secondary_stat, secondary_value
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            (
                item.weapon_key,
                item.level,
                item.ascension_phase,
                item.base_atk,
                item.secondary_stat,
                item.secondary_value,
            )
            for item in stats
        ),
    )


def _insert_artifact_sets(
    connection: sqlite3.Connection,
    artifact_sets: Iterable[ArtifactSetAsset],
) -> None:
    connection.executemany(
        """
        INSERT INTO artifact_sets(asset_key, source_id, name, handler_key)
        VALUES (?, ?, ?, ?)
        """,
        ((item.asset_key, item.source_id, item.name, item.handler_key) for item in artifact_sets),
    )


def _insert_artifact_bonuses(
    connection: sqlite3.Connection,
    bonuses: Iterable[ArtifactSetBonus],
) -> None:
    connection.executemany(
        """
        INSERT INTO artifact_set_bonuses(
            artifact_set_key, piece_count, handler_key, params_json
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            (
                item.artifact_set_key,
                item.piece_count,
                item.handler_key,
                _dump_json(item.params),
            )
            for item in bonuses
        ),
    )


def _insert_talent_scalings(
    connection: sqlite3.Connection,
    entries: Iterable[TalentScalingEntry],
) -> None:
    connection.executemany(
        """
        INSERT INTO talent_scaling_entries(
            character_key, talent_key, entry_key, label, scaling_json, tags_json
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            (
                item.character_key,
                item.talent_key,
                item.entry_key,
                item.label,
                _dump_json(item.scaling),
                _dump_json(list(item.tags)) if item.tags else None,
            )
            for item in entries
        ),
    )


def _insert_effect_payloads(
    connection: sqlite3.Connection,
    payloads: Iterable[EffectPayload],
) -> None:
    connection.executemany(
        """
        INSERT INTO effect_payloads(
            effect_key, owner_type, owner_key, effect_kind, unlock_key, handler_key, params_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                item.effect_key,
                item.owner_type,
                item.owner_key,
                item.effect_kind,
                item.unlock_key,
                item.handler_key,
                _dump_json(item.params),
            )
            for item in payloads
        ),
    )


def _dump_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
