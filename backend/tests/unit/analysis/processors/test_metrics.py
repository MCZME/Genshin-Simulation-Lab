from __future__ import annotations

import pytest

from genshin_sim.analysis.processors.metrics import (
    MetricsError,
    build_metrics,
)
from genshin_sim.analysis.processors.sequences import (
    DamageSequenceEntry,
    HealingSequenceEntry,
)


def _damage(
    *entries: tuple[int, str, str, str, float, str],
) -> tuple[DamageSequenceEntry, ...]:
    return tuple(
        DamageSequenceEntry(
            frame=frame,
            damage_id=damage_id,
            source_ref=source_ref,
            target_ref=target_ref,
            amount=amount,
            damage_kind=kind,
            event_ref=ordinal,
        )
        for ordinal, (frame, damage_id, source_ref, target_ref, amount, kind) in enumerate(entries)
    )


def _healing(
    *entries: tuple[int, str, str, str, float],
) -> tuple[HealingSequenceEntry, ...]:
    return tuple(
        HealingSequenceEntry(
            frame=frame,
            healing_id=healing_id,
            source_ref=source_ref,
            target_ref=target_ref,
            amount=amount,
            healing_kind="healing",
            event_ref=ordinal,
        )
        for ordinal, (frame, healing_id, source_ref, target_ref, amount) in enumerate(entries)
    )


def test_build_metrics_computes_totals_dps_and_shares():
    damage = _damage(
        (1, "d:1", "character:slot_1", "target:target_1", 300.0, "skill"),
        (2, "d:2", "character:slot_2", "target:target_1", 500.0, "burst"),
        (3, "d:3", "character:slot_1", "target:target_1", 200.0, "skill"),
    )
    healing = _healing(
        (2, "h:1", "character:slot_2", "character:slot_1", 120.0),
    )

    metrics = build_metrics(damage, healing, frames_run=600)

    assert metrics.total_damage.value == 1000.0
    assert metrics.dps.value == pytest.approx(100.0)
    assert metrics.highest_hit.value == 500.0
    assert metrics.average_hit.value == pytest.approx(1000.0 / 3)
    assert metrics.total_healing.value == 120.0
    assert [(item.group, item.value) for item in metrics.damage_share_by_source] == [
        ("character:slot_1", pytest.approx(0.5)),
        ("character:slot_2", pytest.approx(0.5)),
    ]
    assert [(item.group, item.value) for item in metrics.damage_share_by_kind] == [
        ("burst", pytest.approx(0.5)),
        ("skill", pytest.approx(0.5)),
    ]
    assert [(item.group, item.value) for item in metrics.healing_share_by_source] == [
        ("character:slot_2", 1.0)
    ]
    assert metrics.dps.definition.startswith("dps = ")


def test_build_metrics_handles_empty_sequences_and_zero_frames():
    metrics = build_metrics((), (), frames_run=0)

    assert metrics.total_damage.value == 0.0
    assert metrics.dps.value == 0.0
    assert metrics.highest_hit.value == 0.0
    assert metrics.average_hit.value == 0.0
    assert metrics.damage_share_by_source == ()
    assert metrics.damage_share_by_kind == ()
    assert metrics.healing_share_by_source == ()


def test_build_metrics_validates_frames():
    with pytest.raises(MetricsError, match="frames_run"):
        build_metrics((), (), frames_run=-1)
    with pytest.raises(MetricsError, match="frames_per_second"):
        build_metrics((), (), frames_run=60, frames_per_second=0)
