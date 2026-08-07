from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from genshin_sim.content import (
    HookContext,
    HookDispatcher,
    HookDispatcherError,
    HookResult,
    HookSubscriptionError,
    StatePatchRequest,
    UnsupportedHookOutputError,
)
from genshin_sim.core.contracts.intents import IntentKind
from genshin_sim.core.contracts.state_schema import (
    StateField,
    StateFieldType,
    StateSchema,
)
from genshin_sim.core.entity_states import CharacterRuntimeState, ContentStateMount
from genshin_sim.core.events import EmptyPayload, EventType, GameEvent
from genshin_sim.core.impacts.models import ImpactKind, ImpactRequest
from genshin_sim.core.simulation.context import SimulationContext
from genshin_sim.core.simulation.intent_queue import IntentQueue
from genshin_sim.core.simulation.team import TeamRuntimeState


@dataclass
class RecordingHook:
    hook_key: str
    subscriptions: tuple[str, ...]
    priority: int = 0
    result: HookResult = field(default_factory=HookResult)
    calls: list[tuple[object, object]] = field(default_factory=list)
    owner_ref: str = "character:slot_1"
    state_key: str = "character.test"

    def handle(self, event: object, context: object) -> HookResult:
        self.calls.append((event, context))
        return self.result


def _game_event(frame: int = 1) -> GameEvent:
    return GameEvent(
        EventType.FRAME_STARTED,
        frame=frame,
        payload=EmptyPayload(),
        record=True,
    )


def _impact_patch_queue(hook: RecordingHook) -> tuple[HookDispatcher, IntentQueue]:
    queue = IntentQueue()
    dispatcher = HookDispatcher((hook,), queue)
    return dispatcher, queue


def test_hook_dispatcher_rejects_unknown_subscription():
    hook = RecordingHook("hook.test", ("NOT_A_REAL_EVENT",))

    with pytest.raises(HookSubscriptionError, match="未知事件类型"):
        HookDispatcher((hook,), IntentQueue())


def test_hook_dispatcher_converts_impact_request_to_next_round_intent():
    request = ImpactRequest(
        frame=1,
        kind=ImpactKind.DAMAGE,
        impact_key="impact.test",
        owner_slot=1,
    )
    hook = RecordingHook(
        "hook.test",
        ("FRAME_STARTED",),
        result=HookResult(impact_requests=[request]),
    )
    dispatcher, queue = _impact_patch_queue(hook)
    context = SimulationContext()
    context.settlement_round = 2
    context.events.publish(_game_event())

    dispatcher.update_frame(context, frame=1)

    assert queue.pending_count == 1
    intent = queue.drain_sorted()[0]
    assert intent.kind is IntentKind.IMPACT
    assert intent.frame == 1
    assert intent.round == 3
    assert intent.source_ref == "hook.test"
    assert intent.payload is request


def test_hook_dispatcher_converts_state_patch_to_next_round_intent():
    patch = StatePatchRequest(
        owner_ref="character:slot_1",
        state_key="character.test",
        fields={"stacks": 1},
    )
    hook = RecordingHook(
        "hook.test",
        ("FRAME_STARTED",),
        result=HookResult(state_patches=[patch]),
    )
    dispatcher, queue = _impact_patch_queue(hook)
    context = SimulationContext()
    context.events.publish(_game_event())

    dispatcher.update_frame(context, frame=1)

    intent = queue.drain_sorted()[0]
    assert intent.kind is IntentKind.STATE_PATCH
    assert intent.round == 1
    assert intent.payload is patch


def test_hook_dispatcher_rejects_state_patch_for_foreign_owner():
    hook = RecordingHook(
        "hook.test",
        ("FRAME_STARTED",),
        result=HookResult(
            state_patches=[
                StatePatchRequest(
                    owner_ref="character:slot_2",
                    state_key="character.test",
                    fields={"stacks": 1},
                )
            ]
        ),
    )
    dispatcher, _ = _impact_patch_queue(hook)
    context = SimulationContext()
    context.events.publish(_game_event())

    with pytest.raises(HookDispatcherError, match="不能写宿主"):
        dispatcher.update_frame(context, frame=1)


def test_hook_dispatcher_processes_only_new_events_per_frame():
    hook = RecordingHook("hook.test", ("FRAME_STARTED",))
    dispatcher, queue = _impact_patch_queue(hook)
    context = SimulationContext()
    context.events.publish(_game_event(frame=1))

    dispatcher.update_frame(context, frame=1)
    dispatcher.update_frame(context, frame=1)

    assert len(hook.calls) == 1

    context.events.clear_frame_events()
    context.events.publish(_game_event(frame=2))
    dispatcher.update_frame(context, frame=2)

    assert len(hook.calls) == 2


def test_hook_dispatcher_invokes_hooks_in_priority_then_key_order():
    calls: list[str] = []

    class CallOrderHook:
        hook_key: str
        owner_ref = "character:slot_1"
        state_key = "character.test"
        subscriptions = ("FRAME_STARTED",)
        priority = 0

        def handle(self, event: object, context: object) -> HookResult:
            calls.append(self.hook_key)
            return HookResult()

    low = CallOrderHook()
    low.hook_key = "hook.low"
    low.priority = 10
    high = CallOrderHook()
    high.hook_key = "hook.high"
    high.priority = 1
    dispatcher = HookDispatcher((low, high), IntentQueue())
    context = SimulationContext()
    context.events.publish(_game_event())

    dispatcher.update_frame(context, frame=1)

    assert calls == ["hook.high", "hook.low"]


def test_hook_dispatcher_rejects_modifier_commands_as_unwired():
    hook = RecordingHook(
        "hook.test",
        ("FRAME_STARTED",),
        result=HookResult(modifier_commands=[object()]),
    )
    dispatcher, _ = _impact_patch_queue(hook)
    context = SimulationContext()
    context.events.publish(_game_event())

    with pytest.raises(UnsupportedHookOutputError, match="modifier_commands"):
        dispatcher.update_frame(context, frame=1)


def test_hook_dispatcher_rejects_wrong_impact_payload_type():
    hook = RecordingHook(
        "hook.test",
        ("FRAME_STARTED",),
        result=HookResult(impact_requests=[object()]),
    )
    dispatcher, _ = _impact_patch_queue(hook)
    context = SimulationContext()
    context.events.publish(_game_event())

    with pytest.raises(UnsupportedHookOutputError, match="ImpactRequest"):
        dispatcher.update_frame(context, frame=1)


def test_hook_context_exposes_read_only_state_view():
    mount = ContentStateMount(
        state_key="character.test",
        schema=StateSchema(
            owner_ref="character:slot_1",
            fields=(StateField(name="stacks", field_type=StateFieldType.INT, default=0),),
        ),
    )
    character = CharacterRuntimeState(
        slot=1,
        character_key="character:75",
        level=90,
        content_states={"character.test": mount},
    )
    team_state = TeamRuntimeState((character,))
    hook = RecordingHook(
        "hook.test",
        ("FRAME_STARTED",),
        owner_ref="character:slot_1",
    )
    dispatcher = HookDispatcher(
        (hook,),
        IntentQueue(),
        team_state=team_state,
    )
    context = SimulationContext()
    context.events.publish(_game_event())

    dispatcher.update_frame(context, frame=1)

    hook_context = hook.calls[0][1]
    assert isinstance(hook_context, HookContext)
    assert hook_context.state("character:slot_1") == {"stacks": 0}
