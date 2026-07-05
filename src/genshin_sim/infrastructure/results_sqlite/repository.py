from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any

from genshin_sim.application.execution import (
    CompletedSimulationRun,
    RecordedEvent,
    RunState,
    SimulationRunSummary,
)
from genshin_sim.application.services.models import RunDetail, RunListItem
from genshin_sim.infrastructure.results_sqlite.schema import init_result_database


class ResultNotFoundError(LookupError):
    """Raised when a persisted simulation session does not exist."""


class SQLiteResultWriter:
    """Persist completed simulation runs into SQLite."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        init_result_database(self.db_path)

    def save_run(self, run: CompletedSimulationRun) -> str:
        session_id = uuid.uuid4().hex
        summary = run.summary.to_dict()
        with closing(_connect(self.db_path)) as connection:
            connection.execute(
                """
                INSERT INTO simulation_runs(
                    session_id, state, config_schema_version, config_kind, name,
                    config_meta_json, config_snapshot_json, summary_json, stop_reason,
                    end_frame, frames_run, event_count, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    RunState.COMPLETED.value,
                    run.config_schema_version,
                    run.config_kind,
                    str(run.config_meta.get("name") or "Untitled Simulation"),
                    _dump_json(run.config_meta),
                    _dump_json(run.config_snapshot),
                    _dump_json(summary),
                    run.summary.stop_reason,
                    run.summary.end_frame,
                    run.summary.frames_run,
                    len(run.events),
                    run.created_at,
                ),
            )
            connection.executemany(
                """
                INSERT INTO simulation_events(
                    session_id, ordinal, frame, event_type, source_type, data_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        session_id,
                        ordinal,
                        event.frame,
                        event.event_type,
                        event.source_type,
                        _dump_json(event.data),
                    )
                    for ordinal, event in enumerate(run.events)
                ),
            )
            connection.commit()
        return session_id


class SQLiteResultRepository:
    """Read persisted simulation runs from SQLite."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def list_runs(self, limit: int = 50) -> tuple[RunListItem, ...]:
        if limit <= 0:
            return ()
        if not self.db_path.exists():
            return ()

        with closing(_connect(self.db_path)) as connection:
            rows = connection.execute(
                """
                SELECT session_id, name, stop_reason, end_frame, frames_run, created_at,
                       event_count
                FROM simulation_runs
                ORDER BY created_at DESC, session_id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return tuple(
            RunListItem(
                session_id=str(row["session_id"]),
                name=str(row["name"]),
                stop_reason=str(row["stop_reason"]),
                end_frame=int(row["end_frame"]),
                frames_run=int(row["frames_run"]),
                created_at=str(row["created_at"]),
                event_count=int(row["event_count"]),
            )
            for row in rows
        )

    def get_run(self, session_id: str) -> RunDetail:
        if not self.db_path.exists():
            raise ResultNotFoundError(f"simulation run not found: {session_id}")

        with closing(_connect(self.db_path)) as connection:
            run_row = connection.execute(
                """
                SELECT session_id, config_snapshot_json, summary_json, created_at
                FROM simulation_runs
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
            if run_row is None:
                raise ResultNotFoundError(f"simulation run not found: {session_id}")

            event_rows = connection.execute(
                """
                SELECT frame, event_type, source_type, data_json
                FROM simulation_events
                WHERE session_id = ?
                ORDER BY ordinal
                """,
                (session_id,),
            ).fetchall()

        summary_payload = _load_json_object(str(run_row["summary_json"]))
        return RunDetail(
            session_id=str(run_row["session_id"]),
            config_snapshot=_load_json_object(str(run_row["config_snapshot_json"])),
            summary=SimulationRunSummary(
                stop_reason=str(summary_payload["stop_reason"]),
                end_frame=int(summary_payload["end_frame"]),
                frames_run=int(summary_payload["frames_run"]),
            ),
            events=tuple(
                RecordedEvent(
                    frame=int(row["frame"]),
                    event_type=str(row["event_type"]),
                    source_type=None if row["source_type"] is None else str(row["source_type"]),
                    data=_load_json_object(str(row["data_json"])),
                )
                for row in event_rows
            ),
            created_at=str(run_row["created_at"]),
        )


def _connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _dump_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load_json_object(raw: str) -> dict[str, Any]:
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("expected JSON object")
    return payload
