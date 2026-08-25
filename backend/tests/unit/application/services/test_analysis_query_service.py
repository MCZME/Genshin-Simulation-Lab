"""分析查询服务声明级结构校验单元测试。"""

from __future__ import annotations

import pytest

from genshin_sim.application.models import (
    AnalysisPlan,
    AnalysisPlanNode,
    AnalysisReadSchema,
    AnalysisTableResult,
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
        return AnalysisReadSchema(tables=(), event_types=())


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

    names = {item.name for item in schema.event_types}
    assert "DAMAGE_RESOLVED" in names
    assert "TEAM_SWITCHED" in names
    assert "ATTRIBUTE_PANEL_CHANGED" in names
    damage = next(item for item in schema.event_types if item.name == "DAMAGE_RESOLVED")
    assert {field.path for field in damage.fields} == {
        "result.final_damage",
        "result.source_ref",
        "result.source_ref.entity_id",
        "result.damage_type",
        "result.element",
    }
    empty_fields = next(
        item for item in schema.event_types if item.name == "TEAM_SWITCHED"
    )
    assert empty_fields.fields == ()
    paths = {item.path: item for item in schema.snapshot_paths}
    assert paths["team.0.character.asset_key"].default_name == "char_1_key"
    assert paths["team.0.character.asset_key"].segments == ("队伍", "槽位 1", "角色", "资产")
    assert paths["team.3.weapon.refinement"].default_name == "weapon_4_refinement"
    assert paths["scene.targets.0.resistance.physical"].default_name == "target_1_res_physical"
