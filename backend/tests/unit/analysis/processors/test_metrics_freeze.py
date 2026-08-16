from __future__ import annotations

from genshin_sim.analysis.processors.metrics import DamageMetrics, MetricValue, ShareValue


def test_metric_value_fields_are_frozen():
    value = MetricValue(key="total_damage", value=1000.0, definition="d")

    assert tuple(value.to_dict()) == ("key", "value", "definition")


def test_share_value_fields_are_frozen():
    value = ShareValue(group="character:slot_1", value=0.5, definition="d")

    assert tuple(value.to_dict()) == ("group", "value", "definition")


def test_damage_metrics_fields_are_frozen():
    metrics = DamageMetrics(
        frames_run=600,
        frames_per_second=60,
        total_damage=MetricValue("total_damage", 1000.0, "d"),
        dps=MetricValue("dps", 100.0, "d"),
        highest_hit=MetricValue("highest_hit", 500.0, "d"),
        average_hit=MetricValue("average_hit", 333.0, "d"),
        damage_share_by_source=(),
        damage_share_by_kind=(),
        total_healing=MetricValue("total_healing", 120.0, "d"),
        healing_share_by_source=(),
    )

    assert tuple(metrics.to_dict()) == (
        "frames_run",
        "frames_per_second",
        "total_damage",
        "dps",
        "highest_hit",
        "average_hit",
        "damage_share_by_source",
        "damage_share_by_kind",
        "total_healing",
        "healing_share_by_source",
    )
