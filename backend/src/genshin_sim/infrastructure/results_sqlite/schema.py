from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

RESULTS_SCHEMA_VERSION = "2"

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
    input_schema_version INTEGER NOT NULL,
    name TEXT NOT NULL,
    input_snapshot_json TEXT NOT NULL,
    initial_snapshot_json TEXT NULL,
    stop_reason TEXT NULL,
    end_frame INTEGER NULL,
    frames_run INTEGER NULL,
    event_count INTEGER NOT NULL DEFAULT 0,
    error_code TEXT NULL,
    error_message TEXT NULL,
    asset_version TEXT NULL,
    content_version TEXT NULL,
    seed TEXT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT NULL,
    finished_at TEXT NULL
);

CREATE TABLE IF NOT EXISTS simulation_events (
    session_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    frame INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    data_json TEXT NOT NULL,
    PRIMARY KEY (session_id, ordinal),
    FOREIGN KEY (session_id) REFERENCES simulation_runs(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_simulation_runs_created_at
    ON simulation_runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_simulation_events_frame
    ON simulation_events(session_id, frame, ordinal);
CREATE INDEX IF NOT EXISTS idx_simulation_events_type
    ON simulation_events(session_id, event_type);
"""


def init_result_database(
    db_path: str | Path,
    *,
    meta: Mapping[str, str] | None = None,
) -> Path:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _ensure_schema_version_compatible(path)

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


def _ensure_schema_version_compatible(path: Path) -> None:
    """开发期版本不兼容时明确报错，不静默覆盖旧库。"""

    if not path.exists() or path.stat().st_size == 0:
        return
    try:
        with closing(sqlite3.connect(path)) as connection:
            table = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'result_db_meta'"
            ).fetchone()
            if table is None:
                return
            row = connection.execute(
                "SELECT value FROM result_db_meta WHERE key = 'schema_version'"
            ).fetchone()
    except sqlite3.DatabaseError as exc:
        raise ValueError(
            f"结果库已存在但不是有效 SQLite 数据库：{path}，请删除或显式重建结果库"
        ) from exc
    if row is not None and row[0] != RESULTS_SCHEMA_VERSION:
        raise ValueError(
            "结果库 schema 版本不兼容："
            f"库内 {row[0]} != 当前 {RESULTS_SCHEMA_VERSION}；"
            "开发期请显式重建结果库，禁止静默覆盖"
        )
