from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import pytest

from genshin_sim.content.state_container import (
    StateContainerNotFoundError,
    StatePatchError,
    StatePatchIntentHandler,
    StatePatchRequest,
    resolve_mount,
)
from genshin_sim.core.contracts.intents import IntentEnvelope, IntentKind
from genshin_sim.core.contracts.phases import FramePhase
from genshin_sim.core.contracts.state_schema import (
    StateField,
    StateFieldType,
    StateSchema,
)
from genshin_sim.core.entity_states import CharacterRuntimeState, ContentStateMount
from genshin_sim.core.simulation.context import SimulationContext
from genshin_sim.core.simulation.team import TeamRuntimeState


def _schema(owner_ref: str = "character:slot_1") -> StateSchema:
    return StateSchema(
        owner_ref=owner_ref,
        fields=(
            StateField(
                name="stacks",
                field_type=StateFieldType.INT,
                default=0,
                non_negative=True,
                max_value=3,
            ),
            StateField(name="active", field_type=StateFieldType.BOOL, default=False),
        ),
    )


def _team_state_with_mount(
    *,
    owner_ref: str = "character:slot_1",
    state_key: str = "character.test",
) -> tuple[TeamRuntimeState, ContentStateMount]:
    mount = ContentStateMount(state_key=state_key, schema=_schema(owner_ref))
    character = CharacterRuntimeState(
        slot=1,
        character_key="character:75",
        level=90,
        content_states={state_key: mount},
    )
    return TeamRuntimeState((character,)), mount


@dataclass(frozen=True, slots=True)
class _FakeSpaceRuntime:
    team_state: TeamRuntimeState


def test_state_patch_request_validates_owner_ref_state_key_and_fields():
    with pytest.raises(StatePatchError, match="owner_ref"):
        StatePatchRequest(owner_ref="", fields={}, state_key="character.test")
    with pytest.raises(StatePatchError, match="state_key"):
        StatePatchRequest(owner_ref="character:slot_1", fields={}, state_key="")
    with pytest.raises(StatePatchError, match="字段名"):
        StatePatchRequest(
            owner_ref="character:slot_1",
            fields={"": 1},
            state_key="character.test",
        )

    bad_fields: Any = {"stacks": (1, 2)}
    with pytest.raises(TypeError, match="fields.stacks"):
        StatePatchRequest(
            owner_ref="character:slot_1",
            fields=bad_fields,
            state_key="character.test",
        )


def test_resolve_mount_returns_host_mount():
    team_state, mount = _team_state_with_mount()
    context = SimulationContext()
    context.space_runtime = cast(Any, _FakeSpaceRuntime(team_state))

    assert resolve_mount(context, slot=1, state_key="character.test") is mount


def test_resolve_mount_raises_without_space_runtime():
    with pytest.raises(StateContainerNotFoundError, match="战场空间运行态"):
        resolve_mount(SimulationContext(), slot=1, state_key="character.test")


def test_state_patch_intent_handler_forwards_to_team_mount():
    team_state, mount = _team_state_with_mount()
    handler = StatePatchIntentHandler(team_state)
    intent = IntentEnvelope(
        intent_id="patch:1",
        kind=IntentKind.STATE_PATCH,
        frame=1,
        phase=FramePhase.SETTLEMENT,
        payload=StatePatchRequest(
            owner_ref="character:slot_1",
            state_key="character.test",
            fields={"stacks": 2, "active": True},
        ),
    )

    handler.handle(object(), intent)

    assert mount.get("stacks") == 2
    assert mount.get("active") is True


def test_state_patch_intent_handler_wraps_validation_error():
    team_state, _mount = _team_state_with_mount()
    handler = StatePatchIntentHandler(team_state)
    intent = IntentEnvelope(
        intent_id="patch:bad",
        kind=IntentKind.STATE_PATCH,
        frame=1,
        phase=FramePhase.SETTLEMENT,
        payload=StatePatchRequest(
            owner_ref="character:slot_1",
            state_key="character.test",
            fields={"stacks": 5},
        ),
    )

    with pytest.raises(StatePatchError, match="不能超过"):
        handler.handle(object(), intent)


def test_state_patch_intent_handler_rejects_wrong_payload_type():
    team_state, _mount = _team_state_with_mount()
    handler = StatePatchIntentHandler(team_state)
    intent = IntentEnvelope(
        intent_id="patch:bad",
        kind=IntentKind.STATE_PATCH,
        frame=1,
        phase=FramePhase.SETTLEMENT,
        payload=object(),
    )

    with pytest.raises(TypeError, match="StatePatchRequest"):
        handler.handle(object(), intent)
