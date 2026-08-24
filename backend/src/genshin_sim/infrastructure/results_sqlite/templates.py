"""结果库模板注册表与执行器。

模板 = 声明（参数 / 关系输入 / 输出列）+ SQL + 可选的 Python 行变换。
声明与 SQL 同处本模块，与结果库 schema 强耦合；前端只消费声明，
执行参数全部走 prepared statement，关系输入由本模块拼装为临时表。
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from genshin_sim.application.models import (
    RelationTable,
    TemplateColumn,
    TemplateDeclaration,
    TemplateOutput,
    TemplateParam,
    TemplateRelation,
    TemplateResult,
)
from genshin_sim.application.services.analysis_templates import (
    TemplateNotFoundError,
    TemplateValidationError,
)

MAX_RESULT_ROWS = 10_000

_TIMELINE_EVENT_TYPES: tuple[str, ...] = (
    "DAMAGE_RESOLVED",
    "HEALING_RESOLVED",
    "BUFF_APPLIED",
    "BUFF_REMOVED",
    "SHIELD_ABSORPTION_RESOLVED",
    "CHARACTER_HEALTH_CHANGED",
    "DIRECT_ENERGY_CHANGE_RESOLVED",
    "REACTION_OCCURRED",
    "ACTION_STARTED",
    "TEAM_SWITCHED",
    "INPUT_KEY_RECEIVED",
    "AURA_ICD_RESOLVED",
)

_METRIC_SUMMARY_COLUMNS: tuple[str, ...] = (
    "total_damage",
    "dps",
    "highest_hit",
    "average_hit",
    "total_healing",
)


@dataclass(frozen=True, slots=True)
class _TemplateSpec:
    """一张模板的完整实现：声明 + SQL 构建 + 可选行变换。"""

    declaration: TemplateDeclaration
    build_sql: Callable[
        [Mapping[str, Any], Mapping[str, RelationTable]],
        tuple[str, dict[str, Any]],
    ]
    needs_database: bool = True
    transform: (
        Callable[
            [list[list[Any]], Mapping[str, RelationTable]],
            list[list[Any]],
        ]
        | None
    ) = None


class SQLiteAnalysisTemplateExecutor:
    """结果库 SQL 模板执行器（实现 application 的稳定读取协议）。"""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def list_templates(self) -> tuple[TemplateDeclaration, ...]:
        return tuple(spec.declaration for spec in _TEMPLATES.values())

    def execute(
        self,
        template_id: str,
        params: Mapping[str, Any] | None = None,
        relations: Mapping[str, RelationTable] | None = None,
    ) -> TemplateResult:
        """执行模板：关系输入建临时表，SQL 安全绑定，返回一张表。"""

        spec = _TEMPLATES.get(template_id)
        if spec is None:
            raise TemplateNotFoundError(template_id)
        params = dict(params or {})
        relations = dict(relations or {})
        declaration = spec.declaration
        columns = declaration.output.columns
        if not self.db_path.exists() and spec.needs_database:
            return TemplateResult(columns=columns, rows=(), truncated=False)

        with closing(_connect(self.db_path)) as connection:
            relation_names: dict[str, str] = {}
            for name, table in relations.items():
                relation_names[name] = _create_relation_table(connection, name, table, declaration)
            sql, binds = spec.build_sql(params, relations)
            for name, table_name in relation_names.items():
                sql = sql.replace("{{" + name + "}}", table_name)
            rows = [list(row) for row in connection.execute(sql, binds)]

        if spec.transform is not None:
            rows = spec.transform(rows, relations)
        truncated = len(rows) > MAX_RESULT_ROWS
        rows = rows[:MAX_RESULT_ROWS]
        return TemplateResult(
            columns=columns,
            rows=tuple(tuple(row) for row in rows),
            truncated=truncated,
        )


def _create_relation_table(
    connection: sqlite3.Connection,
    name: str,
    table: RelationTable,
    declaration: TemplateDeclaration,
) -> str:
    """把请求中的关系表写入连接级临时表，返回表名。"""

    spec = next(
        (relation for relation in declaration.relations if relation.name == name),
        None,
    )
    if spec is None:
        raise TemplateValidationError(f"模板 {declaration.template_id} 不支持关系输入：{name}")
    table_name = f"__rel_{name}"
    column_index = {column: idx for idx, column in enumerate(table.columns)}
    quoted_columns = ", ".join(f'"{column}"' for column in spec.columns)
    insert_marks = ", ".join("?" for _ in spec.columns)
    insert_columns = ", ".join(f'"{column}"' for column in spec.columns)
    connection.execute(f'CREATE TEMP TABLE "{table_name}" ({quoted_columns})')
    for row in table.rows:
        values = tuple(_bind_value(row[column_index[column]]) for column in spec.columns)
        connection.execute(
            f'INSERT INTO "{table_name}" ({insert_columns}) VALUES ({insert_marks})',
            values,
        )
    return table_name


def _bind_value(value: Any) -> Any:
    """关系单元格里的 JSON 复合值以 JSON 文本落入临时表。"""

    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return value


def _connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


class _Binder:
    """生成唯一命名占位符，规避多段 SQL 的绑定顺序问题。"""

    def __init__(self) -> None:
        self.params: dict[str, Any] = {}
        self._counter = 0

    def placeholder(self, value: Any) -> str:
        name = f"p{self._counter}"
        self._counter += 1
        self.params[name] = value
        return f":{name}"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TemplateValidationError("session_ids 必须是字符串列表")
    return list(value)


def _in_placeholders(binder: _Binder, values: Sequence[str]) -> str:
    return ", ".join(binder.placeholder(value) for value in values)


def _frame_clause(binder: _Binder, alias: str, params: Mapping[str, Any]) -> str:
    parts: list[str] = []
    frame_min = params.get("frame_min")
    frame_max = params.get("frame_max")
    if frame_min is not None:
        parts.append(f"{alias}.frame >= {binder.placeholder(frame_min)}")
    if frame_max is not None:
        parts.append(f"{alias}.frame <= {binder.placeholder(frame_max)}")
    return (" AND " + " AND ".join(parts)) if parts else ""


def _session_metrics_columns() -> tuple[TemplateColumn, ...]:
    columns = [
        TemplateColumn("session_id", "string"),
        TemplateColumn("run_name", "string"),
        TemplateColumn("frames_run", "int"),
    ]
    for slot in range(1, 5):
        columns.extend(
            [
                TemplateColumn(f"char_{slot}_key", "string"),
                TemplateColumn(f"char_{slot}_level", "int"),
                TemplateColumn(f"char_{slot}_constellation", "int"),
                TemplateColumn(f"weapon_{slot}_key", "string"),
                TemplateColumn(f"weapon_{slot}_level", "int"),
                TemplateColumn(f"weapon_{slot}_refinement", "int"),
            ]
        )
    columns.extend(
        [
            TemplateColumn("total_damage", "float"),
            TemplateColumn("dps", "float"),
            TemplateColumn("highest_hit", "float"),
            TemplateColumn("average_hit", "float"),
            TemplateColumn("total_healing", "float"),
            TemplateColumn("damage_count", "int"),
            TemplateColumn("healing_count", "int"),
        ]
    )
    return tuple(columns)


def _session_metrics_sql(
    params: Mapping[str, Any],
    relations: Mapping[str, RelationTable],
) -> tuple[str, dict[str, Any]]:
    session_ids = _string_list(params["session_ids"])
    binder = _Binder()
    events_in = _in_placeholders(binder, session_ids)
    frame = _frame_clause(binder, "e", params)
    runs_in = _in_placeholders(binder, session_ids)
    slot_exprs: list[str] = []
    for slot in range(1, 5):
        index = slot - 1
        slot_exprs.extend(
            [
                (
                    f"json_extract(r.input_snapshot_json, "
                    f"'$.team[{index}].character.asset_key') AS char_{slot}_key"
                ),
                (
                    f"json_extract(r.input_snapshot_json, "
                    f"'$.team[{index}].character.level') AS char_{slot}_level"
                ),
                (
                    f"json_extract(r.input_snapshot_json, "
                    f"'$.team[{index}].character.constellation') AS char_{slot}_constellation"
                ),
                (
                    f"json_extract(r.input_snapshot_json, "
                    f"'$.team[{index}].weapon.asset_key') AS weapon_{slot}_key"
                ),
                (
                    f"json_extract(r.input_snapshot_json, "
                    f"'$.team[{index}].weapon.level') AS weapon_{slot}_level"
                ),
                (
                    f"json_extract(r.input_snapshot_json, "
                    f"'$.team[{index}].weapon.refinement') AS weapon_{slot}_refinement"
                ),
            ]
        )
    sql = f"""
SELECT r.session_id,
       r.name AS run_name,
       r.frames_run,
       {", ".join(slot_exprs)},
       COALESCE(m.total_damage, 0) AS total_damage,
       CASE WHEN r.frames_run > 0
            THEN COALESCE(m.total_damage, 0) / (r.frames_run / 60.0)
            ELSE 0 END AS dps,
       COALESCE(m.highest_hit, 0) AS highest_hit,
       CASE WHEN COALESCE(m.damage_count, 0) > 0
            THEN COALESCE(m.total_damage, 0) / m.damage_count
            ELSE 0 END AS average_hit,
       COALESCE(m.total_healing, 0) AS total_healing,
       COALESCE(m.damage_count, 0) AS damage_count,
       COALESCE(m.healing_count, 0) AS healing_count
FROM simulation_runs r
LEFT JOIN (
    SELECT e.session_id,
           COALESCE(SUM(CASE WHEN e.event_type = 'DAMAGE_RESOLVED'
                            THEN CAST(json_extract(e.data_json, '$.result.final_damage') AS REAL)
                            END), 0) AS total_damage,
           COUNT(CASE WHEN e.event_type = 'DAMAGE_RESOLVED' THEN 1 END) AS damage_count,
           MAX(CASE WHEN e.event_type = 'DAMAGE_RESOLVED'
                    THEN CAST(json_extract(e.data_json, '$.result.final_damage') AS REAL)
                    END) AS highest_hit,
           COALESCE(SUM(CASE WHEN e.event_type = 'HEALING_RESOLVED'
                            THEN CAST(json_extract(e.data_json, '$.result.final_healing') AS REAL)
                            END), 0) AS total_healing,
           COUNT(CASE WHEN e.event_type = 'HEALING_RESOLVED' THEN 1 END) AS healing_count
    FROM simulation_events e
    WHERE e.session_id IN ({events_in}){frame}
    GROUP BY e.session_id
) m ON m.session_id = r.session_id
WHERE r.session_id IN ({runs_in})
ORDER BY r.session_id
"""
    return sql, binder.params


def _share_rows_sql(
    params: Mapping[str, Any],
    relations: Mapping[str, RelationTable],
) -> tuple[str, dict[str, Any]]:
    dimension = params.get("dimension")
    if dimension == "source":
        event_type = "DAMAGE_RESOLVED"
        group_path = "$.result.source_ref.entity_id"
        value_path = "$.result.final_damage"
    elif dimension == "damage_kind":
        event_type = "DAMAGE_RESOLVED"
        group_path = "$.result.damage_type"
        value_path = "$.result.final_damage"
    elif dimension == "healing_source":
        event_type = "HEALING_RESOLVED"
        group_path = "$.result.source_ref.entity_id"
        value_path = "$.result.final_healing"
    else:
        raise TemplateValidationError(f"share_rows 不支持的 dimension：{dimension}")

    binder = _Binder()
    session_in = _in_placeholders(binder, _string_list(params["session_ids"]))
    event_ph = binder.placeholder(event_type)
    frame = _frame_clause(binder, "e", params)
    sql = f"""
SELECT json_extract(e.data_json, '{group_path}') AS "group",
       SUM(CAST(json_extract(e.data_json, '{value_path}') AS REAL)) AS value
FROM simulation_events e
WHERE e.event_type = {event_ph} AND e.session_id IN ({session_in}){frame}
GROUP BY "group"
ORDER BY "group"
"""
    return sql, binder.params


def _timeline_rows_sql(
    params: Mapping[str, Any],
    relations: Mapping[str, RelationTable],
) -> tuple[str, dict[str, Any]]:
    session_ids = _string_list(params["session_ids"])
    selected = params.get("event_types")
    if not selected:
        selected = list(_TIMELINE_EVENT_TYPES)
    unknown = [item for item in selected if item not in _TIMELINE_EVENT_TYPES]
    if unknown:
        raise TemplateValidationError(f"timeline_rows 不支持的事件类型：{unknown}")

    binder = _Binder()
    ctes: list[str] = []
    parts: list[str] = []

    point_types = [item for item in ("DAMAGE_RESOLVED", "HEALING_RESOLVED") if item in selected]
    if point_types:
        point_in = _in_placeholders(binder, point_types)
        session_in = _in_placeholders(binder, session_ids)
        frame = _frame_clause(binder, "e", params)
        parts.append(
            f"""SELECT e.session_id,
       CASE WHEN e.event_type = 'DAMAGE_RESOLVED' THEN '伤害' ELSE '治疗' END AS track,
       e.frame AS start_frame,
       NULL AS end_frame,
       CASE WHEN e.event_type = 'DAMAGE_RESOLVED'
            THEN CAST(json_extract(e.data_json, '$.result.final_damage') AS REAL)
            ELSE CAST(json_extract(e.data_json, '$.result.final_healing') AS REAL) END AS value,
       json_extract(e.data_json, '$.result.source_ref.entity_id') AS label
FROM simulation_events e
WHERE e.event_type IN ({point_in}) AND e.session_id IN ({session_in}){frame}"""
        )

    if "BUFF_APPLIED" in selected and "BUFF_REMOVED" in selected:
        applied_in = _in_placeholders(binder, session_ids)
        applied_frame = _frame_clause(binder, "e", params)
        removed_in = _in_placeholders(binder, session_ids)
        removed_frame = _frame_clause(binder, "e", params)
        ctes.append(
            f"""applied AS (
  SELECT session_id,
         json_extract(data_json, '$.result.instance_ref') AS ref,
         MIN(frame) AS start_frame,
         json_extract(data_json, '$.result.definition_key') AS label
  FROM simulation_events e
  WHERE e.event_type = 'BUFF_APPLIED' AND e.session_id IN ({applied_in}){applied_frame}
  GROUP BY session_id, ref
),
removed AS (
  SELECT session_id,
         json_extract(data_json, '$.result.instance_ref') AS ref,
         MAX(frame) AS end_frame
  FROM simulation_events e
  WHERE e.event_type = 'BUFF_REMOVED' AND e.session_id IN ({removed_in}){removed_frame}
  GROUP BY session_id, ref
)"""
        )
        parts.append(
            """SELECT a.session_id, 'Buff' AS track, a.start_frame, r.end_frame,
       NULL AS value, a.label
FROM applied a
LEFT JOIN removed r ON r.session_id = a.session_id AND r.ref = a.ref"""
        )

    generic_types = [
        item
        for item in selected
        if item not in ("DAMAGE_RESOLVED", "HEALING_RESOLVED", "BUFF_APPLIED", "BUFF_REMOVED")
    ]
    if generic_types:
        generic_in = _in_placeholders(binder, generic_types)
        session_in = _in_placeholders(binder, session_ids)
        frame = _frame_clause(binder, "e", params)
        parts.append(
            f"""SELECT e.session_id, e.event_type AS track, e.frame AS start_frame,
       NULL AS end_frame, NULL AS value, NULL AS label
FROM simulation_events e
WHERE e.event_type IN ({generic_in}) AND e.session_id IN ({session_in}){frame}"""
        )

    if not parts:
        raise TemplateValidationError("timeline_rows 未选择任何事件类型")
    with_clause = ("WITH " + ",\n".join(ctes) + "\n") if ctes else ""
    sql = with_clause + "\nUNION ALL\n".join(parts) + "\nORDER BY session_id, start_frame, track"
    return sql, binder.params


def _metric_summary_sql(
    params: Mapping[str, Any],
    relations: Mapping[str, RelationTable],
) -> tuple[str, dict[str, Any]]:
    selects: list[str] = []
    for column in _METRIC_SUMMARY_COLUMNS:
        selects.append(
            f"""SELECT '{column}' AS metric,
       AVG({column}) AS avg,
       MAX({column}) AS max,
       MIN({column}) AS min,
       SQRT(MAX(AVG({column} * {column}) - AVG({column}) * AVG({column}), 0.0)) AS stddev
FROM {{{{source}}}}"""
        )
    return "\nUNION ALL\n".join(selects), {}


def _metric_summary_transform(
    rows: list[list[Any]],
    relations: Mapping[str, RelationTable],
) -> list[list[Any]]:
    table = relations["source"]
    column_index = {column: idx for idx, column in enumerate(table.columns)}
    result: list[list[Any]] = []
    for row in rows:
        metric = row[0]
        values = [
            value
            for value in (table_row[column_index[metric]] for table_row in table.rows)
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        ]
        result.append([*row, _percentile(values, 0.95)])
    return result


def _percentile(values: list[float | int], ratio: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = math.ceil(ratio * len(ordered))
    return ordered[rank - 1]


_TEMPLATES: dict[str, _TemplateSpec] = {
    "session_metrics": _TemplateSpec(
        declaration=TemplateDeclaration(
            template_id="session_metrics",
            display_name="每会话指标",
            params=(
                TemplateParam(
                    name="session_ids",
                    type="string[]",
                    required=True,
                    binding=("session_group", "upstream_column"),
                ),
                TemplateParam(
                    name="frame_min",
                    type="int",
                    required=False,
                    binding=("static", "config"),
                ),
                TemplateParam(
                    name="frame_max",
                    type="int",
                    required=False,
                    binding=("static", "config"),
                ),
            ),
            relations=(),
            output=TemplateOutput(columns=_session_metrics_columns()),
        ),
        build_sql=_session_metrics_sql,
    ),
    "share_rows": _TemplateSpec(
        declaration=TemplateDeclaration(
            template_id="share_rows",
            display_name="占比行",
            params=(
                TemplateParam(
                    name="session_ids",
                    type="string[]",
                    required=True,
                    binding=("session_group", "upstream_column"),
                ),
                TemplateParam(
                    name="dimension",
                    type="string",
                    required=True,
                    binding=("static", "config"),
                ),
                TemplateParam(
                    name="frame_min",
                    type="int",
                    required=False,
                    binding=("static", "config"),
                ),
                TemplateParam(
                    name="frame_max",
                    type="int",
                    required=False,
                    binding=("static", "config"),
                ),
            ),
            relations=(),
            output=TemplateOutput(
                columns=(
                    TemplateColumn("group", "string"),
                    TemplateColumn("value", "float"),
                )
            ),
        ),
        build_sql=_share_rows_sql,
    ),
    "timeline_rows": _TemplateSpec(
        declaration=TemplateDeclaration(
            template_id="timeline_rows",
            display_name="时间轴行",
            params=(
                TemplateParam(
                    name="session_ids",
                    type="string[]",
                    required=True,
                    binding=("session_group", "upstream_column"),
                ),
                TemplateParam(
                    name="event_types",
                    type="string[]",
                    required=False,
                    binding=("static", "config"),
                ),
                TemplateParam(
                    name="frame_min",
                    type="int",
                    required=False,
                    binding=("static", "config"),
                ),
                TemplateParam(
                    name="frame_max",
                    type="int",
                    required=False,
                    binding=("static", "config"),
                ),
            ),
            relations=(),
            output=TemplateOutput(
                columns=(
                    TemplateColumn("session_id", "string"),
                    TemplateColumn("track", "string"),
                    TemplateColumn("start_frame", "int"),
                    TemplateColumn("end_frame", "int"),
                    TemplateColumn("value", "float"),
                    TemplateColumn("label", "string"),
                )
            ),
        ),
        build_sql=_timeline_rows_sql,
    ),
    "metric_summary": _TemplateSpec(
        declaration=TemplateDeclaration(
            template_id="metric_summary",
            display_name="指标汇总",
            params=(),
            relations=(
                TemplateRelation(
                    name="source",
                    columns=_METRIC_SUMMARY_COLUMNS,
                    required=True,
                ),
            ),
            output=TemplateOutput(
                columns=(
                    TemplateColumn("metric", "string"),
                    TemplateColumn("avg", "float"),
                    TemplateColumn("max", "float"),
                    TemplateColumn("min", "float"),
                    TemplateColumn("stddev", "float"),
                    TemplateColumn("p95", "float"),
                )
            ),
        ),
        build_sql=_metric_summary_sql,
        needs_database=False,
        transform=_metric_summary_transform,
    ),
}
