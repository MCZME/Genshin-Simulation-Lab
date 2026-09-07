from __future__ import annotations

import pytest

from genshin_sim.core.contracts.intents import IntentEnvelope, IntentKind
from genshin_sim.core.contracts.phases import FramePhase
from genshin_sim.core.simulation.intent_queue import (
    DuplicateIntentError,
    IntentQueue,
)


def _intent(intent_id: str, frame: int, phase: FramePhase, round: int = 0) -> IntentEnvelope:
    return IntentEnvelope(
        intent_id=intent_id,
        kind=IntentKind.IMPACT,
        frame=frame,
        phase=phase,
        round=round,
    )


def test_queue_drains_in_stable_sort_order():
    queue = IntentQueue()
    queue.enqueue(_intent("b", frame=1, phase=FramePhase.SETTLEMENT, round=1))
    queue.enqueue(_intent("a", frame=1, phase=FramePhase.SETTLEMENT))
    queue.enqueue(_intent("c", frame=2, phase=FramePhase.SETTLEMENT))

    assert [item.intent_id for item in queue.drain_sorted()] == ["a", "b", "c"]
    assert queue.is_empty()


def test_queue_rejects_duplicate_intent_id():
    queue = IntentQueue()
    queue.enqueue(_intent("a", frame=1, phase=FramePhase.SETTLEMENT))

    with pytest.raises(DuplicateIntentError, match="a"):
        queue.enqueue(_intent("a", frame=2, phase=FramePhase.SETTLEMENT))


def test_queue_enqueue_many_and_pending_count():
    queue = IntentQueue()
    queue.enqueue_many(
        (
            _intent("a", frame=1, phase=FramePhase.SETTLEMENT),
            _intent("b", frame=1, phase=FramePhase.FACT_RESPONSE),
        )
    )

    assert queue.pending_count == 2
    assert not queue.is_empty()
