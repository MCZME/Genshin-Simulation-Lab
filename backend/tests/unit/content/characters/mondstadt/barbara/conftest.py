"""芭芭拉单元测试共享 fixture：解释器运行上下文与输入释放辅助。"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from genshin_sim.assets.models import TalentScalingEntry
from genshin_sim.content.characters.mondstadt.barbara.actions import (
    BarbaraActionInterpreter,
    create_barbara_actions,
)
from genshin_sim.content.characters.mondstadt.barbara.content import (
    create_barbara_content_unit,
)
from genshin_sim.content.characters.mondstadt.barbara.data import (
    BARBARA_CHARACTER_HANDLER_KEY,
)
from genshin_sim.content.definitions.content_unit import ContentUnit
from genshin_sim.content.generic.chain_state import chain_state_schema
from genshin_sim.content.registries import CharacterContentUnitRequest
from genshin_sim.content.state_container import StatePatchRequest
from genshin_sim.core.actions import (
    ActionInterpretationContext,
    ActionInterpretationTrigger,
    ActionOwnerRef,
    InputPhysicalState,
    InputSessionView,
)
from genshin_sim.core.entity_states import CharacterRuntimeState, ContentStateMount
from genshin_sim.core.simulation import SimulationContext
from genshin_sim.core.simulation.intent_queue import IntentQueue
from genshin_sim.core.simulation.team import TeamRuntimeState
from genshin_sim.core.space import (
    ACTIVE_CHARACTER_ENTITY_ID,
    Space,
    SpatialEntity,
    SpatialEntityKind,
    Vector3,
)
from genshin_sim.core.space.runtime import SpaceRuntime
from tests.helpers.barbara_assets import barbara_scaling_entries

BarbaraRuntime = tuple[SimulationContext, ContentStateMount, IntentQueue]


@pytest.fixture
def barbara_actions() -> dict[str, object]:
    return {action.action_key: action for action in create_barbara_actions()}


@pytest.fixture
def barbara_content_unit() -> Callable[..., ContentUnit]:
    def _build(
        *,
        talent_levels: dict[str, int] | None = None,
        talent_scalings: tuple[TalentScalingEntry, ...] | None = None,
    ) -> ContentUnit:
        return create_barbara_content_unit(
            CharacterContentUnitRequest(
                handler_key=BARBARA_CHARACTER_HANDLER_KEY,
                character_key="character:10000014",
                slot=1,
                talent_levels=talent_levels or {"normal_attack": 1},
                talent_scalings=talent_scalings or barbara_scaling_entries(),
            )
        )

    return _build


@pytest.fixture
def barbara_runtime() -> Callable[..., BarbaraRuntime]:
    def _build(*, height: float = 0.0) -> BarbaraRuntime:
        context = SimulationContext()
        mount = ContentStateMount(
            state_key=BARBARA_CHARACTER_HANDLER_KEY,
            schema=chain_state_schema("character:slot_1"),
        )
        character = CharacterRuntimeState(
            slot=1,
            character_key="character:75",
            level=90,
            content_states={BARBARA_CHARACTER_HANDLER_KEY: mount},
        )
        team_state = TeamRuntimeState((character,))
        context.space_runtime = SpaceRuntime(
            space=Space(
                (
                    SpatialEntity(
                        ACTIVE_CHARACTER_ENTITY_ID,
                        SpatialEntityKind.ACTIVE_CHARACTER,
                        position=Vector3(0.0, height, 0.0),
                        active_slot=1,
                    ),
                )
            ),
            team_state=team_state,
        )
        queue = IntentQueue()
        context.register_system(queue)
        return context, mount, queue

    return _build


@pytest.fixture
def barbara_session_view() -> Callable[..., InputSessionView]:
    def _build(*, frame: int, key: str = "mouse.left") -> InputSessionView:
        return InputSessionView(
            session_id=frame + 1,
            key=key,
            trigger=ActionInterpretationTrigger.RELEASE,
            press_frame=frame,
            current_frame=frame,
            held_frames=0,
            physical_state=InputPhysicalState.RELEASED,
            owner=ActionOwnerRef.character(1),
            release_frame=frame,
        )

    return _build


@pytest.fixture
def barbara_release(
    barbara_runtime: Callable[..., BarbaraRuntime],
    barbara_session_view: Callable[..., InputSessionView],
) -> Callable[..., object]:
    def _release(
        interpreter: BarbaraActionInterpreter,
        key: str,
        *,
        frame: int,
        runtime: BarbaraRuntime | None = None,
    ):
        context, mount, queue = runtime or barbara_runtime()
        result = interpreter.interpret(
            ActionInterpretationContext(simulation=context),
            barbara_session_view(frame=frame, key=key),
        )
        for intent in queue.drain_sorted():
            assert isinstance(intent.payload, StatePatchRequest)
            assert intent.payload.state_key == BARBARA_CHARACTER_HANDLER_KEY
            mount.apply_patch(intent.payload.fields)
        return result

    return _release
