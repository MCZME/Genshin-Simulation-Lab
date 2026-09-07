from __future__ import annotations

import pytest

from genshin_sim.core.attributes import (
    AttributeSubjectRef,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.contracts.intents import IntentEnvelope, IntentKind
from genshin_sim.core.contracts.phases import FramePhase
from genshin_sim.core.impacts.models import ImpactKind, ImpactRequest
from genshin_sim.core.simulation.intent_handlers import (
    BuffIntentHandler,
    CooldownIntentHandler,
    ImpactIntentHandler,
)
from genshin_sim.core.systems.buff.models import ApplyBuffRequest


def _envelope(kind: IntentKind, payload: object) -> IntentEnvelope:
    return IntentEnvelope(
        intent_id="intent.test",
        kind=kind,
        frame=1,
        phase=FramePhase.SETTLEMENT,
        payload=payload,
    )


class RecordingDispatcher:
    def __init__(self) -> None:
        self.requests: list[ImpactRequest] = []

    def dispatch_requests(
        self,
        context: object,
        requests: tuple[ImpactRequest, ...],
    ) -> None:
        del context
        self.requests.extend(requests)


def test_impact_handler_forwards_impact_request():
    dispatcher = RecordingDispatcher()
    request = ImpactRequest(
        frame=1,
        kind=ImpactKind.ENERGY,
        impact_key="impact.test",
        owner_slot=1,
    )

    ImpactIntentHandler(dispatcher).handle(None, _envelope(IntentKind.IMPACT, request))

    assert dispatcher.requests == [request]


def test_impact_handler_rejects_non_impact_payload():
    handler = ImpactIntentHandler(RecordingDispatcher())

    with pytest.raises(TypeError, match="ImpactRequest"):
        handler.handle(None, _envelope(IntentKind.IMPACT, {"not": "impact"}))


class RecordingBuffRuntime:
    def __init__(self) -> None:
        self.requests: list[ApplyBuffRequest] = []

    def apply(self, request: ApplyBuffRequest) -> None:
        self.requests.append(request)


def test_buff_handler_forwards_apply_buff_request():
    runtime = RecordingBuffRuntime()
    request = ApplyBuffRequest(
        request_id="buff.test",
        frame=1,
        order=0,
        definition_key="buff.definition",
        target_ref=AttributeSubjectRef.character("character:slot:1"),
        source_context=RuntimeSourceRef(
            RuntimeSourceKind.ACTION,
            "action.test",
            "impact.test",
        ),
        duration_frames=60,
    )

    BuffIntentHandler(runtime).handle(None, _envelope(IntentKind.BUFF, request))

    assert runtime.requests == [request]


def test_buff_handler_rejects_non_buff_payload():
    handler = BuffIntentHandler(RecordingBuffRuntime())

    with pytest.raises(TypeError, match="ApplyBuffRequest"):
        handler.handle(None, _envelope(IntentKind.BUFF, {"not": "buff"}))


def test_cooldown_handler_rejects_non_cooldown_payload():
    class RecordingCooldownRuntime:
        def mutate_batch(self, request: object) -> None:
            del request

    handler = CooldownIntentHandler(RecordingCooldownRuntime())

    with pytest.raises(TypeError, match="CooldownMutationBatchRequest"):
        handler.handle(None, _envelope(IntentKind.COOLDOWN, {"not": "cooldown"}))
