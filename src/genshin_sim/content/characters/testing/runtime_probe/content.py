from __future__ import annotations

from genshin_sim.content.characters.testing.runtime_probe.actions import (
    RuntimeProbeActionInterpreter,
    create_runtime_probe_action,
)
from genshin_sim.content.characters.testing.runtime_probe.constants import (
    RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
    RUNTIME_PROBE_IMPACT_KEY,
)
from genshin_sim.content.characters.testing.runtime_probe.impacts import (
    RuntimeProbeImpactFactory,
)
from genshin_sim.content.characters.testing.runtime_probe.state import RuntimeProbeState
from genshin_sim.content.models import ContentRuntimeContribution
from genshin_sim.content.registry import CharacterRuntimeRequest, HandlerRegistry


def create_runtime_probe_content(
    request: CharacterRuntimeRequest,
) -> ContentRuntimeContribution:
    return ContentRuntimeContribution(
        owner_type="character",
        owner_key=request.character_key,
        handler_key=request.handler_key,
        slot=request.slot,
        action_interpreter=RuntimeProbeActionInterpreter(),
        actions=(create_runtime_probe_action(),),
        state_extension=RuntimeProbeState(),
        impact_factories={RUNTIME_PROBE_IMPACT_KEY: RuntimeProbeImpactFactory()},
        metadata={"purpose": "testing_runtime_probe"},
    )


def register(registry: HandlerRegistry) -> HandlerRegistry:
    registry.register_character_factory(
        RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
        create_runtime_probe_content,
    )
    return registry
