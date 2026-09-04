"""分析节点运行时 SQLite 实现：阶段上下文与单节点物化执行。

每个分析上下文持有一个进程内连接；取数节点直接读结果库，关系算子以临时表
形式物化输入阶段后执行单节点语义。执行器不向应用层暴露 SQL 文本。
"""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from genshin_sim.application.models import (
    AnalysisColumn,
    AnalysisNodeExecution,
    AnalysisPlan,
    AnalysisPlanNode,
    AnalysisStageResult,
    AnalysisStageSelection,
    AnalysisTableResult,
)
from genshin_sim.application.services.analysis_runtime import (
    AnalysisContextNotFoundError,
    AnalysisRuntimeValidationError,
    AnalysisStageNotFoundError,
)
from genshin_sim.infrastructure.results_sqlite.analysis_query import (
    MAX_RESULT_ROWS,
    compile_plan_shapes,
    execute_plan_on_connection,
    register_analysis_aggregates,
)

_STAGE_SOURCE_KIND = "__stage_source"
_SQL_TYPE_BY_ANALYSIS_TYPE = {
    "string": "TEXT",
    "int": "INTEGER",
    "bool": "INTEGER",
    "float": "REAL",
}
_CONTEXT_IDLE_TIMEOUT_SECONDS = 30 * 60


class _StageEntry:
    __slots__ = (
        "stage_id",
        "table",
        "columns",
        "rows",
        "truncated",
        "source_node_id",
        "version",
    )

    def __init__(
        self,
        stage_id: str,
        table: str,
        columns: tuple[AnalysisColumn, ...],
        rows: tuple[tuple[Any, ...], ...],
        truncated: bool,
        source_node_id: str,
        version: int,
    ) -> None:
        self.stage_id = stage_id
        self.table = table
        self.columns = columns
        self.rows = rows
        self.truncated = truncated
        self.source_node_id = source_node_id
        self.version = version


class _ContextState:
    __slots__ = (
        "context_id",
        "session_ids",
        "connection",
        "stages",
        "lock",
        "last_used",
    )

    def __init__(
        self,
        context_id: str,
        session_ids: tuple[str, ...],
        connection: sqlite3.Connection,
    ) -> None:
        self.context_id = context_id
        self.session_ids = session_ids
        self.connection = connection
        self.stages: dict[str, _StageEntry] = {}
        self.lock = threading.RLock()
        self.last_used = time.monotonic()


class SQLiteAnalysisStageExecutor:
    """基于结果库连接的阶段运行时；阶段表仅存在于上下文连接内。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._contexts: dict[str, _ContextState] = {}
        self._contexts_lock = threading.RLock()

    def create_context(self, session_ids: Sequence[str]) -> str:
        self._prune_expired_contexts()
        context_id = "ctx_" + uuid.uuid4().hex[:16]
        connection = self._open_connection()
        state = _ContextState(
            context_id=context_id,
            session_ids=tuple(session_ids),
            connection=connection,
        )
        with self._contexts_lock:
            self._contexts[context_id] = state
        return context_id

    def execute_node(
        self,
        context_id: str,
        execution: AnalysisNodeExecution,
    ) -> AnalysisStageResult:
        state = self._require_context(context_id)
        with state.lock:
            result = self._execute_on_context(state, execution)
            return self._materialize(state, result, execution.node_id)

    def select_stage(
        self,
        context_id: str,
        stage_id: str,
        selection: AnalysisStageSelection,
    ) -> AnalysisStageResult:
        state = self._require_context(context_id)
        with state.lock:
            entry = state.stages.get(stage_id)
            if entry is None:
                raise AnalysisStageNotFoundError(f"阶段不存在：{stage_id}")
            if selection.kind == "row":
                result = self._select_row(state.connection, entry, selection)
                return self._materialize(state, result, entry.source_node_id)
            execution = AnalysisNodeExecution(
                node_id="__select_" + uuid.uuid4().hex[:12],
                kind="filter",
                params={
                    "mode": "all",
                    "conditions": [
                        {"column": column, "op": "eq", "value": value}
                        for column, value in zip(
                            selection.columns,
                            selection.values,
                            strict=True,
                        )
                    ],
                },
                input_stages=(entry.stage_id,),
            )
            result = self._execute_operator(state, execution, (entry,))
            return self._materialize(state, result, entry.source_node_id)

    def merge_stages(
        self,
        context_id: str,
        stage_ids: tuple[str, ...] | list[str],
    ) -> AnalysisStageResult:
        state = self._require_context(context_id)
        with state.lock:
            entries: list[_StageEntry] = []
            for stage_id in stage_ids:
                entry = state.stages.get(stage_id)
                if entry is None:
                    raise AnalysisStageNotFoundError(f"阶段不存在：{stage_id}")
                entries.append(entry)
            if len(entries) < 2:
                raise AnalysisRuntimeValidationError("合并至少需要两个输入阶段")
            reference = entries[0]
            for entry in entries[1:]:
                if _columns_of(entry) != _columns_of(reference):
                    raise AnalysisRuntimeValidationError("合并输入阶段表结构不一致")
            sql = " UNION ALL ".join("SELECT * FROM " + _quoted(entry.table) for entry in entries)
            rows = [
                tuple(row)
                for row in state.connection.execute(sql + " LIMIT " + str(MAX_RESULT_ROWS + 1))
            ]
            truncated = len(rows) > MAX_RESULT_ROWS
            result = AnalysisTableResult(
                columns=reference.columns,
                rows=tuple(rows[:MAX_RESULT_ROWS]),
                truncated=truncated,
            )
            return self._materialize(
                state,
                result,
                reference.source_node_id or "merge",
            )

    def read_stage(self, context_id: str, stage_id: str) -> AnalysisStageResult:
        state = self._require_context(context_id)
        with state.lock:
            entry = state.stages.get(stage_id)
            if entry is None:
                raise AnalysisStageNotFoundError(f"阶段不存在：{stage_id}")
            return _stage_result(entry)

    def close_context(self, context_id: str) -> None:
        with self._contexts_lock:
            state = self._contexts.pop(context_id, None)
        if state is None:
            raise AnalysisContextNotFoundError(f"分析上下文不存在：{context_id}")
        with state.lock:
            state.connection.close()

    def _open_connection(self) -> sqlite3.Connection:
        target: str = ":memory:" if not self._db_path.exists() else str(self._db_path)
        connection = sqlite3.connect(target, check_same_thread=False)
        connection.execute("PRAGMA foreign_keys = ON")
        register_analysis_aggregates(connection)
        return connection

    def _require_context(self, context_id: str) -> _ContextState:
        with self._contexts_lock:
            state = self._contexts.get(context_id)
        if state is None:
            raise AnalysisContextNotFoundError(f"分析上下文不存在：{context_id}")
        state.last_used = time.monotonic()
        return state

    def _prune_expired_contexts(self) -> None:
        now = time.monotonic()
        expired: list[_ContextState] = []
        with self._contexts_lock:
            for context_id, state in list(self._contexts.items()):
                if now - state.last_used >= _CONTEXT_IDLE_TIMEOUT_SECONDS:
                    del self._contexts[context_id]
                    expired.append(state)
        for state in expired:
            with state.lock:
                state.connection.close()

    def _execute_on_context(
        self,
        state: _ContextState,
        execution: AnalysisNodeExecution,
    ) -> AnalysisTableResult:
        if execution.kind == "fetch":
            return self._execute_fetch(state, execution)
        source_entries: list[_StageEntry] = []
        for stage_id in execution.input_stages:
            entry = state.stages.get(stage_id)
            if entry is None:
                raise AnalysisStageNotFoundError(f"阶段不存在：{stage_id}")
            source_entries.append(entry)
        return self._execute_operator(state, execution, source_entries)

    def _execute_fetch(
        self,
        state: _ContextState,
        execution: AnalysisNodeExecution,
    ) -> AnalysisTableResult:
        plan = AnalysisPlan(
            session_ids=state.session_ids,
            nodes=(
                AnalysisPlanNode(
                    id=execution.node_id,
                    kind="fetch",
                    params=execution.params,
                ),
            ),
            outputs=(execution.node_id,),
        )
        if not self._db_path.exists():
            shapes = compile_plan_shapes(plan)
            return AnalysisTableResult(
                columns=shapes[execution.node_id],
                rows=(),
                truncated=False,
            )
        tables = execute_plan_on_connection(state.connection, plan)
        return tables[execution.node_id]

    def _execute_operator(
        self,
        state: _ContextState,
        execution: AnalysisNodeExecution,
        source_entries: Sequence[_StageEntry],
    ) -> AnalysisTableResult:
        prefix = f"__in_{uuid.uuid4().hex[:8]}_"
        source_nodes: list[AnalysisPlanNode] = []
        source_ids: list[str] = []
        used: set[str] = {execution.node_id}
        for index, entry in enumerate(source_entries):
            source_id = f"{prefix}{index}"
            while source_id in used:
                source_id = f"{prefix}{index}_{uuid.uuid4().hex[:4]}"
            used.add(source_id)
            source_ids.append(source_id)
            source_nodes.append(
                AnalysisPlanNode(
                    id=source_id,
                    kind=_STAGE_SOURCE_KIND,
                    params={
                        "stage_table": entry.table,
                        "columns": [
                            {"name": column.name, "type": column.type} for column in entry.columns
                        ],
                    },
                )
            )
        target = AnalysisPlanNode(
            id=execution.node_id,
            kind=execution.kind,
            params=execution.params,
            inputs=tuple(source_ids),
        )
        plan = AnalysisPlan(
            session_ids=state.session_ids,
            nodes=tuple(source_nodes) + (target,),
            outputs=(execution.node_id,),
        )
        tables = execute_plan_on_connection(state.connection, plan)
        return tables[execution.node_id]

    @staticmethod
    def _select_row(
        connection: sqlite3.Connection,
        entry: _StageEntry,
        selection: AnalysisStageSelection,
    ) -> AnalysisTableResult:
        row_index = selection.row_index
        if row_index is None:
            row_index = 0
        row = connection.execute(
            "SELECT * FROM " + _quoted(entry.table) + " WHERE rowid = ?",
            (row_index + 1,),
        ).fetchone()
        rows = () if row is None else (tuple(row),)
        return AnalysisTableResult(
            columns=entry.columns,
            rows=rows,
            truncated=False,
        )

    def _materialize(
        self,
        state: _ContextState,
        result: AnalysisTableResult,
        source_node_id: str,
    ) -> AnalysisStageResult:
        stage_id = "stage_" + uuid.uuid4().hex[:16]
        table = "stage_" + uuid.uuid4().hex[:20]
        self._create_stage_table(state.connection, table, result.columns)
        self._insert_rows(state.connection, table, result.columns, result.rows)
        entry = _StageEntry(
            stage_id=stage_id,
            table=table,
            columns=result.columns,
            rows=result.rows,
            truncated=result.truncated,
            source_node_id=source_node_id,
            version=1,
        )
        state.stages[stage_id] = entry
        return _stage_result(entry)

    @staticmethod
    def _create_stage_table(
        connection: sqlite3.Connection,
        table: str,
        columns: tuple[AnalysisColumn, ...],
    ) -> None:
        definitions = [
            _quoted(column.name) + " " + _SQL_TYPE_BY_ANALYSIS_TYPE.get(column.type, "TEXT")
            for column in columns
        ]
        connection.execute(
            "CREATE TEMP TABLE " + _quoted(table) + " (" + ", ".join(definitions) + ")"
        )

    @staticmethod
    def _insert_rows(
        connection: sqlite3.Connection,
        table: str,
        columns: tuple[AnalysisColumn, ...],
        rows: tuple[tuple[Any, ...], ...],
    ) -> None:
        if not rows:
            return
        placeholders = ", ".join("?" for _ in columns)
        sql = "INSERT INTO " + _quoted(table) + " VALUES (" + placeholders + ")"
        values = [
            tuple(
                _normalize_sql_value(value, column.type)
                for value, column in zip(row, columns, strict=True)
            )
            for row in rows
        ]
        connection.executemany(sql, values)


def _stage_result(entry: _StageEntry) -> AnalysisStageResult:
    return AnalysisStageResult(
        stage_id=entry.stage_id,
        columns=entry.columns,
        rows=entry.rows,
        truncated=entry.truncated,
        source_node_id=entry.source_node_id,
    )


def _columns_of(entry: _StageEntry) -> tuple[tuple[str, str], ...]:
    return tuple((column.name, column.type) for column in entry.columns)


def _quoted(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _normalize_sql_value(value: Any, type_: str) -> Any:
    if value is None:
        return None
    if type_ == "bool":
        return 1 if value else 0
    return value
