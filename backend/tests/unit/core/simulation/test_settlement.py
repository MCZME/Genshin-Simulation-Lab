from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from genshin_sim.core.contracts.intents import IntentEnvelope, IntentKind
from genshin_sim.core.contracts.phases import FramePhase
from genshin_sim.core.simulation.settlement import (
    DuplicateIntentHandlerError,
    FrameZeroIntentError,
    IntentSettlementRuntime,
)


@dataclass
class RecordingHandler:
    handled: list[IntentEnvelope] = field(default_factory=list)

    def handle(self, context: object, intent: IntentEnvelope) -> None:
        del context
        self.handled.append(intent)


def _intent(intent_id: str, kind: IntentKind, frame: int = 1) -> IntentEnvelope:
    return IntentEnvelope(
        intent_id=intent_id,
        kind=kind,
        frame=frame,
        phase=FramePhase.SETTLEMENT,
    )


def test_settlement_dispatches_registered_kind_in_order():
    runtime = IntentSettlementRuntime()
    handler = RecordingHandler()
    runtime.register(IntentKind.IMPACT, handler)
    runtime.queue.enqueue_many(
        (
            _intent("b", IntentKind.IMPACT),
            _intent("a", IntentKind.IMPACT),
        )
    )

    settled = runtime.settle_pending(None, frame=1)

    assert [item.intent_id for item in settled] == ["a", "b"]
    assert [item.intent_id for item in handler.handled] == ["a", "b"]
    assert [record.status for record in runtime.records] == ["handled", "handled"]


def test_settlement_records_unknown_kind_as_ignored():
    runtime = IntentSettlementRuntime()
    runtime.queue.enqueue(_intent("a", IntentKind.BUFF))

    settled = runtime.settle_pending(None, frame=1)

    assert len(settled) == 1
    assert runtime.records[0].status == "ignored"
    assert runtime.records[0].reason is not None
    assert "未注册" in runtime.records[0].reason


def test_settlement_rejects_duplicate_handler():
    runtime = IntentSettlementRuntime()
    handler = RecordingHandler()
    runtime.register(IntentKind.IMPACT, handler)

    with pytest.raises(DuplicateIntentHandlerError, match="impact"):
        runtime.register(IntentKind.IMPACT, RecordingHandler())


def test_settlement_update_frame_drains_queue_and_tracks_idle():
    runtime = IntentSettlementRuntime()
    runtime.queue.enqueue(_intent("a", IntentKind.IMPACT))
    assert not runtime.is_idle()

    runtime.update_frame(None, frame=1)

    assert runtime.current_frame == 1
    assert runtime.is_idle()
    assert len(runtime.records) == 1


def test_settlement_rejects_frame_zero_intent():
    runtime = IntentSettlementRuntime()
    runtime.queue.enqueue(_intent("a", IntentKind.IMPACT, frame=0))

    with pytest.raises(FrameZeroIntentError, match="第 0 帧"):
        runtime.settle_pending(None, frame=1)
