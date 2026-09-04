"""分析查询服务声明级结构校验单元测试。"""

from __future__ import annotations

import pytest

from genshin_sim.application.models import (
    AnalysisPlan,
    AnalysisPlanNode,
    AnalysisReadSchema,
    AnalysisSchemaColumn,
    AnalysisTableResult,
    AnalysisTableSchema,
)
from genshin_sim.application.services.analysis_query import (
    AnalysisPlanValidationError,
    AnalysisQueryService,
)


class _FakeExecutor:
    def __init__(self) -> None:
        self.calls: list[AnalysisPlan] = []

    def execute_plan(self, plan: AnalysisPlan) -> dict[str, AnalysisTableResult]:
        self.calls.append(plan)
        return {
            node_id: AnalysisTableResult(columns=(), rows=(), truncated=False)
            for node_id in plan.outputs
        }

    def read_schema(self) -> AnalysisReadSchema:
        return AnalysisReadSchema(
            tables=(
                AnalysisTableSchema(
                    name="simulation_runs",
                    columns=(
                        AnalysisSchemaColumn(
                            "state",
                            "string",
                            "运行状态",
                            "enum:run_state",
                        ),
                    ),
                ),
                AnalysisTableSchema(
                    name="simulation_events",
                    columns=(
                        AnalysisSchemaColumn(
                            "event_type",
                            "string",
                            "事件类型名",
                            "enum:event_type",
                        ),
                    ),
                ),
            ),
            event_types=(),
        )


def _service() -> tuple[AnalysisQueryService, _FakeExecutor]:
    executor = _FakeExecutor()
    return AnalysisQueryService(executor), executor


def test_execute_passes_structure_to_executor() -> None:
    service, executor = _service()
    plan = AnalysisPlan(
        session_ids=("a", "b"),
        nodes=(AnalysisPlanNode(id="runs1", kind="fetch", params={"source": "runs"}),),
        outputs=("runs1",),
    )

    tables = service.execute(plan)

    assert set(tables) == {"runs1"}
    assert executor.calls == [plan]


def test_execute_rejects_oversized_session_list() -> None:
    service, _ = _service()
    plan = AnalysisPlan(
        session_ids=tuple(f"s{i}" for i in range(1001)),
        nodes=(AnalysisPlanNode(id="runs1", kind="fetch", params={"source": "runs"}),),
        outputs=("runs1",),
    )

    with pytest.raises(AnalysisPlanValidationError, match="会话数超过上限"):
        service.execute(plan)


def test_execute_rejects_duplicate_node_ids() -> None:
    service, _ = _service()
    plan = AnalysisPlan(
        session_ids=("a",),
        nodes=(
            AnalysisPlanNode(id="runs1", kind="fetch", params={"source": "runs"}),
            AnalysisPlanNode(id="runs1", kind="fetch", params={"source": "runs"}),
        ),
        outputs=("runs1",),
    )

    with pytest.raises(AnalysisPlanValidationError) as exc_info:
        service.execute(plan)
    assert any("节点 id 重复" in item.get("reason", "") for item in exc_info.value.details)


def test_execute_rejects_illegal_node_id() -> None:
    service, _ = _service()
    plan = AnalysisPlan(
        session_ids=(),
        nodes=(AnalysisPlanNode(id='bad"node', kind="fetch", params={"source": "runs"}),),
        outputs=('bad"node',),
    )

    with pytest.raises(AnalysisPlanValidationError, match="不合法"):
        service.execute(plan)


def test_execute_rejects_unknown_or_empty_outputs() -> None:
    service, _ = _service()
    empty = AnalysisPlan(
        session_ids=(),
        nodes=(AnalysisPlanNode(id="runs1", kind="fetch", params={"source": "runs"}),),
        outputs=(),
    )
    with pytest.raises(AnalysisPlanValidationError, match="outputs 不能为空"):
        service.execute(empty)

    unknown = AnalysisPlan(
        session_ids=(),
        nodes=(AnalysisPlanNode(id="runs1", kind="fetch", params={"source": "runs"}),),
        outputs=("ghost",),
    )
    with pytest.raises(AnalysisPlanValidationError) as exc_info:
        service.execute(unknown)
    details = list(exc_info.value.details)
    assert any(item.get("node_id") == "ghost" for item in details)


def test_read_schema_exposes_full_catalog() -> None:
    service, _ = _service()

    schema = service.read_schema()

    runs = next(table for table in schema.tables if table.name == "simulation_runs")
    assert {column.name: column.value_kind for column in runs.columns}["state"] == (
        "enum:run_state"
    )
    events_table = next(table for table in schema.tables if table.name == "simulation_events")
    assert {column.name: column.value_kind for column in events_table.columns}["event_type"] == (
        "enum:event_type"
    )
    names = {item.name for item in schema.event_types}
    assert "DAMAGE_RESOLVED" in names
    assert "TEAM_SWITCHED" in names
    assert "ATTRIBUTE_PANEL_CHANGED" in names
    damage = next(item for item in schema.event_types if item.name == "DAMAGE_RESOLVED")
    assert {field.path for field in damage.fields} == {
        "result.final_damage",
        "result.source_ref",
        "result.source_ref.entity_id",
        "result.formula_key",
        "result.main_attack_tag",
        "result.element",
    }
    element_field = next(field for field in damage.fields if field.path == "result.element")
    assert element_field.value_kind == "enum:element"
    empty_fields = next(item for item in schema.event_types if item.name == "TEAM_SWITCHED")
    assert empty_fields.fields == ()
    tree = schema.snapshot_tree
    assert tree is not None
    assert tree.kind == "object"
    leaves = {path: node for path, node in _walk_paths(tree) if node.kind == "scalar"}
    assert (
        leaves[("root", "team", "character", "asset_key")].default_name_template == "char_{0}_key"
    )
    assert leaves[("root", "team", "character", "asset_key")].value_kind == ("asset:characters")
    assert (
        leaves[("root", "team", "weapon", "refinement")].default_name_template
        == "weapon_{0}_refinement"
    )
    assert (
        leaves[("root", "team", "artifacts", "stats", "crit_rate")].default_name_template
        == "artifact_{0}_crit_rate"
    )
    assert leaves[("root", "team", "artifacts", "stats", "crit_rate")].type == "float"
    assert (
        leaves[
            ("root", "scene", "targets", "target", "resistance", "physical")
        ].default_name_template
        == "target_{0}_res_physical"
    )
    assert (
        leaves[("root", "scene", "targets", "target", "resistance", "physical")].value_kind
        == "enum:element"
    )
    assert leaves[("root", "meta", "name")].default_name == "meta_name"
    team = next(node for path, node in _walk_paths(tree) if path == ("root", "team"))
    assert team.kind == "list"
    # 列表节点不枚举位置：children 是元素结构，不应出现数字键子节点。
    assert all(not child.key.isdigit() for child in team.children)


def _walk_paths(node, prefix=()):
    path = prefix + (node.key,)
    yield path, node
    for child in node.children:
        yield from _walk_paths(child, path)
