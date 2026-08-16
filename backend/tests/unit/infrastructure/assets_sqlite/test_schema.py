from __future__ import annotations

import sqlite3

import pytest

from genshin_sim.assets import AssetValidationError
from genshin_sim.infrastructure.assets_sqlite import (
    init_asset_database,
    validate_asset_database,
)

_LEGACY_SCHEMA_SQL = """
CREATE TABLE asset_db_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE asset_import_runs (id INTEGER PRIMARY KEY);
CREATE TABLE characters (
    asset_key TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    name TEXT NOT NULL,
    element TEXT NOT NULL,
    weapon_type TEXT NOT NULL,
    rarity INTEGER NOT NULL,
    handler_key TEXT NULL
);
CREATE TABLE character_level_stats (id INTEGER PRIMARY KEY);
CREATE TABLE weapons (id INTEGER PRIMARY KEY);
CREATE TABLE weapon_level_stats (id INTEGER PRIMARY KEY);
CREATE TABLE artifact_sets (id INTEGER PRIMARY KEY);
CREATE TABLE artifact_set_bonuses (id INTEGER PRIMARY KEY);
CREATE TABLE talent_scaling_entries (id INTEGER PRIMARY KEY);
CREATE TABLE effect_payloads (id INTEGER PRIMARY KEY);
"""


def _create_legacy_database(path, *, schema_version: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(_LEGACY_SCHEMA_SQL)
        connection.execute(
            "INSERT INTO asset_db_meta(key, value) VALUES ('schema_version', ?)",
            (schema_version,),
        )


def test_init_refuses_legacy_database_without_relabeling_its_schema(tmp_path):
    db_path = tmp_path / "legacy.db"
    _create_legacy_database(db_path, schema_version="1")

    with pytest.raises(AssetValidationError, match="characters.burst_energy_cost"):
        init_asset_database(db_path)

    with sqlite3.connect(db_path) as connection:
        schema_version = connection.execute(
            "SELECT value FROM asset_db_meta WHERE key = 'schema_version'"
        ).fetchone()[0]
    assert schema_version == "1"


def test_validate_rejects_v2_metadata_when_the_v2_column_is_absent(tmp_path):
    db_path = tmp_path / "mislabeled.db"
    _create_legacy_database(db_path, schema_version="2")

    with pytest.raises(AssetValidationError, match="characters.burst_energy_cost"):
        validate_asset_database(db_path)
