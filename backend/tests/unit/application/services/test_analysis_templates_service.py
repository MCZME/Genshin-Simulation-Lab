"""分析模板服务声明级校验单元测试。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

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
    AnalysisTemplatesService,
    TemplateNotFoundError,
    TemplateValidationError,
)


def _declaration() -> TemplateDeclaration:
    return TemplateDeclaration(
        template_id="session_metrics",
        display_name="每会话指标",
        params=(
            TemplateParam("session_ids", "string[]", True, ("session_group",)),
            TemplateParam("frame_min", "int", False, ("static", "config")),
        ),
        relations=(),
        output=TemplateOutput(
            columns=(TemplateColumn("session_id", "string"),),
        ),
    )


class _FakeExecutor:
    def __init__(self, *declarations: TemplateDeclaration) -> None:
        self._declarations = declarations
        self.calls: list[tuple[str, dict[str, Any], dict[str, RelationTable]]] = []

    def list_templates(self) -> tuple[TemplateDeclaration, ...]:
        return self._declarations

    def execute(
        self,
        template_id: str,
        params: Mapping[str, Any] | None = None,
        relations: Mapping[str, RelationTable] | None = None,
    ) -> TemplateResult:
        self.calls.append((template_id, dict(params or {}), dict(relations or {})))
        return TemplateResult(
            columns=(TemplateColumn("session_id", "string"),),
            rows=(),
            truncated=False,
        )


def test_execute_validates_required_params() -> None:
    executor = _FakeExecutor(_declaration())
    service = AnalysisTemplatesService(executor)

    with pytest.raises(TemplateValidationError, match="缺少必填参数"):
        service.execute("session_metrics", params={"frame_min": 0})


def test_execute_rejects_unknown_params_and_type_mismatch() -> None:
    executor = _FakeExecutor(_declaration())
    service = AnalysisTemplatesService(executor)

    with pytest.raises(TemplateValidationError, match="不支持参数"):
        service.execute("session_metrics", params={"session_ids": ["a"], "nope": 1})
    with pytest.raises(TemplateValidationError, match="类型不符"):
        service.execute(
            "session_metrics",
            params={"session_ids": ["a"], "frame_min": "0"},
        )


def test_execute_unknown_template_raises() -> None:
    service = AnalysisTemplatesService(_FakeExecutor(_declaration()))

    with pytest.raises(TemplateNotFoundError):
        service.execute("missing", params={"session_ids": ["a"]})


def test_execute_validates_relation_required_and_columns() -> None:
    declaration = TemplateDeclaration(
        template_id="metric_summary",
        display_name="指标汇总",
        params=(),
        relations=(
            TemplateRelation(
                "source",
                ("total_damage", "dps"),
                True,
            ),
        ),
        output=TemplateOutput(columns=(TemplateColumn("metric", "string"),)),
    )
    executor = _FakeExecutor(declaration)
    service = AnalysisTemplatesService(executor)

    with pytest.raises(TemplateValidationError, match="缺少必填关系输入"):
        service.execute("metric_summary")
    with pytest.raises(TemplateValidationError, match="缺少所需列"):
        service.execute(
            "metric_summary",
            relations={
                "source": RelationTable(
                    columns=("total_damage",),
                    rows=((1.0,),),
                )
            },
        )
    with pytest.raises(TemplateValidationError, match="不支持关系输入"):
        service.execute(
            "metric_summary",
            relations={"other": RelationTable(columns=("total_damage",), rows=((1.0,),))},
        )


def test_execute_delegates_to_executor_with_validated_inputs() -> None:
    executor = _FakeExecutor(_declaration())
    service = AnalysisTemplatesService(executor)

    result = service.execute(
        "session_metrics",
        params={"session_ids": ["a", "b"], "frame_min": 0},
    )

    assert result.rows == ()
    assert executor.calls == [
        (
            "session_metrics",
            {"session_ids": ["a", "b"], "frame_min": 0},
            {},
        )
    ]
