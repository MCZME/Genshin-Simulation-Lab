"""伤害序列与治疗序列中间模型。

中间模型把事件流加工为稳定的原始数值序列，DPS、占比等指标都从序列派生，
不直接读事件。序列只承载原始数值，不携带折叠状态；时间以帧为原始单位，
秒为派生展示（帧 ÷ 60）。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from genshin_sim.analysis.processors.state_fold import RecordedEventLike


class SequenceError(RuntimeError):
    """中间序列加工错误基类。"""


@dataclass(frozen=True, slots=True)
class DamageSequenceEntry:
    """一次已结算伤害的原始序列记录。"""

    frame: int
    damage_id: str
    source_ref: str
    target_ref: str
    amount: float
    damage_kind: str
    event_ref: int

    def to_dict(self) -> dict[str, object]:
        return {
            "frame": self.frame,
            "damage_id": self.damage_id,
            "source_ref": self.source_ref,
            "target_ref": self.target_ref,
            "amount": self.amount,
            "damage_kind": self.damage_kind,
            "event_ref": self.event_ref,
        }


@dataclass(frozen=True, slots=True)
class HealingSequenceEntry:
    """一次已结算治疗的原始序列记录。"""

    frame: int
    healing_id: str
    source_ref: str
    target_ref: str
    amount: float
    healing_kind: str
    event_ref: int

    def to_dict(self) -> dict[str, object]:
        return {
            "frame": self.frame,
            "healing_id": self.healing_id,
            "source_ref": self.source_ref,
            "target_ref": self.target_ref,
            "amount": self.amount,
            "healing_kind": self.healing_kind,
            "event_ref": self.event_ref,
        }


def build_damage_sequence(
    events: Iterable[RecordedEventLike],
) -> tuple[DamageSequenceEntry, ...]:
    """从 ``DAMAGE_RESOLVED`` 事件构建伤害序列。"""

    entries: list[DamageSequenceEntry] = []
    for ordinal, event in enumerate(events):
        if event.event_type != "DAMAGE_RESOLVED":
            continue
        result = event.data.get("result")
        if not isinstance(result, dict):
            raise SequenceError("DAMAGE_RESOLVED 载荷缺少 result 映射")
        entries.append(
            DamageSequenceEntry(
                frame=event.frame,
                damage_id=str(result["request_id"]),
                source_ref=str(result["source_ref"]),
                target_ref=str(result["target_ref"]),
                amount=float(result["final_damage"]),
                damage_kind=str(result["damage_type"]),
                event_ref=ordinal,
            )
        )
    return tuple(entries)


def build_healing_sequence(
    events: Iterable[RecordedEventLike],
) -> tuple[HealingSequenceEntry, ...]:
    """从 ``HEALING_RESOLVED`` 事件构建治疗序列。"""

    entries: list[HealingSequenceEntry] = []
    for ordinal, event in enumerate(events):
        if event.event_type != "HEALING_RESOLVED":
            continue
        result = event.data.get("result")
        if not isinstance(result, dict):
            raise SequenceError("HEALING_RESOLVED 载荷缺少 result 映射")
        source_ref = result.get("source_ref")
        target_ref = result.get("target_ref")
        if not isinstance(source_ref, dict) or not isinstance(target_ref, dict):
            raise SequenceError("HEALING_RESOLVED source_ref/target_ref 必须是映射")
        entries.append(
            HealingSequenceEntry(
                frame=event.frame,
                healing_id=str(result["healing_id"]),
                source_ref=str(source_ref["entity_id"]),
                target_ref=str(target_ref["entity_id"]),
                amount=float(result["final_healing"]),
                healing_kind="healing",
                event_ref=ordinal,
            )
        )
    return tuple(entries)
