"""结果库查询计划编译执行器。

查询计划（取数/算子节点 + 参数 + 有序输入）编译为 CTE 链在结果库上一次执行；
中间结果不出后端。形状推导规则与《分析系统契约》v2 第 5 节一致，
本模块是聚合口径的唯一真值实现并配 golden 断言。
安全边界：字面量全部绑定参数，列名经白名单校验后以标识符引用，不拼接 SQL 文本。
"""

from __future__ import annotations

import math
import re
import sqlite3
from collections.abc import Mapping, Sequence
from contextlib import closing
from pathlib import Path
from typing import Any

from genshin_sim.application.models import (
    AnalysisColumn,
    AnalysisPlan,
    AnalysisPlanNode,
    AnalysisReadSchema,
    AnalysisSchemaColumn,
    AnalysisTableResult,
    AnalysisTableSchema,
)
from genshin_sim.application.services.analysis_query import AnalysisPlanValidationError

MAX_RESULT_ROWS = 10_000
_MAX_EXPR_DEPTH = 16
_MAX_EXTRACT_COLUMNS = 64
_MAX_LIMIT_COUNT = 10_000

_IDENTIFIER_PATTERN = re.compile("^[A-Za-z0-9_-]{1,64}$")
_COLUMN_NAME_PATTERN = re.compile("^[A-Za-z0-9_\u4e00-\u9fff]{1,64}$")

_NUMERIC_TYPES = frozenset({"int", "float"})
_TYPE_VOCABULARY = frozenset({"string", "int", "float", "bool"})

_INPUT_ARITY: dict[str, int] = {
    "fetch": 0,
    "filter": 1,
    "project": 1,
    "sort": 1,
    "limit": 1,
    "aggregate": 1,
    "compute": 1,
    "join": 2,
}

_FETCH_PARAM_KEYS: dict[str, frozenset[str]] = {
    "fetch": frozenset(
        {"source", "snapshot_columns", "event_types", "payload_columns"}
    ),
    "filter": frozenset({"mode", "conditions"}),
    "project": frozenset({"columns"}),
    "sort": frozenset({"keys"}),
    "aggregate": frozenset({"group_by", "aggregates"}),
    "limit": frozenset({"count"}),
    "join": frozenset({"left_key", "right_key", "mode"}),
    "compute": frozenset({"columns"}),
}

_AGGREGATE_FUNCTIONS = frozenset({"sum", "count", "avg", "max", "min", "stddev", "p95"})
_CONDITION_OPERATORS = frozenset(
    {"eq", "ne", "not_in", "in", "gt", "gte", "lt", "lte", "is_null", "is_not_null"}
)
_COMPUTE_OPERATORS = frozenset({"+", "-", "*", "/"})

_RUN_TABLE_SCHEMA: tuple[AnalysisSchemaColumn, ...] = (
    AnalysisSchemaColumn("session_id", "string", "会话 ID"),
    AnalysisSchemaColumn(
        "state",
        "string",
        "运行状态 completed/failed/cancelled",
        "enum:run_state",
    ),
    AnalysisSchemaColumn("name", "string", "运行展示名"),
    AnalysisSchemaColumn("input_schema_version", "int", "输入快照格式版本"),
    AnalysisSchemaColumn("created_at", "string", "创建时间"),
    AnalysisSchemaColumn("started_at", "string", "开始时间"),
    AnalysisSchemaColumn("finished_at", "string", "结束时间"),
    AnalysisSchemaColumn("stop_reason", "string", "停止原因"),
    AnalysisSchemaColumn("end_frame", "int", "结束帧"),
    AnalysisSchemaColumn("frames_run", "int", "实际运行帧数"),
    AnalysisSchemaColumn("event_count", "int", "事件总数"),
    AnalysisSchemaColumn("error_code", "string", "错误码"),
    AnalysisSchemaColumn("error_message", "string", "错误信息"),
    AnalysisSchemaColumn("asset_version", "string", "资产库版本"),
    AnalysisSchemaColumn("content_version", "string", "内容版本"),
    AnalysisSchemaColumn("seed", "string", "随机种子"),
)

_EVENT_TABLE_SCHEMA: tuple[AnalysisSchemaColumn, ...] = (
    AnalysisSchemaColumn("session_id", "string", "会话 ID"),
    AnalysisSchemaColumn("ordinal", "int", "会话内全局事实顺序"),
    AnalysisSchemaColumn("frame", "int", "事件帧号"),
    AnalysisSchemaColumn("event_type", "string", "事件类型名", "enum:event_type"),
)

class SQLiteAnalysisQueryExecutor:
    """结果库查询计划编译执行器（实现 application 的稳定读取协议）。"""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def execute_plan(self, plan: AnalysisPlan) -> Mapping[str, AnalysisTableResult]:
        compiled = _PlanCompiler(plan).compile()
        if not self.db_path.exists():
            return {
                node_id: AnalysisTableResult(
                    columns=compiled.shapes[node_id], rows=(), truncated=False
                )
                for node_id in compiled.output_ids
            }
        with closing(_connect(self.db_path)) as connection:
            connection.create_aggregate("P95", 1, _P95Aggregate)
            return compiled.execute(connection)

    def read_schema(self) -> AnalysisReadSchema:
        return AnalysisReadSchema(
            tables=(
                AnalysisTableSchema(name="simulation_runs", columns=_RUN_TABLE_SCHEMA),
                AnalysisTableSchema(name="simulation_events", columns=_EVENT_TABLE_SCHEMA),
            ),
            event_types=(),
        )


class _CompiledPlan:
    """编译产物：CTE 序列 + 共享绑定 + 输出形状。"""

    def __init__(self) -> None:
        self.ctes: list[str] = []
        self.binds: dict[str, Any] = {}
        self.shapes: dict[str, tuple[AnalysisColumn, ...]] = {}
        self.output_ids: tuple[str, ...] = ()

    def execute(self, connection: sqlite3.Connection) -> Mapping[str, AnalysisTableResult]:
        results: dict[str, AnalysisTableResult] = {}
        prefix = ("WITH " + ", ".join(self.ctes) + " ") if self.ctes else ""
        for node_id in self.output_ids:
            # 输出表硬上限：SQL 侧限制避免全量物化，多取一行用于判定 truncated。
            sql = (
                prefix
                + "SELECT * FROM "
                + _node_sql(node_id)
                + " LIMIT "
                + str(MAX_RESULT_ROWS + 1)
            )
            rows = [tuple(row) for row in connection.execute(sql, self.binds)]
            truncated = len(rows) > MAX_RESULT_ROWS
            results[node_id] = AnalysisTableResult(
                columns=self.shapes[node_id],
                rows=tuple(rows[:MAX_RESULT_ROWS]),
                truncated=truncated,
            )
        return results


class _P95Aggregate:
    """线性插值 P95 聚合（SQLite create_aggregate 工厂）。"""

    def __init__(self) -> None:
        self.values: list[float] = []

    def step(self, value: Any) -> None:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            self.values.append(float(value))

    def finalize(self) -> Any:
        if not self.values:
            return None
        ordered = sorted(self.values)
        if len(ordered) == 1:
            return ordered[0]
        rank = (len(ordered) - 1) * 0.95
        low = int(math.floor(rank))
        high = min(low + 1, len(ordered) - 1)
        fraction = rank - low
        return ordered[low] * (1.0 - fraction) + ordered[high] * fraction


def _connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _quoted(identifier: str) -> str:
    return '"' + identifier + '"'


def _node_sql(node_id: str) -> str:
    return _quoted("n_" + node_id)


def _in_placeholders(binder: _Binder, values: Sequence[Any]) -> str:
    return ", ".join(binder.placeholder(value) for value in values)


class _Binder:
    """生成唯一命名占位符，规避多段 SQL 的绑定顺序问题。"""

    def __init__(self) -> None:
        self.params: dict[str, Any] = {}
        self._counter = 0

    def placeholder(self, value: Any) -> str:
        name = "p" + str(self._counter)
        self._counter += 1
        self.params[name] = value
        return ":" + name


def _typed_json_extract(probe: str, extracted: str, type_: str) -> str:
    if type_ == "string":
        return "CASE WHEN " + probe + " = 'text' THEN " + extracted + " END"
    if type_ == "bool":
        return (
            "CASE WHEN " + probe + " = 'true' THEN 1"
            " WHEN " + probe + " = 'false' THEN 0 END"
        )
    cast_to = "INTEGER" if type_ == "int" else "REAL"
    numeric = "('integer', 'real')" if type_ == "float" else "('integer')"
    return (
        "CASE WHEN " + probe + " IN " + numeric
        + " THEN CAST(" + extracted + " AS " + cast_to + ") END"
    )


def _literal_matches(column_type: str, literal: Any) -> bool:
    if column_type == "string":
        return isinstance(literal, str)
    if column_type == "bool":
        return isinstance(literal, bool)
    if column_type == "int":
        return isinstance(literal, int) and not isinstance(literal, bool)
    if column_type == "float":
        return isinstance(literal, (int, float)) and not isinstance(literal, bool)
    return False


class _PlanCompiler:
    """计划校验（结构 + 形状）与 CTE 编译；问题统一收集后一次性抛出。"""

    def __init__(self, plan: AnalysisPlan) -> None:
        self._plan = plan
        self._issues: list[dict[str, Any]] = []
        self._binder = _Binder()
        self.compiled = _CompiledPlan()
        self.compiled.binds = self._binder.params
        self.compiled.output_ids = tuple(dict.fromkeys(plan.outputs))

    def compile(self) -> _CompiledPlan:
        by_id = self._check_structure()
        order = self._topological_order(by_id)
        shapes: dict[str, tuple[AnalysisColumn, ...]] = {}
        for node_id in order:
            node = by_id[node_id]
            input_shapes = [shapes[item] for item in node.inputs]
            shape = self._infer_shape(node, input_shapes)
            shapes[node.id] = shape
            cte = self._compile_node(node, input_shapes)
            if cte is not None:
                self.compiled.ctes.append(cte)
        if self._issues:
            raise AnalysisPlanValidationError("查询计划校验失败", self._issues)
        self.compiled.shapes = shapes
        return self.compiled

    def _issue(self, node_id: str | None, reason: str) -> None:
        entry: dict[str, Any] = {"reason": reason}
        if node_id is not None:
            entry["node_id"] = node_id
        self._issues.append(entry)

    def _as_list(self, value: Any, node_id: str, label: str) -> list[Any]:
        if value is None:
            return []
        if not isinstance(value, list):
            self._issue(node_id, label + " 必须是数组")
            return []
        return value

    def _check_structure(self) -> dict[str, AnalysisPlanNode]:
        by_id: dict[str, AnalysisPlanNode] = {}
        for node in self._plan.nodes:
            if not isinstance(node.id, str) or not _IDENTIFIER_PATTERN.match(node.id):
                self._issue(None, "节点 id 不合法：" + repr(node.id))
                continue
            if node.id in by_id:
                self._issue(node.id, "节点 id 重复")
                continue
            by_id[node.id] = node
        for node in self._plan.nodes:
            arity = _INPUT_ARITY.get(node.kind)
            if arity is None:
                self._issue(node.id, "未知节点类型：" + node.kind)
                continue
            if len(node.inputs) != arity:
                self._issue(node.id, "输入数量应为 " + str(arity))
            allowed = _FETCH_PARAM_KEYS.get(node.kind, frozenset())
            unknown = sorted(set(node.params) - set(allowed))
            if unknown:
                self._issue(node.id, "不支持的参数：" + ", ".join(unknown))
            for input_id in node.inputs:
                if input_id == node.id or input_id not in by_id:
                    self._issue(node.id, "引用了不存在或非法的上游节点：" + str(input_id))
        if self._issues:
            raise AnalysisPlanValidationError("查询计划校验失败", self._issues)
        self._check_cycles(by_id)
        if self._issues:
            raise AnalysisPlanValidationError("查询计划校验失败", self._issues)
        return by_id

    def _check_cycles(self, by_id: Mapping[str, AnalysisPlanNode]) -> None:
        state: dict[str, int] = {}

        def visit(node_id: str) -> bool:
            status = state.get(node_id, 0)
            if status == 1:
                self._issue(node_id, "查询计划存在环")
                return True
            if status == 2:
                return False
            state[node_id] = 1
            for input_id in by_id[node_id].inputs:
                if visit(input_id):
                    return True
            state[node_id] = 2
            return False

        for node_id in by_id:
            if visit(node_id):
                break

    def _topological_order(self, by_id: Mapping[str, AnalysisPlanNode]) -> list[str]:
        order: list[str] = []
        done: set[str] = set()
        pending = set(by_id)
        while pending:
            ready = sorted(
                node_id
                for node_id in pending
                if all(item in done for item in by_id[node_id].inputs)
            )
            if not ready:
                first = sorted(pending)[0]
                self._issue(first, "查询计划存在环")
                break
            for node_id in ready:
                order.append(node_id)
                done.add(node_id)
                pending.discard(node_id)
        return order

    def _infer_shape(
        self,
        node: AnalysisPlanNode,
        input_shapes: list[tuple[AnalysisColumn, ...]],
    ) -> tuple[AnalysisColumn, ...]:
        kind = node.kind
        params = node.params
        source_columns = input_shapes[0] if input_shapes else ()
        source_types = {column.name: column.type for column in source_columns}
        checker = _ShapeChecker(self, node, source_types)
        passthrough = tuple(AnalysisColumn(name, type_) for name, type_ in source_types.items())
        if kind == "fetch":
            checker.check_fetch(params)
            source = params.get("source")
            if source == "runs":
                return checker.fetch_shape(_RUN_TABLE_SCHEMA, params.get("snapshot_columns"))
            if source == "events":
                return checker.fetch_shape(
                    _EVENT_TABLE_SCHEMA,
                    params.get("payload_columns"),
                    require_event_type=True,
                )
            return ()
        if kind == "filter":
            checker.check_conditions(params)
            return passthrough
        if kind == "sort":
            checker.check_sort(params)
            return passthrough
        if kind == "limit":
            checker.check_limit(params)
            return passthrough
        if kind == "project":
            return checker.project_shape(params)
        if kind == "aggregate":
            return checker.aggregate_shape(params)
        if kind == "compute":
            return checker.compute_shape(params)
        if kind == "join":
            right = input_shapes[1] if len(input_shapes) > 1 else ()
            return checker.join_shape(params, right)
        self._issue(node.id, "未知节点类型：" + kind)
        return ()

    # ---- SQL 编译（形状推导已通过，此处信任参数） ----

    def _compile_node(
        self,
        node: AnalysisPlanNode,
        input_shapes: list[tuple[AnalysisColumn, ...]],
    ) -> str | None:
        alias_sql = _node_sql(node.id)
        source_sql = _node_sql(node.inputs[0]) if node.inputs else ""
        body = self._compile_body(node, input_shapes, self._binder, source_sql)
        if body is None:
            return None
        return alias_sql + " AS (" + body + ")"

    def _compile_body(
        self,
        node: AnalysisPlanNode,
        input_shapes: list[tuple[AnalysisColumn, ...]],
        binder: _Binder,
        source_sql: str,
    ) -> str | None:
        if node.kind == "fetch":
            return self._compile_fetch(node, binder)
        if node.kind == "filter":
            return self._compile_filter(node, binder, source_sql)
        if node.kind == "project":
            return self._compile_project(node, source_sql)
        if node.kind == "sort":
            return self._compile_sort(node, source_sql)
        if node.kind == "limit":
            count = node.params["count"]
            return "SELECT * FROM " + source_sql + " LIMIT " + binder.placeholder(count)
        if node.kind == "aggregate":
            return self._compile_aggregate(node, source_sql)
        if node.kind == "join":
            return self._compile_join(node, input_shapes)
        if node.kind == "compute":
            return self._compile_compute(node, input_shapes, binder, source_sql)
        return None

    def _compile_fetch(self, node: AnalysisPlanNode, binder: _Binder) -> str:
        if node.params.get("source") == "events":
            table = "simulation_events"
            select_items = [_quoted(item.name) for item in _EVENT_TABLE_SCHEMA]
            extracts = node.params.get("payload_columns") or []
            extract_column = "data_json"
            conditions = [
                _quoted("session_id")
                + " IN ("
                + _in_placeholders(binder, self._plan.session_ids)
                + ")"
            ]
            event_types = node.params.get("event_types") or []
            if event_types:
                conditions.append(
                    _quoted("event_type")
                    + " IN ("
                    + _in_placeholders(binder, [str(item) for item in event_types])
                    + ")"
                )
        else:
            table = "simulation_runs"
            select_items = [_quoted(item.name) for item in _RUN_TABLE_SCHEMA]
            extracts = node.params.get("snapshot_columns") or []
            extract_column = "input_snapshot_json"
            conditions = [
                _quoted("session_id")
                + " IN ("
                + _in_placeholders(binder, self._plan.session_ids)
                + ")"
            ]
        for item in extracts:
            path = "$." + str(item["path"])
            typed = _typed_extract(table, extract_column, path, str(item["type"]))
            if node.params.get("source") == "events":
                # 提取列按声明的事件类型作用域取值：其他类型行一律为 NULL
                # （2026-08-26 契约修订，见分析系统契约 3.1）。
                event_type = item.get("event_type") if isinstance(item, dict) else None
                typed = (
                    "CASE WHEN "
                    + _quoted("event_type")
                    + " = "
                    + binder.placeholder(str(event_type))
                    + " THEN "
                    + typed
                    + " ELSE NULL END"
                )
            select_items.append(typed + " AS " + _quoted(str(item["name"])))
        return (
            "SELECT " + ", ".join(select_items)
            + " FROM " + table
            + " WHERE " + " AND ".join(conditions)
        )

    def _compile_filter(self, node: AnalysisPlanNode, binder: _Binder, source_sql: str) -> str:
        mode = node.params.get("mode", "all")
        glue = " OR " if mode == "any" else " AND "
        parts: list[str] = []
        for condition in node.params.get("conditions") or []:
            ref = _quoted(str(condition["column"]))
            op = condition["op"]
            value = condition.get("value")
            if op == "eq":
                parts.append(ref + " = " + binder.placeholder(value))
            elif op == "ne":
                parts.append(
                    "(" + ref + " != " + binder.placeholder(value) + " OR " + ref + " IS NULL)"
                )
            elif op == "in":
                parts.append(ref + " IN (" + _in_placeholders(binder, value) + ")")
            elif op == "not_in":
                parts.append(
                    "("
                    + ref
                    + " NOT IN ("
                    + _in_placeholders(binder, value)
                    + ") OR "
                    + ref
                    + " IS NULL)"
                )
            elif op == "gt":
                parts.append(ref + " > " + binder.placeholder(value))
            elif op == "gte":
                parts.append(ref + " >= " + binder.placeholder(value))
            elif op == "lt":
                parts.append(ref + " < " + binder.placeholder(value))
            elif op == "lte":
                parts.append(ref + " <= " + binder.placeholder(value))
            elif op == "is_null":
                parts.append(ref + " IS NULL")
            else:
                parts.append(ref + " IS NOT NULL")
        if not parts:
            # 空条件组按恒真语义处理，避免生成非法 SQL。
            return "SELECT * FROM " + source_sql
        predicate = "(" + glue.join(parts) + ")" if len(parts) > 1 else parts[0]
        return "SELECT * FROM " + source_sql + " WHERE " + predicate

    def _compile_project(self, node: AnalysisPlanNode, source_sql: str) -> str:
        items: list[str] = []
        for item in node.params.get("columns") or []:
            name = str(item["name"])
            target = item["as"] if item.get("as") is not None else name
            items.append(_quoted(name) + " AS " + _quoted(str(target)))
        return "SELECT " + ", ".join(items) + " FROM " + source_sql

    def _compile_sort(self, node: AnalysisPlanNode, source_sql: str) -> str:
        keys: list[str] = []
        for key in node.params.get("keys") or []:
            direction = "DESC" if key.get("direction") == "desc" else "ASC"
            keys.append(_quoted(str(key["column"])) + " " + direction)
        return "SELECT * FROM " + source_sql + " ORDER BY " + ", ".join(keys)

    def _compile_aggregate(self, node: AnalysisPlanNode, source_sql: str) -> str:
        select_items: list[str] = []
        group_items: list[str] = []
        for name in node.params.get("group_by") or []:
            select_items.append(_quoted(str(name)))
            group_items.append(_quoted(str(name)))
        for item in node.params.get("aggregates") or []:
            fn = str(item["fn"])
            column = _quoted(str(item["column"]))
            alias = item.get("as")
            final = alias if alias is not None else (fn + "_" + str(item["column"]))
            if fn == "sum":
                expr = "COALESCE(SUM(" + column + "), 0)"
            elif fn == "count":
                expr = "COUNT(" + column + ")"
            elif fn == "avg":
                expr = "AVG(" + column + ")"
            elif fn == "max":
                expr = "MAX(" + column + ")"
            elif fn == "min":
                expr = "MIN(" + column + ")"
            elif fn == "stddev":
                x2 = "AVG(" + column + " * " + column + ")"
                mean = "AVG(" + column + ")"
                expr = "SQRT(MAX((" + x2 + " - (" + mean + " * " + mean + ")), 0.0))"
            else:
                expr = "P95(" + column + ")"
            select_items.append(expr + " AS " + _quoted(str(final)))
        sql = "SELECT " + ", ".join(select_items) + " FROM " + source_sql
        if group_items:
            sql += " GROUP BY " + ", ".join(group_items)
        return sql

    def _compile_join(
        self,
        node: AnalysisPlanNode,
        input_shapes: list[tuple[AnalysisColumn, ...]],
    ) -> str:
        left_alias = _node_sql(node.inputs[0])
        right_alias = _node_sql(node.inputs[1])
        left_columns = input_shapes[0]
        right_columns = input_shapes[1] if len(input_shapes) > 1 else ()
        left_names = {column.name for column in left_columns}
        select_items = ["L." + _quoted(column.name) for column in left_columns]
        select_items.extend(
            "R." + _quoted(column.name)
            for column in right_columns
            if column.name not in left_names
        )
        mode = "LEFT JOIN" if node.params.get("mode") == "left" else "JOIN"
        on_clause = (
            "L."
            + _quoted(str(node.params["left_key"]))
            + " = R."
            + _quoted(str(node.params["right_key"]))
        )
        return (
            "SELECT " + ", ".join(select_items)
            + " FROM "
            + left_alias
            + " L "
            + mode
            + " "
            + right_alias
            + " R ON "
            + on_clause
        )

    def _compile_compute(
        self,
        node: AnalysisPlanNode,
        input_shapes: list[tuple[AnalysisColumn, ...]],
        binder: _Binder,
        source_sql: str,
    ) -> str:
        select_items = [
            _quoted(column.name) for column in (input_shapes[0] if input_shapes else ())
        ]
        for item in node.params.get("columns") or []:
            expr_sql = self._compile_expr(item.get("expr"), binder, depth=0)
            select_items.append(expr_sql + " AS " + _quoted(str(item["name"])))
        return "SELECT " + ", ".join(select_items) + " FROM " + source_sql

    def _compile_expr(self, expr: Any, binder: _Binder, *, depth: int) -> str:
        if depth > _MAX_EXPR_DEPTH:
            raise AnalysisPlanValidationError(
                "查询计划校验失败", [{"reason": "计算列表达式过深"}]
            )
        if "col" in expr:
            return _quoted(str(expr["col"]))
        if "lit" in expr:
            return binder.placeholder(expr["lit"])
        op = str(expr["op"])
        left = self._compile_expr(expr.get("left"), binder, depth=depth + 1)
        right = self._compile_expr(expr.get("right"), binder, depth=depth + 1)
        if op == "/":
            return "(CAST(" + left + " AS REAL) / NULLIF(CAST(" + right + " AS REAL), 0))"
        return "(" + left + " " + op + " " + right + ")"


def _pairs(types: Mapping[str, str]) -> tuple[AnalysisColumn, ...]:
    return tuple(AnalysisColumn(name, type_) for name, type_ in types.items())


class _ShapeChecker:
    """单算子参数校验 + 输出形状推导。"""

    def __init__(
        self,
        compiler: _PlanCompiler,
        node: AnalysisPlanNode,
        types: Mapping[str, str],
    ) -> None:
        self.compiler = compiler
        self.node = node
        self.types = types

    def fetch_shape(
        self,
        base_schema: tuple[AnalysisSchemaColumn, ...],
        raw_extracts: Any,
        *,
        require_event_type: bool = False,
    ) -> tuple[AnalysisColumn, ...]:
        output = [AnalysisColumn(item.name, item.type) for item in base_schema]
        taken = {column.name for column in output}
        extracts = self.compiler._as_list(raw_extracts, self.node.id, "提取列")
        if len(extracts) > _MAX_EXTRACT_COLUMNS:
            self.compiler._issue(self.node.id, "提取列数量超过上限 " + str(_MAX_EXTRACT_COLUMNS))
        for item in extracts[:_MAX_EXTRACT_COLUMNS]:
            path = item.get("path") if isinstance(item, dict) else None
            name = item.get("name") if isinstance(item, dict) else None
            type_ = item.get("type") if isinstance(item, dict) else None
            if require_event_type:
                event_type = item.get("event_type") if isinstance(item, dict) else None
                if not isinstance(event_type, str) or not event_type:
                    self.compiler._issue(
                        self.node.id, "载荷提取列缺少事件类型 event_type"
                    )
                    continue
            if not isinstance(path, str) or not path or "'" in path or path.startswith("."):
                self.compiler._issue(self.node.id, "提取路径不合法：" + str(path))
                continue
            if not isinstance(name, str) or not _COLUMN_NAME_PATTERN.match(name):
                self.compiler._issue(self.node.id, "提取列名不合法：" + str(name))
                continue
            if type_ not in _TYPE_VOCABULARY:
                self.compiler._issue(self.node.id, "提取列类型不合法：" + str(type_))
                continue
            if name in taken:
                self.compiler._issue(self.node.id, "输出列名重复：" + name)
                continue
            taken.add(name)
            output.append(AnalysisColumn(name, type_))
        return tuple(output)

    def check_fetch(self, params: Mapping[str, Any]) -> None:
        """取数节点来源与标量参数校验（提取列在 fetch_shape 中校验）。"""

        source = params.get("source")
        if source not in ("runs", "events"):
            self.compiler._issue(self.node.id, "source 必须是 runs 或 events")
            return
        if source == "runs":
            for key in ("event_types", "payload_columns"):
                if key in params:
                    self.compiler._issue(self.node.id, f"source=runs 不支持参数 {key}")
            return
        if "snapshot_columns" in params:
            self.compiler._issue(self.node.id, "source=events 不支持参数 snapshot_columns")
        event_types = params.get("event_types")
        if event_types is not None and (
            not isinstance(event_types, list)
            or any(not isinstance(item, str) for item in event_types)
        ):
            self.compiler._issue(self.node.id, "event_types 必须是字符串数组")
    def project_shape(self, params: Mapping[str, Any]) -> tuple[AnalysisColumn, ...]:
        output: list[AnalysisColumn] = []
        seen: set[str] = set()
        columns = self._list(params.get("columns"), "columns")
        if not columns:
            self.compiler._issue(self.node.id, "投影至少需要一列")
        for item in columns:
            name = self._field(item, "name")
            alias = self._field(item, "as")
            if not isinstance(name, str) or name not in self.types:
                self.compiler._issue(self.node.id, "投影列不存在：" + str(name))
                continue
            final = alias if alias is not None else name
            if not isinstance(final, str) or not _COLUMN_NAME_PATTERN.match(final):
                self.compiler._issue(self.node.id, "输出列名不合法：" + str(final))
                continue
            if final in seen:
                self.compiler._issue(self.node.id, "输出列名重复：" + final)
                continue
            seen.add(final)
            output.append(AnalysisColumn(final, self.types[name]))
        return tuple(output)

    def aggregate_shape(self, params: Mapping[str, Any]) -> tuple[AnalysisColumn, ...]:
        output: list[AnalysisColumn] = []
        seen: set[str] = set()
        group_by = self._list(params.get("group_by"), "group_by")
        aggregates = self._list(params.get("aggregates"), "aggregates")
        if not group_by and not aggregates:
            self.compiler._issue(self.node.id, "聚合至少需要分组列或聚合项")
        for name in group_by:
            if not isinstance(name, str) or name not in self.types:
                self.compiler._issue(self.node.id, "分组列不存在：" + str(name))
                continue
            if name in seen:
                self.compiler._issue(self.node.id, "分组列重复：" + name)
                continue
            seen.add(name)
            output.append(AnalysisColumn(name, self.types[name]))
        for item in aggregates:
            fn = self._field(item, "fn")
            column = self._field(item, "column")
            alias = self._field(item, "as")
            if fn is None or fn not in _AGGREGATE_FUNCTIONS:
                self.compiler._issue(self.node.id, "不支持的聚合函数：" + str(fn))
                continue
            if not isinstance(column, str) or column not in self.types:
                self.compiler._issue(self.node.id, "聚合列不存在：" + str(column))
                continue
            if fn != "count" and self.types[column] not in _NUMERIC_TYPES:
                self.compiler._issue(self.node.id, "聚合函数要求 int/float 列：" + column)
                continue
            default_name = fn + "_" + column
            final = alias if alias is not None else default_name
            if not isinstance(final, str) or not _COLUMN_NAME_PATTERN.match(final):
                self.compiler._issue(self.node.id, "聚合输出列名不合法：" + str(final))
                continue
            if final in seen:
                self.compiler._issue(self.node.id, "输出列名重复：" + final)
                continue
            seen.add(final)
            if fn in ("avg", "stddev", "p95"):
                result_type = "float"
            elif fn in ("sum", "max", "min"):
                result_type = self.types[column]
            else:
                result_type = "int"
            output.append(AnalysisColumn(final, result_type))
        return tuple(output)

    def compute_shape(self, params: Mapping[str, Any]) -> tuple[AnalysisColumn, ...]:
        output = [AnalysisColumn(name, type_) for name, type_ in self.types.items()]
        taken = set(self.types)
        columns = self._list(params.get("columns"), "columns")
        if not columns:
            self.compiler._issue(self.node.id, "计算列至少需要一列")
        for item in columns:
            name = self._field(item, "name")
            expr = item.get("expr") if isinstance(item, dict) else None
            if not isinstance(name, str) or not _COLUMN_NAME_PATTERN.match(name):
                self.compiler._issue(self.node.id, "计算列名不合法：" + str(name))
                continue
            if name in taken:
                self.compiler._issue(self.node.id, "输出列名重复：" + name)
                continue
            expr_type = self.check_expr(expr, depth=0)
            if expr_type is None:
                continue
            taken.add(name)
            output.append(AnalysisColumn(name, expr_type))
        return tuple(output)

    def join_shape(
        self,
        params: Mapping[str, Any],
        right_shape: tuple[AnalysisColumn, ...],
    ) -> tuple[AnalysisColumn, ...]:
        output = [AnalysisColumn(name, type_) for name, type_ in self.types.items()]
        left_names = {column.name for column in output}
        mode = params.get("mode", "inner")
        if mode not in ("inner", "left"):
            self.compiler._issue(self.node.id, "连接模式只允许 inner/left")
        left_key = params.get("left_key")
        right_key = params.get("right_key")
        if not isinstance(left_key, str) or left_key not in left_names:
            self.compiler._issue(self.node.id, "左表连接键不存在：" + str(left_key))
        right_types = {column.name: column.type for column in right_shape}
        if not isinstance(right_key, str) or right_key not in right_types:
            self.compiler._issue(self.node.id, "右表连接键不存在：" + str(right_key))
        for name, type_ in right_types.items():
            if name not in left_names:
                output.append(AnalysisColumn(name, type_))
        return tuple(output)

    def check_conditions(self, params: Mapping[str, Any]) -> None:
        mode = params.get("mode", "all")
        if mode not in ("all", "any"):
            self.compiler._issue(self.node.id, "条件组合模式只允许 all/any")
        for condition in self._list(params.get("conditions"), "conditions"):
            column = self._field(condition, "column")
            op = self._field(condition, "op")
            if not isinstance(column, str) or column not in self.types:
                self.compiler._issue(self.node.id, "条件列不存在：" + str(column))
                continue
            if op is None or op not in _CONDITION_OPERATORS:
                self.compiler._issue(self.node.id, "不支持的条件操作符：" + str(op))
                continue
            if op in ("gt", "gte", "lt", "lte") and self.types[column] not in _NUMERIC_TYPES:
                self.compiler._issue(self.node.id, "数值比较要求 int/float 列：" + column)
                continue
            if op in ("is_null", "is_not_null"):
                if isinstance(condition, dict) and "value" in condition:
                    self.compiler._issue(self.node.id, "空判断条件不接受 value")
                continue
            value = condition.get("value") if isinstance(condition, dict) else None
            if op in ("in", "not_in"):
                if not isinstance(value, list) or not value:
                    self.compiler._issue(self.node.id, "in/not_in 需要非空数组：" + column)
                    continue
                mismatched = [
                    item for item in value if not _literal_matches(self.types[column], item)
                ]
                if mismatched:
                    self.compiler._issue(
                        self.node.id, "in/not_in 元素类型与列不符：" + column
                    )
                continue
            if not _literal_matches(self.types[column], value):
                self.compiler._issue(self.node.id, "条件字面量类型与列不符：" + column)

    def check_sort(self, params: Mapping[str, Any]) -> None:
        keys = self._list(params.get("keys"), "keys")
        if not keys:
            self.compiler._issue(self.node.id, "排序至少需要一个键")
        for key in keys:
            column = self._field(key, "column")
            direction = key.get("direction", "asc") if isinstance(key, dict) else "asc"
            if direction not in ("asc", "desc"):
                self.compiler._issue(self.node.id, "排序方向只允许 asc/desc")
            if not isinstance(column, str) or column not in self.types:
                self.compiler._issue(self.node.id, "排序列不存在：" + str(column))

    def check_limit(self, params: Mapping[str, Any]) -> None:
        count = params.get("count")
        if (
            not isinstance(count, int)
            or isinstance(count, bool)
            or not 1 <= count <= _MAX_LIMIT_COUNT
        ):
            self.compiler._issue(
                self.node.id,
                "limit count 必须是 1 到 " + str(_MAX_LIMIT_COUNT) + " 的整数",
            )

    def check_expr(self, expr: Any, *, depth: int) -> str | None:
        if depth > _MAX_EXPR_DEPTH:
            self.compiler._issue(self.node.id, "计算列表达式过深")
            return None
        if not isinstance(expr, dict):
            self.compiler._issue(self.node.id, "计算列表达式必须是对象")
            return None
        if "col" in expr:
            name = expr["col"]
            if not isinstance(name, str) or name not in self.types:
                self.compiler._issue(self.node.id, "计算列引用了不存在的列：" + str(name))
                return None
            if self.types[name] not in _NUMERIC_TYPES:
                self.compiler._issue(self.node.id, "计算列要求数值列：" + name)
                return None
            return self.types[name]
        if "lit" in expr:
            value = expr["lit"]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                self.compiler._issue(self.node.id, "计算列字面量必须是数值")
                return None
            return "int" if isinstance(value, int) else "float"
        op = expr.get("op")
        if op not in _COMPUTE_OPERATORS:
            self.compiler._issue(self.node.id, "不支持的运算符：" + str(op))
            return None
        left = self.check_expr(expr.get("left"), depth=depth + 1)
        right = self.check_expr(expr.get("right"), depth=depth + 1)
        if left is None or right is None:
            return None
        if op == "/":
            return "float"
        return "int" if left == "int" and right == "int" else "float"

    def _list(self, value: Any, label: str) -> list[Any]:
        return self.compiler._as_list(value, self.node.id, label)

    @staticmethod
    def _field(item: Any, key: str) -> Any:
        return item.get(key) if isinstance(item, dict) else None


def _typed_extract(table: str, json_column: str, path: str, type_: str) -> str:
    probe = "json_type(" + table + "." + _quoted(json_column) + ", '" + path + "')"
    extracted = "json_extract(" + table + "." + _quoted(json_column) + ", '" + path + "')"
    return _typed_json_extract(probe, extracted, type_)
