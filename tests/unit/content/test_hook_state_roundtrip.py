from __future__ import annotations

from dataclasses import dataclass, field

from genshin_sim.content import (
    HookDispatcher,
    HookResult,
    StatePatchIntentHandler,
    StatePatchRequest,
)
from genshin_sim.core.contracts.intents import IntentKind
from genshin_sim.core.contracts.phases import FramePhase
from genshin_sim.core.contracts.state_schema import (
    StateField,
    StateFieldType,
    StateSchema,
)
from genshin_sim.core.entity_states import CharacterRuntimeState, ContentStateMount
from genshin_sim.core.events import EmptyPayload, EventType, GameEvent
from genshin_sim.core.simulation.context import SimulationContext
from genshin_sim.core.simulation.intent_queue import IntentQueue
from genshin_sim.core.simulation.pipeline import FramePipeline
from genshin_sim.core.simulation.settlement import IntentSettlementRuntime
from genshin_sim.core.simulation.team import TeamRuntimeState


@dataclass
class ChargePatchHook:
    hook_key: str = "hook.test.charge"
    owner_ref: str = "character:slot_1"
    state_key: str = "character.test"
    subscriptions: tuple[str, ...] = ("FRAME_STARTED",)
    priority: int = 0
    calls: list[object] = field(default_factory=list)

    def handle(self, event: object, context: object) -> HookResult:
        del context
        self.calls.append(event)
        return HookResult(
            state_patches=(
                StatePatchRequest(
                    owner_ref="character:slot_1",
                    state_key="character.test",
                    fields={"stacks": 2},
                ),
            )
        )


def test_hook_emits_state_patch_settled_in_next_round():
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
    hook = ChargePatchHook()
    queue = IntentQueue()
    settlement_runtime = IntentSettlementRuntime(queue)
    settlement_runtime.register(
        IntentKind.STATE_PATCH,
        StatePatchIntentHandler(team_state),
    )
    pipeline = FramePipeline(settlement_runtime=settlement_runtime)
    pipeline.add(
        FramePhase.FACT_RESPONSE,
        "content_hooks",
        HookDispatcher((hook,), queue, team_state=team_state),
    )
    context = SimulationContext()
    context.events.publish(
        GameEvent(
            EventType.FRAME_STARTED,
            frame=1,
            payload=EmptyPayload(),
            record=True,
        )
    )

    pipeline.update_frame(context, frame=1)

    assert mount.get("stacks") == 2
    assert len(hook.calls) == 1
    assert [record.kind for record in settlement_runtime.records] == [IntentKind.STATE_PATCH]
    assert [record.round for record in settlement_runtime.records] == [1]
    assert settlement_runtime.records[0].status == "handled"
    assert context.settlement_round == 1
