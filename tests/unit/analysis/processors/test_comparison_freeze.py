from __future__ import annotations

from genshin_sim.analysis.processors.comparison import ComparisonColumn, ComparisonResult


def test_comparison_column_fields_are_frozen():
    column = ComparisonColumn(label="a", results=())

    assert tuple(column.to_dict()) == ("label", "results")


def test_comparison_result_fields_are_frozen():
    result = ComparisonResult(columns=())

    assert tuple(result.to_dict()) == ("columns",)
