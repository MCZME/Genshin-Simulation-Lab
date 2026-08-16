"""统一意图结算运行时。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from genshin_sim.core.contracts.intents import IntentEnvelope, IntentKind
from genshin_sim.core.protocols import FrameUpdatable
from genshin_sim.core.simulation.intent_queue import IntentQueue


class IntentSettlementError(Exception):
    """意图结算错误基类。"""


class DuplicateIntentHandlerError(IntentSettlementError, ValueError):
    """同一意图类型重复注册处理。"""


class FrameZeroIntentError(IntentSettlementError, ValueError):
    """第 0 帧不允许普通意图。"""


class IntentKindHandler(Protocol):
    def handle(self, context: object, intent: IntentEnvelope) -> None: ...


@dataclass(frozen=True, slots=True)
class IntentSettlementRecord:
    """一次意图结算记录。"""

    frame: int
    round: int
    intent_id: str
    kind: IntentKind
    status: str
    reason: str | None = None


class IntentSettlementRuntime(FrameUpdatable):
    """按意图类型分发的结算运行时。

    M1 阶段先落地队列与结算外壳：已注册类型交给对应处理，未注册类型记录
    为 ignored，不改变既有影响分发路径。
    """

    def __init__(self, queue: IntentQueue | None = None) -> None:
        self.queue = queue or IntentQueue()
        self._handlers: dict[IntentKind, IntentKindHandler] = {}
        self._records: list[IntentSettlementRecord] = []
        self._current_frame = 0

    @property
    def records(self) -> tuple[IntentSettlementRecord, ...]:
        return tuple(self._records)

    @property
    def current_frame(self) -> int:
        return self._current_frame

    def register(self, kind: IntentKind, handler: IntentKindHandler) -> None:
        if not isinstance(kind, IntentKind):
            raise TypeError("kind 必须是 IntentKind")
        if not hasattr(handler, "handle"):
            raise TypeError("handler 必须实现 handle")
        if kind in self._handlers:
            raise DuplicateIntentHandlerError(f"重复注册意图处理：{kind.value}")
        self._handlers[kind] = handler

    def has_handler(self, kind: IntentKind) -> bool:
        return kind in self._handlers

    def settle_pending(
        self,
        context: object,
        frame: int,
        *,
        round: int = 0,
    ) -> tuple[IntentEnvelope, ...]:
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            raise ValueError("frame 必须是非负整数")
        if isinstance(round, bool) or not isinstance(round, int) or round < 0:
            raise ValueError("round 必须是非负整数")
        batch = self.queue.drain_sorted()
        for intent in batch:
            if intent.frame == 0:
                raise FrameZeroIntentError(f"第 0 帧不接受普通意图：{intent.intent_id}")
            handler = self._handlers.get(intent.kind)
            if handler is None:
                self._records.append(
                    IntentSettlementRecord(
                        frame=frame,
                        round=round,
                        intent_id=intent.intent_id,
                        kind=intent.kind,
                        status="ignored",
                        reason="未注册该意图类型的处理",
                    )
                )
                continue
            handler.handle(context, intent)
            self._records.append(
                IntentSettlementRecord(
                    frame=frame,
                    round=round,
                    intent_id=intent.intent_id,
                    kind=intent.kind,
                    status="handled",
                )
            )
        return batch

    def update_frame(self, context: object, frame: int) -> None:
        self._current_frame = frame
        self.settle_pending(context, frame)

    def is_idle(self) -> bool:
        return self.queue.is_empty()
