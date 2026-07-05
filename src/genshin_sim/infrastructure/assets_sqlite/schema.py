from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from genshin_sim.assets import AssetValidationError

ASSET_SCHEMA_VERSION = "1"

_REQUIRED_TABLES = {
    "asset_db_meta",
    "asset_import_runs",
    "characters",
    "character_level_stats",
    "weapons",
    "weapon_level_stats",
    "artifact_sets",
    "artifact_set_bonuses",
    "talent_scaling_entries",
    "effect_payloads",
}

_SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS asset_db_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS asset_import_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    source_version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    data_version TEXT NOT NULL,
    importer_version TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    note TEXT NULL
);

CREATE TABLE IF NOT EXISTS characters (
    asset_key TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    name TEXT NOT NULL,
    element TEXT NOT NULL,
    weapon_type TEXT NOT NULL,
    rarity INTEGER NOT NULL,
    handler_key TEXT NULL
);

CREATE TABLE IF NOT EXISTS character_level_stats (
    character_key TEXT NOT NULL,
    level INTEGER NOT NULL,
    ascension_phase INTEGER NOT NULL,
    base_hp REAL NOT NULL,
    base_atk REAL NOT NULL,
    base_def REAL NOT NULL,
    ascension_stat TEXT NULL,
    ascension_value REAL NULL,
    PRIMARY KEY (character_key, level, ascension_phase),
    FOREIGN KEY (character_key) REFERENCES characters(asset_key) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS weapons (
    asset_key TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    name TEXT NOT NULL,
    weapon_type TEXT NOT NULL,
    rarity INTEGER NOT NULL,
    handler_key TEXT NULL
);

CREATE TABLE IF NOT EXISTS weapon_level_stats (
    weapon_key TEXT NOT NULL,
    level INTEGER NOT NULL,
    ascension_phase INTEGER NOT NULL,
    base_atk REAL NOT NULL,
    secondary_stat TEXT NULL,
    secondary_value REAL NULL,
    PRIMARY KEY (weapon_key, level, ascension_phase),
    FOREIGN KEY (weapon_key) REFERENCES weapons(asset_key) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS artifact_sets (
    asset_key TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    name TEXT NOT NULL,
    handler_key TEXT NULL
);

CREATE TABLE IF NOT EXISTS artifact_set_bonuses (
    artifact_set_key TEXT NOT NULL,
    piece_count INTEGER NOT NULL,
    handler_key TEXT NOT NULL,
    params_json TEXT NOT NULL,
    PRIMARY KEY (artifact_set_key, piece_count, handler_key),
    FOREIGN KEY (artifact_set_key) REFERENCES artifact_sets(asset_key) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS talent_scaling_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_key TEXT NOT NULL,
    talent_key TEXT NOT NULL,
    entry_key TEXT NOT NULL,
    label TEXT NOT NULL,
    scaling_json TEXT NOT NULL,
    tags_json TEXT NULL,
    UNIQUE (character_key, talent_key, entry_key),
    FOREIGN KEY (character_key) REFERENCES characters(asset_key) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS effect_payloads (
    effect_key TEXT PRIMARY KEY,
    owner_type TEXT NOT NULL,
    owner_key TEXT NOT NULL,
    effect_kind TEXT NOT NULL,
    unlock_key TEXT NULL,
    handler_key TEXT NOT NULL,
    params_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_characters_weapon_type
    ON characters(weapon_type);
CREATE INDEX IF NOT EXISTS idx_weapons_weapon_type
    ON weapons(weapon_type);
CREATE INDEX IF NOT EXISTS idx_talent_scaling_character_talent
    ON talent_scaling_entries(character_key, talent_key);
CREATE INDEX IF NOT EXISTS idx_effect_payloads_owner
    ON effect_payloads(owner_key, effect_kind);
"""


def init_asset_database(
    db_path: str | Path,
    *,
    meta: Mapping[str, str] | None = None,
) -> Path:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    default_meta = {
        "schema_version": ASSET_SCHEMA_VERSION,
        "data_version": "empty",
        "importer_version": "manual",
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source_name": "manual",
        "source_version": "empty",
        "content_hash": "",
    }
    if meta is not None:
        default_meta.update({str(key): str(value) for key, value in meta.items()})

    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(_SCHEMA_SQL)
        connection.executemany(
            """
            INSERT INTO asset_db_meta(key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            sorted(default_meta.items()),
        )
        connection.commit()

    return path


def validate_asset_database(db_path: str | Path) -> None:
    path = Path(db_path)
    if not path.exists():
        raise AssetValidationError(f"asset database does not exist: {path}")

    try:
        with closing(sqlite3.connect(path)) as connection:
            connection.row_factory = sqlite3.Row
            _validate_required_tables(connection)
            _validate_schema_version(connection)
            _validate_foreign_keys(connection)
            _validate_json_payloads(connection)
    except sqlite3.Error as exc:
        raise AssetValidationError(f"invalid asset database: {path}") from exc


def _validate_required_tables(connection: sqlite3.Connection) -> None:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    tables = {str(row["name"]) for row in rows}
    missing = sorted(_REQUIRED_TABLES - tables)
    if missing:
        raise AssetValidationError(f"missing asset database tables: {', '.join(missing)}")


def _validate_schema_version(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        "SELECT value FROM asset_db_meta WHERE key = 'schema_version'"
    ).fetchone()
    if row is None:
        raise AssetValidationError("asset database missing schema_version")
    if str(row["value"]) != ASSET_SCHEMA_VERSION:
        raise AssetValidationError(f"unsupported asset schema_version: {row['value']!r}")


def _validate_foreign_keys(connection: sqlite3.Connection) -> None:
    rows = connection.execute("PRAGMA foreign_key_check").fetchall()
    if rows:
        raise AssetValidationError("asset database contains orphan foreign keys")


def _validate_json_payloads(connection: sqlite3.Connection) -> None:
    checks = (
        ("artifact_set_bonuses", "params_json"),
        ("talent_scaling_entries", "scaling_json"),
        ("effect_payloads", "params_json"),
    )
    for table_name, column_name in checks:
        for row in connection.execute(f"SELECT {column_name} FROM {table_name}"):
            _load_json_object(str(row[column_name]), f"{table_name}.{column_name}")

    for row in connection.execute(
        "SELECT tags_json FROM talent_scaling_entries WHERE tags_json IS NOT NULL"
    ):
        try:
            tags = json.loads(str(row["tags_json"]))
        except json.JSONDecodeError as exc:
            raise AssetValidationError(
                "talent_scaling_entries.tags_json must be valid JSON"
            ) from exc
        if not isinstance(tags, list):
            raise AssetValidationError("talent_scaling_entries.tags_json must be a JSON list")


def _load_json_object(raw: str, field_name: str) -> dict[str, object]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AssetValidationError(f"{field_name} must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise AssetValidationError(f"{field_name} must be a JSON object")
    return payload
