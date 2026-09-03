"""分析节点运行时（阶段执行）集成测试。"""

from __future__ import annotations

from typing import Any

import pytest

from genshin_sim.application.execution import (
    CompletedSimulationRun,
    RecordedEvent,
    SimulationRunSummary,
)
from genshin_sim.application.models import (
    AnalysisNodeExecution,
    AnalysisPlan,
    AnalysisPlanNode,
    AnalysisStageSelection,
)
from genshin_sim.application.services.analysis_runtime import (
    AnalysisContextNotFoundError,
    AnalysisStageNotFoundError,
)
from genshin_sim.infrastructure.results_sqlite import (
    SQLiteAnalysisStageExecutor,
    SQLiteResultWriter,
)
from genshin_sim.infrastructure.results_sqlite.analysis_query import (
    SQLiteAnalysisQueryExecutor,
)


def _damage(frame: int, *, amount: float) -> RecordedEvent:
    return RecordedEvent(
        frame=frame,
        event_type="DAMAGE_RESOLVED",
        data={
            "result": {
                "request_id": f"damage:{frame}",
                "source_ref": {"kind": "character", "entity_id": "character:slot_1"},
                "target_ref": {"kind": "target", "entity_id": "target:target_1"},
                "final_damage": amount,
                "formula_key": "damage_formula.general",
            }
        },
    )


def _run(session_id: str, *, events: tuple[RecordedEvent, ...]) -> CompletedSimulationRun:
    return CompletedSimulationRun(
        session_id=session_id,
        input_schema_version=2,
        input_kind="simulation_input",
        input_meta={"name": f"跑批 {session_id}"},
        input_snapshot={
            "schema_version": 2,
            "kind": "simulation_input",
            "meta": {"name": f"跑批 {session_id}"},
            "team": [],
        },
        summary=SimulationRunSummary(
            stop_reason="MAX_FRAMES",
            end_frame=120,
            frames_run=120,
        ),
        events=events,
        initial_snapshot={"frame": 0, "providers": {}},
        created_at="2026-08-24T00:00:00+00:00",
        started_at="2026-08-24T00:00:00+00:00",
        finished_at="2026-08-24T00:01:00+00:00",
    )


def _populate(tmp_path) -> Any:
    db_path = tmp_path / "results.db"
    writer = SQLiteResultWriter(db_path)
    writer.save_run(
        _run(
            "run:1",
            events=(_damage(10, amount=300.0), _damage(20, amount=700.0)),
        )
    )
    writer.save_run(
        _run(
            "run:2",
            events=(_damage(3, amount=500.0),),
        )
    )
    return db_path


def _columns(stage) -> dict[str, int]:
    return {column.name: index for index, column in enumerate(stage.columns)}


def _column_values(stage, name: str) -> list[Any]:
    index = _columns(stage)[name]
    return [row[index] for row in stage.rows]


def test_stage_runtime_reproduces_fetch_filter_pipeline(tmp_path) -> None:
    db_path = _populate(tmp_path)
    runtime = SQLiteAnalysisStageExecutor(db_path)
    context_id = runtime.create_context(("run:1", "run:2"))
    try:
        runs = runtime.execute_node(
            context_id,
            AnalysisNodeExecution(
                node_id="runs1",
                kind="fetch",
                params={"source": "runs"},
            ),
        )
        assert sorted(_column_values(runs, "session_id")) == ["run:1", "run:2"]

        filtered = runtime.execute_node(
            context_id,
            AnalysisNodeExecution(
                node_id="f1",
                kind="filter",
                params={
                    "mode": "all",
                    "conditions": [{"column": "stop_reason", "op": "eq", "value": "MAX_FRAMES"}],
                },
                input_stages=(runs.stage_id,),
            ),
        )
        assert sorted(_column_values(filtered, "session_id")) == ["run:1", "run:2"]

        read_back = runtime.read_stage(context_id, filtered.stage_id)
        assert read_back == filtered
    finally:
        runtime.close_context(context_id)


def test_stage_runtime_reproduces_aggregate_join_compute_golden(tmp_path) -> None:
    db_path = _populate(tmp_path)
    runtime = SQLiteAnalysisStageExecutor(db_path)
    legacy = SQLiteAnalysisQueryExecutor(db_path)
    context_id = runtime.create_context(("run:1", "run:2"))
    try:
        runs = runtime.execute_node(
            context_id,
            AnalysisNodeExecution(
                node_id="runs1",
                kind="fetch",
                params={"source": "runs"},
            ),
        )
        events = runtime.execute_node(
            context_id,
            AnalysisNodeExecution(
                node_id="ev1",
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
        )
        aggregated = runtime.execute_node(
            context_id,
            AnalysisNodeExecution(
                node_id="agg1",
                kind="aggregate",
                params={
                    "group_by": ["session_id"],
                    "aggregates": [{"fn": "sum", "column": "damage"}],
                },
                input_stages=(events.stage_id,),
            ),
        )
        joined = runtime.execute_node(
            context_id,
            AnalysisNodeExecution(
                node_id="j1",
                kind="join",
                params={
                    "left_key": "session_id",
                    "right_key": "session_id",
                    "mode": "inner",
                },
                input_stages=(runs.stage_id, aggregated.stage_id),
            ),
        )
        computed = runtime.execute_node(
            context_id,
            AnalysisNodeExecution(
                node_id="c1",
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
                input_stages=(joined.stage_id,),
            ),
        )

        expected = legacy.execute_plan(
            AnalysisPlan(
                session_ids=("run:1", "run:2"),
                nodes=(
                    AnalysisPlanNode(id="runs1", kind="fetch", params={"source": "runs"}),
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
                outputs=("c1",),
            )
        )["c1"]

        assert [column.name for column in computed.columns] == [
            column.name for column in expected.columns
        ]
        by_session = {
            _column_values(computed, "session_id")[i]: tuple(row)
            for i, row in enumerate(computed.rows)
        }
        expected_by_session = {
            _column_values(expected, "session_id")[i]: tuple(row)
            for i, row in enumerate(expected.rows)
        }
        for session_id, row in expected_by_session.items():
            actual = by_session[session_id]
            assert actual[0] == row[0]
            assert actual[1] == pytest.approx(row[1])
    finally:
        runtime.close_context(context_id)


def test_stage_runtime_fetch_without_result_db_returns_empty_stage(tmp_path) -> None:
    runtime = SQLiteAnalysisStageExecutor(tmp_path / "missing.db")
    context_id = runtime.create_context(("run:1",))
    try:
        stage = runtime.execute_node(
            context_id,
            AnalysisNodeExecution(
                node_id="runs1",
                kind="fetch",
                params={"source": "runs"},
            ),
        )
        assert stage.rows == ()
        assert "session_id" in _columns(stage)
    finally:
        runtime.close_context(context_id)


def test_stage_runtime_rejects_missing_context_and_stage(tmp_path) -> None:
    runtime = SQLiteAnalysisStageExecutor(_populate(tmp_path))
    with pytest.raises(AnalysisContextNotFoundError):
        runtime.read_stage("ctx_missing", "stage_missing")

    context_id = runtime.create_context(("run:1",))
    try:
        with pytest.raises(AnalysisStageNotFoundError):
            runtime.execute_node(
                context_id,
                AnalysisNodeExecution(
                    node_id="f1",
                    kind="limit",
                    params={"count": 1},
                    input_stages=("stage_missing",),
                ),
            )
    finally:
        runtime.close_context(context_id)


def test_stage_runtime_select_group_and_row(tmp_path) -> None:
    runtime = SQLiteAnalysisStageExecutor(_populate(tmp_path))
    context_id = runtime.create_context(("run:1", "run:2"))
    try:
        runs = runtime.execute_node(
            context_id,
            AnalysisNodeExecution(
                node_id="runs1",
                kind="fetch",
                params={"source": "runs"},
            ),
        )
        selected = runtime.select_stage(
            context_id,
            runs.stage_id,
            AnalysisStageSelection(
                kind="group",
                columns=("session_id",),
                values=("run:2",),
            ),
        )
        assert _column_values(selected, "session_id") == ["run:2"]

        row = runtime.select_stage(
            context_id,
            runs.stage_id,
            AnalysisStageSelection(kind="row", row_index=1),
        )
        assert len(row.rows) == 1
        assert _column_values(row, "session_id")[0] in ("run:1", "run:2")
        assert runtime.read_stage(context_id, row.stage_id) == row
    finally:
        runtime.close_context(context_id)


def test_stage_runtime_merge_same_shape_stages(tmp_path) -> None:
    runtime = SQLiteAnalysisStageExecutor(_populate(tmp_path))
    context_id = runtime.create_context(("run:1", "run:2"))
    try:
        left = runtime.execute_node(
            context_id,
            AnalysisNodeExecution(
                node_id="runs1",
                kind="fetch",
                params={"source": "runs"},
            ),
        )
        right = runtime.execute_node(
            context_id,
            AnalysisNodeExecution(
                node_id="runs2",
                kind="fetch",
                params={"source": "runs"},
            ),
        )
        merged = runtime.merge_stages(
            context_id,
            (left.stage_id, right.stage_id),
        )

        assert [column.name for column in merged.columns] == [
            column.name for column in left.columns
        ]
        assert len(merged.rows) == 4
        assert sorted(_column_values(merged, "session_id")) == [
            "run:1",
            "run:1",
            "run:2",
            "run:2",
        ]
    finally:
        runtime.close_context(context_id)


def test_stage_runtime_matches_legacy_for_derive_chain(tmp_path) -> None:
    """新旧执行器 golden 对齐：常量列链结果完全一致。"""

    db_path = _populate(tmp_path)
    runtime = SQLiteAnalysisStageExecutor(db_path)
    legacy = SQLiteAnalysisQueryExecutor(db_path)
    context_id = runtime.create_context(("run:1", "run:2"))
    try:
        runs = runtime.execute_node(
            context_id,
            AnalysisNodeExecution(
                node_id="runs1",
                kind="fetch",
                params={"source": "runs"},
            ),
        )
        derived = runtime.execute_node(
            context_id,
            AnalysisNodeExecution(
                node_id="d1",
                kind="derive",
                params={
                    "columns": [
                        {
                            "name": "attribute_key",
                            "type": "string",
                            "value": "stat.crit_rate",
                        }
                    ]
                },
                input_stages=(runs.stage_id,),
            ),
        )

        expected = legacy.execute_plan(
            AnalysisPlan(
                session_ids=("run:1", "run:2"),
                nodes=(
                    AnalysisPlanNode(id="runs1", kind="fetch", params={"source": "runs"}),
                    AnalysisPlanNode(
                        id="d1",
                        kind="derive",
                        params={
                            "columns": [
                                {
                                    "name": "attribute_key",
                                    "type": "string",
                                    "value": "stat.crit_rate",
                                }
                            ]
                        },
                        inputs=("runs1",),
                    ),
                ),
                outputs=("d1",),
            )
        )["d1"]

        assert [column.name for column in derived.columns] == [
            column.name for column in expected.columns
        ]
        assert sorted(tuple(row) for row in derived.rows) == sorted(
            tuple(row) for row in expected.rows
        )
    finally:
        runtime.close_context(context_id)


def test_stage_runtime_close_context_drops_stages(tmp_path) -> None:
    runtime = SQLiteAnalysisStageExecutor(_populate(tmp_path))
    context_id = runtime.create_context(("run:1",))
    stage = runtime.execute_node(
        context_id,
        AnalysisNodeExecution(
            node_id="runs1",
            kind="fetch",
            params={"source": "runs"},
        ),
    )
    assert stage.rows != ()
    runtime.close_context(context_id)
    with pytest.raises(AnalysisContextNotFoundError):
        runtime.read_stage(context_id, stage.stage_id)


def test_stage_runtime_prunes_idle_context_on_next_create(
    tmp_path,
    monkeypatch,
) -> None:
    """空闲超时上下文在后续创建时回收，防止页面刷新等场景长期占用连接。"""

    monkeypatch.setattr(
        "genshin_sim.infrastructure.results_sqlite.analysis_stage._CONTEXT_IDLE_TIMEOUT_SECONDS",
        -1.0,
    )
    runtime = SQLiteAnalysisStageExecutor(_populate(tmp_path))
    first = runtime.create_context(("run:1",))
    second = runtime.create_context(("run:1",))
    try:
        with pytest.raises(AnalysisContextNotFoundError):
            runtime.read_stage(first, "stage_missing")
    finally:
        runtime.close_context(second)
