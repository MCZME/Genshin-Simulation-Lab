"""对比并置模型。

对比的核心定义：把满足条件查询到的数据并置呈现。任何数据都可对比——跨运行、
同运行不同帧、不同实体、不同领域。本模块只提供"多查询结果并置"的通用能力，
不做领域假设；具体对比方案（对齐规则、聚合口径、展示形式）在此基础上增加限制。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from genshin_sim.analysis.processors.query import (
    EventQuery,
    EventQueryResult,
    RunReader,
    StateQuery,
    StateQueryResult,
    query_events,
    query_state,
)


class ComparisonError(ValueError):
    """对比模型错误基类。"""


@dataclass(frozen=True, slots=True)
class ComparisonQuery:
    """一次参与对比的查询及其展示标签。"""

    label: str
    query: StateQuery | EventQuery


@dataclass(frozen=True, slots=True)
class ComparisonColumn:
    """一次查询的结果列。"""

    label: str
    results: tuple[StateQueryResult | EventQueryResult, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "results": tuple(result.to_dict() for result in self.results),
        }


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    """多个查询结果的并置。"""

    columns: tuple[ComparisonColumn, ...]

    def to_dict(self) -> dict[str, object]:
        return {"columns": tuple(column.to_dict() for column in self.columns)}


def build_comparison(
    reader: RunReader,
    queries: Sequence[ComparisonQuery],
) -> ComparisonResult:
    """执行多个查询并把结果按列并置。"""

    if not queries:
        raise ComparisonError("对比至少需要一个查询")
    labels: set[str] = set()
    columns: list[ComparisonColumn] = []
    for item in queries:
        if not isinstance(item.label, str) or not item.label.strip():
            raise ComparisonError("对比查询标签必须是非空字符串")
        if item.label in labels:
            raise ComparisonError(f"对比查询标签重复：{item.label}")
        labels.add(item.label)
        if isinstance(item.query, StateQuery):
            results = query_state(reader, item.query)
        elif isinstance(item.query, EventQuery):
            results = query_events(reader, item.query)
        else:
            raise ComparisonError("对比查询必须是 StateQuery 或 EventQuery")
        columns.append(ComparisonColumn(item.label, results))
    return ComparisonResult(tuple(columns))
