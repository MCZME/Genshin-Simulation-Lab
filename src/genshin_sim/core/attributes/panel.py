"""属性面板快照与差异发布。

属性系统是查询式解析器，所有影响属性的机制最终都经过解析器。面板同步器
在每帧机制结算完成后解析当前面板，与上次发布的面板比较，有差异才发布
``ATTRIBUTE_PANEL_CHANGED``，载荷只含变化字段（before/after 值 + after
``applied_terms``）。
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from genshin_sim.core.attributes.keys import PUBLIC_ATTRIBUTE_KEYS, AttributeKey
from genshin_sim.core.attributes.models import (
    AttributeQuery,
    AttributeSnapshotEntry,
    AttributeSubjectRef,
    TraceLevel,
)
from genshin_sim.core.attributes.resolver import AttributeResolver
from genshin_sim.core.events import EventType, GameEvent
from genshin_sim.core.events.payloads import AttributePanelChangedPayload
from genshin_sim.core.protocols import FrameUpdatable

_VALUE_TOLERANCE = 1e-9


class AttributePanelError(RuntimeError):
    """属性面板错误基类。"""


@dataclass(frozen=True, slots=True)
class AttributePanelChange:
    """面板中单个属性的变化证据。"""

    attribute_key: str
    before_value: float
    after_value: float
    after_terms: tuple[dict[str, object], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "attribute_key": self.attribute_key,
            "before_value": self.before_value,
            "after_value": self.after_value,
            "after_terms": tuple(self.after_terms),
        }


_PanelKey = tuple[str, str]


def resolve_panel(
    resolver: AttributeResolver,
    subject_refs: Iterable[AttributeSubjectRef],
    frame: int,
    keys: Iterable[AttributeKey] = PUBLIC_ATTRIBUTE_KEYS,
) -> dict[_PanelKey, AttributeSnapshotEntry]:
    """按公开属性集合解析每个主体的面板，返回 (entity_id, attribute_key) -> 条目。"""

    entries: dict[_PanelKey, AttributeSnapshotEntry] = {}
    for subject in subject_refs:
        snapshot = resolver.snapshot(
            snapshot_id=f"attributes:{subject.entity_id}:{frame}",
            queries=tuple(
                AttributeQuery(subject_ref=subject, attribute_key=key, frame=frame) for key in keys
            ),
            trace_level=TraceLevel.APPLIED,
        )
        for entry in snapshot.entries:
            entries[(subject.entity_id, entry.attribute_key.value)] = entry
    return entries


def panel_entries_to_dict(
    entries: Iterable[AttributeSnapshotEntry],
) -> dict[str, object]:
    """把面板条目序列化为 {attribute_key: {"value": ..., "applied_terms": [...]}}。"""

    return {
        entry.attribute_key.value: {
            "value": entry.value,
            "applied_terms": tuple(term.to_dict() for term in entry.applied_terms),
        }
        for entry in entries
    }


def attributes_provider_dict(
    resolver: AttributeResolver,
    subject_refs: Iterable[AttributeSubjectRef],
    frame: int,
    keys: Iterable[AttributeKey] = PUBLIC_ATTRIBUTE_KEYS,
) -> dict[str, object]:
    """导出 attributes 快照 provider 形状：{frame, subjects: {entity_id: {key: {...}}}}。"""

    subjects: dict[str, object] = {}
    for subject in subject_refs:
        snapshot = resolver.snapshot(
            snapshot_id=f"attributes:{subject.entity_id}:{frame}",
            queries=tuple(
                AttributeQuery(subject_ref=subject, attribute_key=key, frame=frame) for key in keys
            ),
            trace_level=TraceLevel.APPLIED,
        )
        subjects[subject.entity_id] = panel_entries_to_dict(snapshot.entries)
    return {"frame": frame, "subjects": subjects}


class AttributePanelSynchronizer(FrameUpdatable):
    """在机制结算后比较面板并发布差异事件。"""

    def __init__(
        self,
        resolver: AttributeResolver,
        subject_refs: Iterable[AttributeSubjectRef],
        keys: Iterable[AttributeKey] = PUBLIC_ATTRIBUTE_KEYS,
    ) -> None:
        self._resolver = resolver
        self._subject_refs = tuple(subject_refs)
        self._keys = tuple(keys)
        self._baseline: dict[_PanelKey, AttributeSnapshotEntry] = {}
        self._published: dict[_PanelKey, AttributeSnapshotEntry] = {}

    @property
    def subject_entity_ids(self) -> tuple[str, ...]:
        return tuple(subject.entity_id for subject in self._subject_refs)

    def capture_baseline(self, frame: int = 0) -> None:
        """在运行前捕获第 0 帧面板，作为首次差异比较的基线。"""

        self._baseline = resolve_panel(
            self._resolver,
            self._subject_refs,
            frame,
            self._keys,
        )
        self._published = dict(self._baseline)

    def update_frame(self, context: object, frame: int) -> None:
        events = getattr(context, "events", None)
        if events is None:
            return
        current = resolve_panel(self._resolver, self._subject_refs, frame, self._keys)
        by_subject: dict[str, list[AttributePanelChange]] = {
            subject.entity_id: [] for subject in self._subject_refs
        }
        subjects_by_entity_id = {subject.entity_id: subject for subject in self._subject_refs}
        for panel_key, entry in sorted(current.items()):
            subject = subjects_by_entity_id[panel_key[0]]
            previous = self._published.get(panel_key)
            if previous is None:
                baseline_entry = self._baseline.get(panel_key)
                if baseline_entry is None or _same_value(baseline_entry.value, entry.value):
                    self._published[panel_key] = entry
                    continue
                before_value = baseline_entry.value
            elif _same_value(previous.value, entry.value):
                continue
            else:
                before_value = previous.value
            by_subject[subject.entity_id].append(
                AttributePanelChange(
                    attribute_key=entry.attribute_key.value,
                    before_value=before_value,
                    after_value=entry.value,
                    after_terms=tuple(term.to_dict() for term in entry.applied_terms),
                )
            )
            self._published[panel_key] = entry
        for subject in self._subject_refs:
            changes = by_subject[subject.entity_id]
            if not changes:
                continue
            events.publish(
                GameEvent(
                    EventType.ATTRIBUTE_PANEL_CHANGED,
                    frame,
                    AttributePanelChangedPayload(
                        frame=frame,
                        subject_ref=subject.to_dict(),
                        changes=tuple(changes),
                    ),
                )
            )

    def is_idle(self) -> bool:
        return True


def _same_value(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=_VALUE_TOLERANCE)
