from __future__ import annotations

from dataclasses import dataclass

import pytest

from genshin_sim.core.contracts.intents import IntentEnvelope, IntentKind
from genshin_sim.core.contracts.phases import PHASE_ORDER, FramePhase
from genshin_sim.core.simulation import SimulationContext
from genshin_sim.core.simulation.pipeline import (
    DuplicatePhaseHandlerError,
    FramePipeline,
    FramePipelineRoundLimitError,
)
from genshin_sim.core.simulation.settlement import IntentSettlementRuntime


@dataclass
class RecordingUpdatable:
    calls: list[str]
    key: str
    idle: bool = True

    def update_frame(self, context: SimulationContext, frame: int) -> None:
        del context
        self.calls.append(f"{self.key}:{frame}")

    def is_idle(self) -> bool:
        return self.idle


def test_pipeline_updates_handlers_in_phase_order():
    calls: list[str] = []
    pipeline = FramePipeline()
    action = RecordingUpdatable(calls, "action")
    time_advance = RecordingUpdatable(calls, "time_advance")
    snapshot = RecordingUpdatable(calls, "snapshot")
    pipeline.add(FramePhase.ACTION_ADVANCE, "action", action)
    pipeline.add(FramePhase.TIME_ADVANCE, "time_advance", time_advance)
    pipeline.add(FramePhase.SNAPSHOT, "snapshot", snapshot)
    context = SimulationContext()

    pipeline.update_frame(context, frame=5)

    assert calls == ["time_advance:5", "action:5", "snapshot:5"]


def test_pipeline_updatables_preserve_phase_and_registration_order():
    calls: list[str] = []
    pipeline = FramePipeline()
    first = RecordingUpdatable(calls, "first")
    second = RecordingUpdatable(calls, "second")
    pipeline.add(FramePhase.TIME_ADVANCE, "first", first)
    pipeline.add(FramePhase.TIME_ADVANCE, "second", second)

    assert pipeline.updatables == (first, second)


def test_pipeline_rejects_duplicate_phase_key():
    pipeline = FramePipeline()
    handler = RecordingUpdatable([], "handler")
    pipeline.add(FramePhase.TIME_ADVANCE, "duplicate", handler)

    with pytest.raises(DuplicatePhaseHandlerError, match="duplicate"):
        pipeline.add(FramePhase.TIME_ADVANCE, "duplicate", handler)


def test_pipeline_is_idle_includes_intent_queue():
    runtime = IntentSettlementRuntime()
    pipeline = FramePipeline(settlement_runtime=runtime)
    assert pipeline.is_idle()

    runtime.queue.enqueue(
        IntentEnvelope(
            intent_id="a",
            kind=IntentKind.IMPACT,
            frame=1,
            phase=FramePhase.SETTLEMENT,
        )
    )
    assert not pipeline.is_idle()

    pipeline.update_frame(SimulationContext(), frame=1)
    assert pipeline.is_idle()


def test_pipeline_phase_order_matches_contract():
    phases = [binding.phase for binding in FramePipeline().bindings]
    assert phases == []
    assert PHASE_ORDER == (
        FramePhase.TIME_ADVANCE,
        FramePhase.INPUT_INTERPRET,
        FramePhase.ACTION_ADVANCE,
        FramePhase.SETTLEMENT,
        FramePhase.FACT_RESPONSE,
        FramePhase.SNAPSHOT,
    )


def _settlement_intent(intent_id: str, frame: int = 1) -> IntentEnvelope:
    return IntentEnvelope(
        intent_id=intent_id,
        kind=IntentKind.IMPACT,
        frame=frame,
        phase=FramePhase.SETTLEMENT,
    )


def test_pipeline_settles_same_frame_rounds():
    runtime = IntentSettlementRuntime()
    pipeline = FramePipeline(settlement_runtime=runtime)
    fact_calls: list[int] = []

    class FollowUpHandler:
        def __init__(self) -> None:
            self.calls = 0

        def handle(self, context: object, intent: IntentEnvelope) -> None:
            del context
            self.calls += 1
            if self.calls == 1:
                runtime.queue.enqueue(_settlement_intent("follow-up", frame=intent.frame))

    class RecordingFactResponse:
        def update_frame(self, context: SimulationContext, frame: int) -> None:
            del context
            fact_calls.append(frame)

        def is_idle(self) -> bool:
            return True

    runtime.register(IntentKind.IMPACT, FollowUpHandler())
    pipeline.add(FramePhase.FACT_RESPONSE, "recording_hook", RecordingFactResponse())
    runtime.queue.enqueue(_settlement_intent("first"))

    pipeline.update_frame(SimulationContext(), frame=1)

    assert [record.round for record in runtime.records] == [0, 1]
    assert [record.status for record in runtime.records] == ["handled", "handled"]
    assert fact_calls == [1, 1]


def test_pipeline_raises_when_settlement_rounds_exceed_limit():
    runtime = IntentSettlementRuntime()
    pipeline = FramePipeline(settlement_runtime=runtime)
    counter = 0

    class UnboundedHandler:
        def handle(self, context: object, intent: IntentEnvelope) -> None:
            del context
            nonlocal counter
            counter += 1
            runtime.queue.enqueue(_settlement_intent(f"next-{counter}"))

    runtime.register(IntentKind.IMPACT, UnboundedHandler())
    runtime.queue.enqueue(_settlement_intent("first"))

    with pytest.raises(FramePipelineRoundLimitError, match="上限"):
        pipeline.update_frame(SimulationContext(), frame=1)
