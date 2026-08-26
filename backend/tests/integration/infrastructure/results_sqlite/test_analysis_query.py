"""结果库查询计划编译执行器集成测试（含聚合口径 golden 断言）。"""

from __future__ import annotations

from typing import Any

import pytest

from genshin_sim.application.execution import (
    CompletedSimulationRun,
    RecordedEvent,
    SimulationRunSummary,
)
from genshin_sim.application.models import AnalysisPlan, AnalysisPlanNode
from genshin_sim.application.services.analysis_query import AnalysisPlanValidationError
from genshin_sim.infrastructure.results_sqlite import SQLiteResultWriter
from genshin_sim.infrastructure.results_sqlite.analysis_query import (
    SQLiteAnalysisQueryExecutor,
)


def _damage(
    frame: int,
    *,
    amount: float,
    source: str = "character:slot_1",
    damage_type: str = "skill",
) -> RecordedEvent:
    return RecordedEvent(
        frame=frame,
        event_type="DAMAGE_RESOLVED",
        data={
            "result": {
                "request_id": f"damage:{frame}",
                "source_ref": {"kind": "character", "entity_id": source},
                "target_ref": {"kind": "target", "entity_id": "target:target_1"},
                "final_damage": amount,
                "damage_type": damage_type,
            }
        },
    )


def _healing(frame: int, *, amount: float, source: str = "character:slot_1") -> RecordedEvent:
    return RecordedEvent(
        frame=frame,
        event_type="HEALING_RESOLVED",
        data={
            "result": {
                "request_id": f"healing:{frame}",
                "source_ref": {"kind": "character", "entity_id": source},
                "target_ref": {"kind": "character", "entity_id": source},
                "final_healing": amount,
            }
        },
    )


def _run(
    session_id: str,
    *,
    events: tuple[RecordedEvent, ...],
    frames_run: int = 120,
    team: list[dict[str, Any]] | None = None,
) -> CompletedSimulationRun:
    return CompletedSimulationRun(
        session_id=session_id,
        input_schema_version=2,
        input_kind="simulation_input",
        input_meta={"name": f"跑批 {session_id}"},
        input_snapshot={
            "schema_version": 2,
            "kind": "simulation_input",
            "meta": {"name": f"跑批 {session_id}"},
            "team": team
            or [
                {
                    "character": {
                        "asset_key": "character:barbara",
                        "level": 80,
                        "constellation": 2,
                    },
                    "weapon": {
                        "asset_key": "weapon:thrilling_tales",
                        "level": 90,
                        "refinement": 5,
                    },
                }
            ],
        },
        summary=SimulationRunSummary(
            stop_reason="MAX_FRAMES",
            end_frame=frames_run,
            frames_run=frames_run,
        ),
        events=events,
        initial_snapshot={"frame": 0, "providers": {}},
        created_at="2026-08-24T00:00:00+00:00",
        started_at="2026-08-24T00:00:00+00:00",
        finished_at="2026-08-24T00:01:00+00:00",
    )


def _executor(tmp_path) -> SQLiteAnalysisQueryExecutor:
    db_path = tmp_path / "results.db"
    writer = SQLiteResultWriter(db_path)
    writer.save_run(
        _run(
            "run:1",
            frames_run=120,
            events=(
                _damage(10, amount=300.0, damage_type="skill"),
                _damage(20, amount=700.0, damage_type="burst"),
            ),
        )
    )
    writer.save_run(
        _run(
            "run:2",
            frames_run=60,
            events=(_damage(3, amount=500.0),),
            team=[
                {
                    "character": {
                        "asset_key": "character:amber",
                        "level": 70,
                        "constellation": 0,
                    },
                    "weapon": {
                        "asset_key": "weapon:slingshot",
                        "level": 80,
                        "refinement": 1,
                    },
                }
            ],
        )
    )
    return SQLiteAnalysisQueryExecutor(db_path)


def _plan(nodes: tuple[AnalysisPlanNode, ...], outputs: tuple[str, ...]) -> AnalysisPlan:
    return AnalysisPlan(session_ids=("run:1", "run:2"), nodes=nodes, outputs=outputs)


def _column_values(table, name: str) -> list[Any]:
    index = next(i for i, c in enumerate(table.columns) if c.name == name)
    return [row[index] for row in table.rows]


def test_fetch_runs_source_exposes_snapshot_condition_columns(tmp_path) -> None:
    executor = _executor(tmp_path)
    plan = _plan(
        (
            AnalysisPlanNode(
                id="runs1",
                kind="fetch",
                params={
                    "source": "runs",
                    "snapshot_columns": [
                        {
                            "path": "team[0].character.asset_key",
                            "name": "char_1_key",
                            "type": "string",
                        }
                    ]
                },
            ),
        ),
        ("runs1",),
    )

    tables = executor.execute_plan(plan)

    table = tables["runs1"]
    assert _column_values(table, "char_1_key") == [
        "character:barbara",
        "character:amber",
    ]
    assert all(column.name != "input_snapshot_json" for column in table.columns)


def test_per_session_dps_pipeline_golden(tmp_path) -> None:
    """成员指标主链 golden：事件求和 → 连接运行表 → 计算 DPS。"""

    executor = _executor(tmp_path)
    plan = _plan(
        (
            AnalysisPlanNode(id="runs1", kind="fetch", params={"source": "runs"}),
            AnalysisPlanNode(
                id="ev1",
                kind="fetch",
                params={
                    "source": "events",
                    "event_types": ["DAMAGE_RESOLVED"],
                    "payload_columns": [
                        {
                            "event_type": "DAMAGE_RESOLVED",
                            "path": "result.final_damage",
                            "name": "damage",
                            "type": "float",
                        }
                    ],
                },
            ),
            AnalysisPlanNode(
                id="agg1",
                kind="aggregate",
                params={
                    "group_by": ["session_id"],
                    "aggregates": [{"fn": "sum", "column": "damage"}],
                },
                inputs=("ev1",),
            ),
            AnalysisPlanNode(
                id="j1",
                kind="join",
                params={
                    "left_key": "session_id",
                    "right_key": "session_id",
                    "mode": "inner",
                },
                inputs=("runs1", "agg1"),
            ),
            AnalysisPlanNode(
                id="c1",
                kind="compute",
                params={
                    "columns": [
                        {
                            "name": "dps",
                            "expr": {
                                "op": "/",
                                "left": {"col": "sum_damage"},
                                "right": {
                                    "op": "/",
                                    "left": {"col": "frames_run"},
                                    "right": {"lit": 60},
                                },
                            },
                        }
                    ]
                },
                inputs=("j1",),
            ),
        ),
        ("c1",),
    )

    tables = executor.execute_plan(plan)

    table = tables["c1"]
    rows = {
        row[table.columns.index(next(c for c in table.columns if c.name == "session_id"))]: row
        for row in table.rows
    }
    del rows
    sessions = sorted(_column_values(table, "session_id"))
    assert sessions == ["run:1", "run:2"]
    dps_index = next(i for i, c in enumerate(table.columns) if c.name == "dps")
    sum_index = next(i for i, c in enumerate(table.columns) if c.name == "sum_damage")
    by_session = {
        _column_values(table, "session_id")[i]: (row[sum_index], row[dps_index])
        for i, row in enumerate(table.rows)
    }
    assert by_session["run:1"] == (1000.0, pytest.approx(500.0))
    assert by_session["run:2"] == (500.0, pytest.approx(500.0))


def test_global_aggregate_statistics_golden(tmp_path) -> None:
    """无分组聚合的统计口径：stddev 为总体标准差，p95 线性插值。"""

    executor = _executor(tmp_path)
    plan = _plan(
        (
            AnalysisPlanNode(
                id="ev1",
                kind="fetch",
                params={
                    "source": "events",
                    "payload_columns": [
                        {
                            "event_type": "DAMAGE_RESOLVED",
                            "path": "result.final_damage",
                            "name": "damage",
                            "type": "float",
                        }
                    ]
                },
            ),
            AnalysisPlanNode(
                id="agg1",
                kind="aggregate",
                params={
                    "aggregates": [
                        {"fn": "sum", "column": "damage"},
                        {"fn": "count", "column": "damage"},
                        {"fn": "avg", "column": "damage"},
                        {"fn": "max", "column": "damage"},
                        {"fn": "min", "column": "damage"},
                        {"fn": "stddev", "column": "damage"},
                        {"fn": "p95", "column": "damage"},
                    ]
                },
                inputs=("ev1",),
            ),
        ),
        ("agg1",),
    )

    table = executor.execute_plan(plan)["agg1"]

    assert len(table.rows) == 1
    row = table.rows[0]
    names = [column.name for column in table.columns]
    assert names == [
        "sum_damage",
        "count_damage",
        "avg_damage",
        "max_damage",
        "min_damage",
        "stddev_damage",
        "p95_damage",
    ]
    assert row[names.index("sum_damage")] == pytest.approx(1500.0)
    assert row[names.index("count_damage")] == 3
    assert row[names.index("avg_damage")] == pytest.approx(500.0)
    assert row[names.index("max_damage")] == pytest.approx(700.0)
    assert row[names.index("min_damage")] == pytest.approx(300.0)
    # 总体标准差：sqrt(((300-500)^2 + 0 + (700-500)^2) / 3)。
    assert row[names.index("stddev_damage")] == pytest.approx((80000 / 3) ** 0.5)
    # 线性插值：rank = (3 - 1) * 0.95 = 1.9，落在排序后第 2、3 个值之间。
    assert row[names.index("p95_damage")] == pytest.approx(500 + (700 - 500) * 0.9)


def test_filter_pushdown_and_ne_null_semantics(tmp_path) -> None:
    executor = _executor(tmp_path)
    plan = _plan(
        (
            AnalysisPlanNode(id="runs1", kind="fetch", params={"source": "runs"}),
            AnalysisPlanNode(
                id="f1",
                kind="filter",
                params={
                    "mode": "all",
                    "conditions": [
                        {"column": "state", "op": "eq", "value": "completed"},
                        {"column": "stop_reason", "op": "not_in", "value": ["CANCELLED"]},
                    ],
                },
                inputs=("runs1",),
            ),
        ),
        ("f1",),
    )

    tables = executor.execute_plan(plan)

    assert sorted(_column_values(tables["f1"], "session_id")) == ["run:1", "run:2"]


def test_empty_filter_is_identity(tmp_path) -> None:
    executor = _executor(tmp_path)
    plan = _plan(
        (
            AnalysisPlanNode(id="runs1", kind="fetch", params={"source": "runs"}),
            AnalysisPlanNode(id="f1", kind="filter", params={}, inputs=("runs1",)),
        ),
        ("f1",),
    )

    tables = executor.execute_plan(plan)

    assert sorted(_column_values(tables["f1"], "session_id")) == ["run:1", "run:2"]


def test_project_rejects_empty_columns(tmp_path) -> None:
    executor = _executor(tmp_path)
    plan = _plan(
        (
            AnalysisPlanNode(id="runs1", kind="fetch", params={"source": "runs"}),
            AnalysisPlanNode(id="p1", kind="project", params={"columns": []}, inputs=("runs1",)),
        ),
        ("p1",),
    )

    with pytest.raises(AnalysisPlanValidationError) as exc_info:
        executor.execute_plan(plan)

    details = list(exc_info.value.details)
    assert any(item.get("node_id") == "p1" and "至少" in item.get("reason", "") for item in details)


def test_aggregate_rejects_empty_params(tmp_path) -> None:
    executor = _executor(tmp_path)
    plan = _plan(
        (
            AnalysisPlanNode(id="ev1", kind="fetch", params={"source": "events"}),
            AnalysisPlanNode(id="a1", kind="aggregate", params={}, inputs=("ev1",)),
        ),
        ("a1",),
    )

    with pytest.raises(AnalysisPlanValidationError) as exc_info:
        executor.execute_plan(plan)

    details = list(exc_info.value.details)
    assert any(item.get("node_id") == "a1" and "至少" in item.get("reason", "") for item in details)


def test_compute_rejects_empty_columns(tmp_path) -> None:
    executor = _executor(tmp_path)
    plan = _plan(
        (
            AnalysisPlanNode(id="runs1", kind="fetch", params={"source": "runs"}),
            AnalysisPlanNode(id="c1", kind="compute", params={"columns": []}, inputs=("runs1",)),
        ),
        ("c1",),
    )

    with pytest.raises(AnalysisPlanValidationError) as exc_info:
        executor.execute_plan(plan)

    details = list(exc_info.value.details)
    assert any(item.get("node_id") == "c1" and "至少" in item.get("reason", "") for item in details)


@pytest.mark.parametrize(
    ("params", "reason"),
    [
        ({"source": "events", "event_types": "DAMAGE_RESOLVED"}, "event_types"),
        ({"source": "events", "frame_min": 0}, "frame_min"),
        ({"source": "events", "frame_max": 18000}, "frame_max"),
    ],
)
def test_fetch_events_source_rejects_invalid_parameters(tmp_path, params, reason) -> None:
    executor = _executor(tmp_path)
    plan = _plan(
        (AnalysisPlanNode(id="ev1", kind="fetch", params=params),),
        ("ev1",),
    )

    with pytest.raises(AnalysisPlanValidationError) as exc_info:
        executor.execute_plan(plan)

    details = list(exc_info.value.details)
    assert any(
        item.get("node_id") == "ev1" and reason in item.get("reason", "")
        for item in details
    )


def test_fetch_events_source_requires_payload_event_type(tmp_path) -> None:
    """载荷提取列缺少 event_type 时校验拒绝（2026-08-26 契约修订）。"""

    executor = _executor(tmp_path)
    plan = _plan(
        (
            AnalysisPlanNode(
                id="ev1",
                kind="fetch",
                params={
                    "source": "events",
                    "payload_columns": [
                        {"path": "result.final_damage", "name": "damage", "type": "float"}
                    ],
                },
            ),
        ),
        ("ev1",),
    )

    with pytest.raises(AnalysisPlanValidationError) as exc_info:
        executor.execute_plan(plan)

    details = list(exc_info.value.details)
    assert any(
        item.get("node_id") == "ev1" and "事件类型" in item.get("reason", "")
        for item in details
    )


def test_fetch_events_source_scopes_extract_by_event_type(tmp_path) -> None:
    """提取列按声明事件类型作用域取值：同路径字段跨类型不混合（2026-08-26）。"""

    db_path = tmp_path / "results.db"
    writer = SQLiteResultWriter(db_path)
    writer.save_run(
        _run(
            "run:1",
            events=(
                _damage(10, amount=300.0, source="character:dps"),
                _healing(20, amount=500.0, source="character:healer"),
            ),
        )
    )
    executor = SQLiteAnalysisQueryExecutor(db_path)
    plan = _plan(
        (
            AnalysisPlanNode(
                id="ev1",
                kind="fetch",
                params={
                    "source": "events",
                    "payload_columns": [
                        {
                            "event_type": "DAMAGE_RESOLVED",
                            "path": "result.source_ref.entity_id",
                            "name": "damage_source",
                            "type": "string",
                        },
                        {
                            "event_type": "HEALING_RESOLVED",
                            "path": "result.source_ref.entity_id",
                            "name": "healing_source",
                            "type": "string",
                        },
                    ],
                },
            ),
        ),
        ("ev1",),
    )

    table = executor.execute_plan(plan)["ev1"]
    damage = _column_values(table, "damage_source")
    healing = _column_values(table, "healing_source")
    assert [value for value in damage if value is not None] == ["character:dps"]
    assert sum(value is None for value in damage) == 1
    assert [value for value in healing if value is not None] == ["character:healer"]
    assert sum(value is None for value in healing) == 1


def test_fetch_rejects_missing_or_invalid_source(tmp_path) -> None:
    executor = _executor(tmp_path)
    plan = _plan((AnalysisPlanNode(id="f1", kind="fetch", params={}),), ("f1",))

    with pytest.raises(AnalysisPlanValidationError) as exc_info:
        executor.execute_plan(plan)

    details = list(exc_info.value.details)
    assert any(
        item.get("node_id") == "f1" and "source" in item.get("reason", "")
        for item in details
    )


def test_fetch_rejects_cross_source_params(tmp_path) -> None:
    executor = _executor(tmp_path)
    plan = _plan(
        (
            AnalysisPlanNode(
                id="f1",
                kind="fetch",
                params={"source": "runs", "event_types": ["DAMAGE_RESOLVED"]},
            ),
        ),
        ("f1",),
    )

    with pytest.raises(AnalysisPlanValidationError) as exc_info:
        executor.execute_plan(plan)

    details = list(exc_info.value.details)
    assert any(
        item.get("node_id") == "f1" and "source=runs 不支持" in item.get("reason", "")
        for item in details
    )


def test_output_limit_marks_truncated(tmp_path) -> None:
    db_path = tmp_path / "results.db"
    writer = SQLiteResultWriter(db_path)
    writer.save_run(
        _run(
            "run:big",
            events=tuple(_damage(index, amount=1.0) for index in range(10_001)),
        )
    )
    executor = SQLiteAnalysisQueryExecutor(db_path)
    plan = AnalysisPlan(
        session_ids=("run:big",),
        nodes=(AnalysisPlanNode(id="ev1", kind="fetch", params={"source": "events"}),),
        outputs=("ev1",),
    )

    table = executor.execute_plan(plan)["ev1"]

    assert table.truncated is True
    assert len(table.rows) == 10_000


def test_unknown_column_reports_node_detail(tmp_path) -> None:
    executor = SQLiteAnalysisQueryExecutor(tmp_path / "missing.db")
    plan = _plan(
        (
            AnalysisPlanNode(
                id="f1",
                kind="filter",
                params={
                    "conditions": [{"column": "nope", "op": "eq", "value": 1}]
                },
            ),
        ),
        ("f1",),
    )

    with pytest.raises(AnalysisPlanValidationError) as exc_info:
        executor.execute_plan(plan)

    details = list(exc_info.value.details)
    assert any(item.get("node_id") == "f1" for item in details)


def test_cycle_detection(tmp_path) -> None:
    executor = SQLiteAnalysisQueryExecutor(tmp_path / "missing.db")
    plan = AnalysisPlan(
        session_ids=("run:1",),
        nodes=(
            AnalysisPlanNode(id="a", kind="limit", params={"count": 1}, inputs=("b",)),
            AnalysisPlanNode(id="b", kind="limit", params={"count": 1}, inputs=("a",)),
        ),
        outputs=("a",),
    )

    with pytest.raises(AnalysisPlanValidationError):
        executor.execute_plan(plan)


def test_read_schema_lists_tables_from_executor() -> None:
    executor = SQLiteAnalysisQueryExecutor("nonexistent/results.db")

    schema = executor.read_schema()

    table_names = {table.name for table in schema.tables}
    assert table_names == {"simulation_runs", "simulation_events"}
    assert schema.event_types == ()
