"""统一意图队列。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from genshin_sim.core.contracts.intents import IntentEnvelope


class IntentQueueError(Exception):
    """意图队列错误基类。"""


class DuplicateIntentError(IntentQueueError, ValueError):
    """同一队列中出现重复 intent_id。"""


@dataclass(slots=True)
class IntentQueue:
    """按稳定排序键收集与派发意图的队列。"""

    _pending: list[IntentEnvelope] = field(default_factory=list)

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def enqueue(self, intent: IntentEnvelope) -> None:
        if not isinstance(intent, IntentEnvelope):
            raise TypeError("intent 必须是 IntentEnvelope")
        if any(item.intent_id == intent.intent_id for item in self._pending):
            raise DuplicateIntentError(f"重复 intent_id：{intent.intent_id}")
        self._pending.append(intent)

    def enqueue_many(self, intents: Iterable[IntentEnvelope]) -> None:
        for intent in intents:
            self.enqueue(intent)

    def drain_sorted(self) -> tuple[IntentEnvelope, ...]:
        """按 frame -> phase -> round -> source -> id 排序后清空返回。"""

        batch = tuple(sorted(self._pending, key=lambda item: item.sort_key()))
        self._pending.clear()
        return batch

    def is_empty(self) -> bool:
        return not self._pending
