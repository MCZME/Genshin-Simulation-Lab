"""结果库模板执行器集成测试。"""

from __future__ import annotations

from typing import Any

import pytest

from genshin_sim.application.execution import (
    CompletedSimulationRun,
    RecordedEvent,
    SimulationRunSummary,
)
from genshin_sim.application.models import RelationTable
from genshin_sim.infrastructure.results_sqlite import SQLiteResultWriter
from genshin_sim.infrastructure.results_sqlite.templates import (
    SQLiteAnalysisTemplateExecutor,
    TemplateNotFoundError,
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


def _healing(frame: int, *, amount: float, source: str = "character:slot_2") -> RecordedEvent:
    return RecordedEvent(
        frame=frame,
        event_type="HEALING_RESOLVED",
        data={
            "result": {
                "healing_id": f"healing:{frame}",
                "source_ref": {"kind": "character", "entity_id": source},
                "target_ref": {"kind": "character", "entity_id": "character:slot_1"},
                "final_healing": amount,
            }
        },
    )


def _buff_apply(frame: int, ref: str, definition: str) -> RecordedEvent:
    return RecordedEvent(
        frame=frame,
        event_type="BUFF_APPLIED",
        data={
            "result": {
                "instance_ref": {"entity_id": "character:slot_1", "buff_id": ref},
                "definition_key": definition,
            }
        },
    )


def _buff_remove(frame: int, ref: str) -> RecordedEvent:
    return RecordedEvent(
        frame=frame,
        event_type="BUFF_REMOVED",
        data={
            "result": {
                "instance_ref": {"entity_id": "character:slot_1", "buff_id": ref},
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
                },
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
                },
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


def _write_runs(tmp_path) -> SQLiteAnalysisTemplateExecutor:
    db_path = tmp_path / "results.db"
    writer = SQLiteResultWriter(db_path)
    writer.save_run(
        _run(
            "run:1",
            frames_run=120,
            events=(
                _buff_apply(10, "buff:atk", "atk_buff"),
                _damage(10, amount=300.0, damage_type="skill"),
                _healing(15, amount=100.0),
                _damage(20, amount=700.0, damage_type="burst"),
                _buff_remove(90, "buff:atk"),
                RecordedEvent(
                    frame=5,
                    event_type="ACTION_STARTED",
                    data={"action_key": "elemental_skill"},
                ),
            ),
        )
    )
    writer.save_run(
        _run(
            "run:2",
            frames_run=60,
            events=(_damage(3, amount=500.0, source="character:slot_1", damage_type="skill"),),
            team=[
                {
                    "character": {
                        "asset_key": "character:barbara",
                        "level": 90,
                        "constellation": 6,
                    },
                    "weapon": {
                        "asset_key": "weapon:prototype_amber",
                        "level": 90,
                        "refinement": 2,
                    },
                }
            ],
        )
    )
    return SQLiteAnalysisTemplateExecutor(db_path)


def test_catalog_lists_v1_templates(tmp_path) -> None:
    executor = SQLiteAnalysisTemplateExecutor(tmp_path / "missing.db")

    declarations = {item.template_id: item for item in executor.list_templates()}

    assert set(declarations) == {
        "session_metrics",
        "share_rows",
        "timeline_rows",
        "metric_summary",
    }
    session_metrics = declarations["session_metrics"]
    assert session_metrics.params[0].name == "session_ids"
    assert session_metrics.params[0].binding == ("session_group", "upstream_column")
    assert (session_metrics.output.columns[0].name, session_metrics.output.columns[0].type) == (
        "session_id",
        "string",
    )
    assert "total_damage" in {column.name for column in session_metrics.output.columns}


def test_session_metrics_aggregates_and_variant_columns(tmp_path) -> None:
    executor = _write_runs(tmp_path)

    result = executor.execute(
        "session_metrics",
        {"session_ids": ["run:1", "run:2"]},
    )

    columns = {column.name: idx for idx, column in enumerate(result.columns)}
    assert result.truncated is False
    assert len(result.rows) == 2
    first = result.rows[0]
    assert first[columns["session_id"]] == "run:1"
    assert first[columns["run_name"]] == "跑批 run:1"
    assert first[columns["frames_run"]] == 120
    assert first[columns["char_1_key"]] == "character:barbara"
    assert first[columns["char_1_level"]] == 80
    assert first[columns["char_1_constellation"]] == 2
    assert first[columns["weapon_1_key"]] == "weapon:thrilling_tales"
    assert first[columns["weapon_1_refinement"]] == 5
    assert first[columns["total_damage"]] == 1000.0
    assert first[columns["damage_count"]] == 2
    assert first[columns["highest_hit"]] == 700.0
    assert first[columns["average_hit"]] == 500.0
    assert first[columns["dps"]] == 500.0
    assert first[columns["total_healing"]] == 100.0
    assert first[columns["healing_count"]] == 1

    second = result.rows[1]
    assert second[columns["session_id"]] == "run:2"
    assert second[columns["weapon_1_refinement"]] == 2
    assert second[columns["dps"]] == 500.0


def test_session_metrics_frame_filter(tmp_path) -> None:
    executor = _write_runs(tmp_path)

    result = executor.execute(
        "session_metrics",
        {"session_ids": ["run:1"], "frame_min": 15, "frame_max": 20},
    )

    columns = {column.name: idx for idx, column in enumerate(result.columns)}
    row = result.rows[0]
    assert row[columns["total_damage"]] == 700.0
    assert row[columns["damage_count"]] == 1
    assert row[columns["total_healing"]] == 100.0


def test_share_rows_by_dimension(tmp_path) -> None:
    executor = _write_runs(tmp_path)

    by_source = executor.execute(
        "share_rows",
        {"session_ids": ["run:1"], "dimension": "source"},
    )
    by_kind = executor.execute(
        "share_rows",
        {"session_ids": ["run:1"], "dimension": "damage_kind"},
    )
    by_healing = executor.execute(
        "share_rows",
        {"session_ids": ["run:1"], "dimension": "healing_source"},
    )

    assert list(by_source.rows) == [("character:slot_1", 1000.0)]
    assert list(by_kind.rows) == [("burst", 700.0), ("skill", 300.0)]
    assert list(by_healing.rows) == [("character:slot_2", 100.0)]


def test_timeline_rows_points_segments_and_generic(tmp_path) -> None:
    executor = _write_runs(tmp_path)

    result = executor.execute("timeline_rows", {"session_ids": ["run:1"]})

    rows = {(row[1], row[2]): row for row in result.rows}
    assert rows[("Buff", 10)][3] == 90
    assert rows[("Buff", 10)][5] == "atk_buff"
    assert rows[("伤害", 10)][4] == 300.0
    assert rows[("治疗", 15)][4] == 100.0
    assert rows[("ACTION_STARTED", 5)][4] is None
    assert result.columns[2].name == "start_frame"


def test_timeline_rows_event_type_filter(tmp_path) -> None:
    executor = _write_runs(tmp_path)

    result = executor.execute(
        "timeline_rows",
        {"session_ids": ["run:1"], "event_types": ["DAMAGE_RESOLVED"]},
    )

    assert {row[1] for row in result.rows} == {"伤害"}
    assert len(result.rows) == 2


def test_metric_summary_consumes_relation_table(tmp_path) -> None:
    executor = SQLiteAnalysisTemplateExecutor(tmp_path / "results.db")
    table = RelationTable(
        columns=("total_damage", "dps", "highest_hit", "average_hit", "total_healing"),
        rows=(
            (1000.0, 500.0, 700.0, 500.0, 100.0),
            (500.0, 500.0, 300.0, 500.0, 0.0),
        ),
    )

    result = executor.execute("metric_summary", relations={"source": table})

    by_metric = {row[0]: row for row in result.rows}
    assert by_metric["total_damage"][1] == 750.0
    assert by_metric["total_damage"][2] == 1000.0
    assert by_metric["total_damage"][3] == 500.0
    assert by_metric["total_damage"][4] == pytest.approx(250.0)
    assert by_metric["total_damage"][5] == 1000.0
    assert by_metric["dps"][4] == 0.0
    assert by_metric["dps"][5] == 500.0


def test_execute_truncates_rows_over_cap(tmp_path, monkeypatch) -> None:
    import genshin_sim.infrastructure.results_sqlite.templates as templates_module

    monkeypatch.setattr(templates_module, "MAX_RESULT_ROWS", 3)
    executor = _write_runs(tmp_path)

    result = executor.execute(
        "timeline_rows",
        {"session_ids": ["run:1"]},
    )

    assert result.truncated is True
    assert len(result.rows) == 3


def test_execute_unknown_template_raises(tmp_path) -> None:
    executor = SQLiteAnalysisTemplateExecutor(tmp_path / "results.db")

    with pytest.raises(TemplateNotFoundError):
        executor.execute("no_such_template", {})


def test_execute_missing_database_returns_empty(tmp_path) -> None:
    executor = SQLiteAnalysisTemplateExecutor(tmp_path / "missing.db")

    result = executor.execute("session_metrics", {"session_ids": ["run:1"]})

    assert result.rows == ()
    assert result.truncated is False
