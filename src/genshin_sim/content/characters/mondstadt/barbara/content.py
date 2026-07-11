from __future__ import annotations

from genshin_sim.content.characters.mondstadt.barbara.actions import (
    BarbaraActionInterpreter,
    create_barbara_actions,
)
from genshin_sim.content.characters.mondstadt.barbara.constants import (
    BARBARA_CHARACTER_HANDLER_KEY,
    BARBARA_HIT_IMPACT_KEYS,
)
from genshin_sim.content.characters.mondstadt.barbara.impacts import (
    BarbaraActionImpactFactory,
)
from genshin_sim.content.characters.mondstadt.barbara.state import BarbaraState
from genshin_sim.content.models import ContentRuntimeContribution
from genshin_sim.content.registry import CharacterRuntimeRequest, HandlerRegistry


def create_barbara_content(
    request: CharacterRuntimeRequest,
) -> ContentRuntimeContribution:
    impact_factory = BarbaraActionImpactFactory()
    return ContentRuntimeContribution(
        owner_type="character",
        owner_key=request.character_key,
        handler_key=request.handler_key,
        slot=request.slot,
        action_interpreter=BarbaraActionInterpreter(),
        actions=create_barbara_actions(),
        state_extension=BarbaraState(),
        impact_factories={impact_key: impact_factory for impact_key in BARBARA_HIT_IMPACT_KEYS},
        metadata={"purpose": "barbara_action_state_machine"},
    )


def register(registry: HandlerRegistry) -> HandlerRegistry:
    registry.register_character_factory(
        BARBARA_CHARACTER_HANDLER_KEY,
        create_barbara_content,
    )
    return registry
