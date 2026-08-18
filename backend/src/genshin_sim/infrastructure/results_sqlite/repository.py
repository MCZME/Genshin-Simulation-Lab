from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from time import sleep
from typing import Any

from genshin_sim.application.execution import (
    CompletedSimulationRun,
    FailedSimulationRun,
    RecordedEvent,
    RunState,
    SimulationRunSummary,
)
from genshin_sim.application.models import RunDetail, RunListItem
from genshin_sim.infrastructure.errors import ResultWriteError, SqliteBusyError
from genshin_sim.infrastructure.results_sqlite.schema import init_result_database

DEFAULT_BUSY_TIMEOUT_SECONDS = 5.0
DEFAULT_WRITE_RETRIES = 3


class ResultNotFoundError(LookupError):
    """Raised when a persisted simulation session does not exist."""


class SQLiteResultWriter:
    """Persist completed simulation runs into SQLite."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        busy_timeout_seconds: float = DEFAULT_BUSY_TIMEOUT_SECONDS,
        write_retries: int = DEFAULT_WRITE_RETRIES,
    ) -> None:
        self.db_path = Path(db_path)
        self.busy_timeout_seconds = busy_timeout_seconds
        self.write_retries = write_retries
        init_result_database(self.db_path)

    def save_run(self, run: CompletedSimulationRun) -> str:
        return self._save(_write_completed_run, run)

    def save_failed_run(self, run: FailedSimulationRun) -> str:
        return self._save(_write_failed_run, run)

    def _save(
        self,
        write: Callable[[sqlite3.Connection, Any], None],
        run: Any,
    ) -> str:
        self._validate_write_settings()
        last_error: Exception | None = None
        for attempt in range(self.write_retries):
            try:
                with closing(_connect(self.db_path, self.busy_timeout_seconds)) as connection:
                    write(connection, run)
                    connection.commit()
                return run.session_id
            except sqlite3.OperationalError as exc:
                if _is_lock_contention(exc):
                    last_error = exc
                    if attempt < self.write_retries - 1:
                        sleep(0.05 * (attempt + 1))
                        continue
                    raise SqliteBusyError() from exc
                raise ResultWriteError(f"结果写入失败：{exc}") from exc
            except ValueError:
                # session_id 重复等业务性拒绝不包装为基础设施错误，
                # 保持写入方能够按结果库身份冲突直接处理。
                raise
            except Exception as exc:
                raise ResultWriteError(f"结果写入失败：{exc}") from exc
        raise ResultWriteError("结果写入重试次数已用尽") from last_error

    def _validate_write_settings(self) -> None:
        if self.busy_timeout_seconds < 0:
            raise ValueError("busy_timeout_seconds 不能为负数")
        if self.write_retries <= 0:
            raise ValueError("write_retries 必须是正整数")


def _write_completed_run(connection: sqlite3.Connection, run: CompletedSimulationRun) -> None:
    _require_missing_run(connection, run.session_id)
    connection.execute(
        """
        INSERT INTO simulation_runs(
            session_id, state, input_schema_version, name, input_snapshot_json,
            initial_snapshot_json, stop_reason, end_frame, frames_run, event_count,
            error_code, error_message, asset_version, content_version, seed,
            created_at, started_at, finished_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run.session_id,
            RunState.COMPLETED.value,
            run.input_schema_version,
            str(run.input_meta.get("name") or "Untitled Simulation"),
            _dump_json(run.input_snapshot),
            None if run.initial_snapshot is None else _dump_json(run.initial_snapshot),
            run.summary.stop_reason,
            run.summary.end_frame,
            run.summary.frames_run,
            len(run.events),
            None,
            None,
            run.asset_version,
            run.content_version,
            run.seed,
            run.created_at,
            run.started_at,
            run.finished_at,
        ),
    )
    connection.executemany(
        """
        INSERT INTO simulation_events(
            session_id, ordinal, frame, event_type, data_json
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            (
                run.session_id,
                ordinal,
                event.frame,
                event.event_type,
                _dump_json(event.data),
            )
            for ordinal, event in enumerate(run.events)
        ),
    )


def _write_failed_run(connection: sqlite3.Connection, run: FailedSimulationRun) -> None:
    _require_missing_run(connection, run.session_id)
    connection.execute(
        """
        INSERT INTO simulation_runs(
            session_id, state, input_schema_version, name, input_snapshot_json,
            initial_snapshot_json, stop_reason, end_frame, frames_run, event_count,
            error_code, error_message, asset_version, content_version, seed,
            created_at, started_at, finished_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run.session_id,
            run.state.value,
            run.input_schema_version,
            str(run.input_meta.get("name") or "Untitled Simulation"),
            _dump_json(run.input_snapshot),
            None,
            None,
            None,
            None,
            0,
            run.error_code,
            run.error_message,
            None,
            None,
            None,
            run.created_at,
            run.started_at,
            run.finished_at,
        ),
    )


class SQLiteResultRepository:
    """Read persisted simulation runs from SQLite."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def list_runs(
        self,
        limit: int = 50,
        offset: int = 0,
        state: str | None = None,
    ) -> tuple[RunListItem, ...]:
        if limit <= 0:
            return ()
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("offset 必须是非负整数")
        if not self.db_path.exists():
            return ()

        with closing(_connect(self.db_path)) as connection:
            sql = (
                "SELECT session_id, state, name, stop_reason, end_frame, frames_run, created_at,"
                " event_count FROM simulation_runs"
            )
            params: list[Any] = []
            if state is not None:
                sql += " WHERE state = ?"
                params.append(state)
            sql += " ORDER BY created_at DESC, session_id DESC LIMIT ? OFFSET ?"
            params.append(limit)
            params.append(offset)
            rows = connection.execute(sql, tuple(params)).fetchall()
        return tuple(
            RunListItem(
                session_id=str(row["session_id"]),
                state=str(row["state"]),
                name=str(row["name"]),
                stop_reason="" if row["stop_reason"] is None else str(row["stop_reason"]),
                end_frame=0 if row["end_frame"] is None else int(row["end_frame"]),
                frames_run=0 if row["frames_run"] is None else int(row["frames_run"]),
                created_at=str(row["created_at"]),
                event_count=int(row["event_count"]),
            )
            for row in rows
        )

    def count_events(
        self,
        session_id: str,
        *,
        frame_min: int | None = None,
        frame_max: int | None = None,
        event_type: str | None = None,
    ) -> int:
        if not self.db_path.exists():
            raise ResultNotFoundError(f"simulation run not found: {session_id}")

        conditions = ["session_id = ?"]
        params: list[Any] = [session_id]
        if frame_min is not None:
            conditions.append("frame >= ?")
            params.append(frame_min)
        if frame_max is not None:
            conditions.append("frame <= ?")
            params.append(frame_max)
        if event_type is not None:
            conditions.append("event_type = ?")
            params.append(event_type)

        with closing(_connect(self.db_path)) as connection:
            run_row = connection.execute(
                "SELECT 1 FROM simulation_runs WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if run_row is None:
                raise ResultNotFoundError(f"simulation run not found: {session_id}")
            row = connection.execute(
                f"SELECT COUNT(*) FROM simulation_events WHERE {' AND '.join(conditions)}",
                tuple(params),
            ).fetchone()
        return int(row[0])

    def get_run(self, session_id: str, *, include_events: bool = True) -> RunDetail:
        if not self.db_path.exists():
            raise ResultNotFoundError(f"simulation run not found: {session_id}")

        with closing(_connect(self.db_path)) as connection:
            columns = [
                "session_id",
                "state",
                "input_snapshot_json",
                "stop_reason",
                "end_frame",
                "frames_run",
                "error_code",
                "error_message",
                "created_at",
                "started_at",
                "finished_at",
            ]
            if include_events:
                columns.insert(2, "initial_snapshot_json")
            run_row = connection.execute(
                f"""
                SELECT {", ".join(columns)}
                FROM simulation_runs
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
            if run_row is None:
                raise ResultNotFoundError(f"simulation run not found: {session_id}")

            event_rows: list[Any] = []
            if include_events:
                event_rows = connection.execute(
                    """
                    SELECT frame, event_type, data_json
                    FROM simulation_events
                    WHERE session_id = ?
                    ORDER BY ordinal
                    """,
                    (session_id,),
                ).fetchall()

        summary = None
        if run_row["stop_reason"] is not None:
            summary = SimulationRunSummary(
                stop_reason=str(run_row["stop_reason"]),
                end_frame=int(run_row["end_frame"]),
                frames_run=int(run_row["frames_run"]),
            )
        initial_snapshot = run_row["initial_snapshot_json"] if include_events else None
        return RunDetail(
            session_id=str(run_row["session_id"]),
            state=str(run_row["state"]),
            input_snapshot=_load_json_object(str(run_row["input_snapshot_json"])),
            initial_snapshot=(
                None if initial_snapshot is None else _load_json_object(str(initial_snapshot))
            ),
            summary=summary,
            events=tuple(
                RecordedEvent(
                    frame=int(row["frame"]),
                    event_type=str(row["event_type"]),
                    data=_load_json_object(str(row["data_json"])),
                )
                for row in event_rows
            ),
            error_code=None if run_row["error_code"] is None else str(run_row["error_code"]),
            error_message=(
                None if run_row["error_message"] is None else str(run_row["error_message"])
            ),
            created_at=str(run_row["created_at"]),
            started_at=None if run_row["started_at"] is None else str(run_row["started_at"]),
            finished_at=None if run_row["finished_at"] is None else str(run_row["finished_at"]),
        )

    def get_events(
        self,
        session_id: str,
        frame_min: int | None = None,
        frame_max: int | None = None,
        event_type: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> tuple[RecordedEvent, ...]:
        if offset is not None and offset < 0:
            raise ValueError("offset 必须是非负整数")
        if limit is not None and limit < 0:
            raise ValueError("limit 必须是非负整数")
        if not self.db_path.exists():
            raise ResultNotFoundError(f"simulation run not found: {session_id}")

        conditions = ["session_id = ?"]
        params: list[Any] = [session_id]
        if frame_min is not None:
            conditions.append("frame >= ?")
            params.append(frame_min)
        if frame_max is not None:
            conditions.append("frame <= ?")
            params.append(frame_max)
        if event_type is not None:
            conditions.append("event_type = ?")
            params.append(event_type)

        sql = (
            "SELECT frame, event_type, data_json FROM simulation_events "
            f"WHERE {' AND '.join(conditions)} ORDER BY ordinal"
        )
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        elif offset is not None:
            sql += " LIMIT -1"
        if offset is not None:
            sql += " OFFSET ?"
            params.append(offset)

        with closing(_connect(self.db_path)) as connection:
            run_row = connection.execute(
                "SELECT 1 FROM simulation_runs WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if run_row is None:
                raise ResultNotFoundError(f"simulation run not found: {session_id}")
            rows = connection.execute(sql, tuple(params)).fetchall()

        return tuple(
            RecordedEvent(
                frame=int(row["frame"]),
                event_type=str(row["event_type"]),
                data=_load_json_object(str(row["data_json"])),
            )
            for row in rows
        )


def _connect(
    db_path: Path,
    busy_timeout_seconds: float = DEFAULT_BUSY_TIMEOUT_SECONDS,
) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path, timeout=busy_timeout_seconds)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {int(busy_timeout_seconds * 1000)}")
    return connection


def _is_lock_contention(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).lower()
    return "locked" in message or "busy" in message


def _require_missing_run(connection: sqlite3.Connection, session_id: str) -> None:
    row = connection.execute(
        "SELECT 1 FROM simulation_runs WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if row is not None:
        raise ValueError(f"simulation run already exists: {session_id}")


def _dump_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load_json_object(raw: str) -> dict[str, Any]:
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("expected JSON object")
    return payload
