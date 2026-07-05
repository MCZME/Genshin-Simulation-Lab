from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

RESULTS_SCHEMA_VERSION = "1"

_SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS result_db_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS simulation_runs (
    session_id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    config_schema_version INTEGER NOT NULL,
    config_kind TEXT NOT NULL,
    name TEXT NOT NULL,
    config_meta_json TEXT NOT NULL,
    config_snapshot_json TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    stop_reason TEXT NOT NULL,
    end_frame INTEGER NOT NULL,
    frames_run INTEGER NOT NULL,
    event_count INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS simulation_events (
    session_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    frame INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    source_type TEXT NULL,
    data_json TEXT NOT NULL,
    PRIMARY KEY (session_id, ordinal),
    FOREIGN KEY (session_id) REFERENCES simulation_runs(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_simulation_runs_created_at
    ON simulation_runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_simulation_events_frame
    ON simulation_events(session_id, frame, ordinal);
"""


def init_result_database(
    db_path: str | Path,
    *,
    meta: Mapping[str, str] | None = None,
) -> Path:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    rows = {
        "schema_version": RESULTS_SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    if meta is not None:
        rows.update({str(key): str(value) for key, value in meta.items()})

    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(_SCHEMA_SQL)
        connection.executemany(
            """
            INSERT INTO result_db_meta(key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            sorted(rows.items()),
        )
        connection.commit()
    return path
