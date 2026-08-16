"""从中间序列派生的第一版摘要指标。

指标只消费伤害/治疗序列，不直接读事件；每个指标都带口径说明（定义字符串、
帧率、时间基准），避免不同口径误比较。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from genshin_sim.analysis.processors.sequences import (
    DamageSequenceEntry,
    HealingSequenceEntry,
)


class MetricsError(ValueError):
    """指标计算错误基类。"""


@dataclass(frozen=True, slots=True)
class MetricValue:
    """单个指标数值与口径说明。"""

    key: str
    value: float
    definition: str

    def to_dict(self) -> dict[str, object]:
        return {"key": self.key, "value": self.value, "definition": self.definition}


@dataclass(frozen=True, slots=True)
class ShareValue:
    """按分组统计的占比指标。"""

    group: str
    value: float
    definition: str

    def to_dict(self) -> dict[str, object]:
        return {"group": self.group, "value": self.value, "definition": self.definition}


@dataclass(frozen=True, slots=True)
class DamageMetrics:
    """整场伤害/治疗摘要指标。"""

    frames_run: int
    frames_per_second: int
    total_damage: MetricValue
    dps: MetricValue
    highest_hit: MetricValue
    average_hit: MetricValue
    damage_share_by_source: tuple[ShareValue, ...]
    damage_share_by_kind: tuple[ShareValue, ...]
    total_healing: MetricValue
    healing_share_by_source: tuple[ShareValue, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "frames_run": self.frames_run,
            "frames_per_second": self.frames_per_second,
            "total_damage": self.total_damage.to_dict(),
            "dps": self.dps.to_dict(),
            "highest_hit": self.highest_hit.to_dict(),
            "average_hit": self.average_hit.to_dict(),
            "damage_share_by_source": tuple(item.to_dict() for item in self.damage_share_by_source),
            "damage_share_by_kind": tuple(item.to_dict() for item in self.damage_share_by_kind),
            "total_healing": self.total_healing.to_dict(),
            "healing_share_by_source": tuple(
                item.to_dict() for item in self.healing_share_by_source
            ),
        }


def build_metrics(
    damage_sequence: tuple[DamageSequenceEntry, ...],
    healing_sequence: tuple[HealingSequenceEntry, ...],
    *,
    frames_run: int,
    frames_per_second: int = 60,
) -> DamageMetrics:
    """从伤害/治疗序列派生整场摘要指标。"""

    if isinstance(frames_run, bool) or not isinstance(frames_run, int) or frames_run < 0:
        raise MetricsError("frames_run 必须是非负整数")
    if (
        isinstance(frames_per_second, bool)
        or not isinstance(frames_per_second, int)
        or frames_per_second <= 0
    ):
        raise MetricsError("frames_per_second 必须是正整数")

    total_damage = sum(entry.amount for entry in damage_sequence)
    damage_count = len(damage_sequence)
    highest_hit = max((entry.amount for entry in damage_sequence), default=0.0)
    average_hit = total_damage / damage_count if damage_count else 0.0
    elapsed_seconds = frames_run / frames_per_second
    dps = total_damage / elapsed_seconds if elapsed_seconds > 0 else 0.0

    total_healing = sum(entry.amount for entry in healing_sequence)

    return DamageMetrics(
        frames_run=frames_run,
        frames_per_second=frames_per_second,
        total_damage=MetricValue(
            key="total_damage",
            value=total_damage,
            definition="total_damage = Σ damage_sequence.amount",
        ),
        dps=MetricValue(
            key="dps",
            value=dps,
            definition=("dps = total_damage / (frames_run / frames_per_second)，整场口径，帧转秒"),
        ),
        highest_hit=MetricValue(
            key="highest_hit",
            value=highest_hit,
            definition="highest_hit = max(damage_sequence.amount)",
        ),
        average_hit=MetricValue(
            key="average_hit",
            value=average_hit,
            definition="average_hit = total_damage / count(damage_sequence)",
        ),
        damage_share_by_source=_shares(
            total_damage,
            (entry.source_ref for entry in damage_sequence),
            (entry.amount for entry in damage_sequence),
            "damage_share = group_amount / total_damage",
        ),
        damage_share_by_kind=_shares(
            total_damage,
            (entry.damage_kind for entry in damage_sequence),
            (entry.amount for entry in damage_sequence),
            "damage_share = group_amount / total_damage",
        ),
        total_healing=MetricValue(
            key="total_healing",
            value=total_healing,
            definition="total_healing = Σ healing_sequence.amount",
        ),
        healing_share_by_source=_shares(
            total_healing,
            (entry.source_ref for entry in healing_sequence),
            (entry.amount for entry in healing_sequence),
            "healing_share = group_amount / total_healing",
        ),
    )


def _shares(
    total: float,
    groups: Iterable[str],
    amounts: Iterable[float],
    definition: str,
) -> tuple[ShareValue, ...]:
    grouped: dict[str, float] = {}
    for group, amount in zip(groups, amounts, strict=True):
        grouped[group] = grouped.get(group, 0.0) + amount
    if total <= 0:
        return ()
    return tuple(
        ShareValue(
            group=group,
            value=amount / total,
            definition=definition,
        )
        for group, amount in sorted(grouped.items())
    )
