from __future__ import annotations

from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
)
from genshin_sim.content.registries import CharacterContentUnitRequest
from genshin_sim.content.test.characters.runtime_probe.actions import (
    RuntimeProbeActionInterpreter,
    create_runtime_probe_action,
)
from genshin_sim.content.test.characters.runtime_probe.constants import (
    RUNTIME_PROBE_CONTENT_VERSION,
    RUNTIME_PROBE_IMPACT_KEY,
)
from genshin_sim.content.test.characters.runtime_probe.impacts import (
    RuntimeProbeImpactFactory,
)


def create_runtime_probe_content_unit(
    request: CharacterContentUnitRequest,
) -> ContentUnit:
    """新模型内容单元工厂（运行时探针）。"""

    return ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key=request.character_key,
        handler_key=request.handler_key,
        version=RUNTIME_PROBE_CONTENT_VERSION,
        slot=request.slot,
        action_interpreter=RuntimeProbeActionInterpreter(),
        actions=(create_runtime_probe_action(),),
        impact_factories={RUNTIME_PROBE_IMPACT_KEY: RuntimeProbeImpactFactory()},
        metadata={"purpose": "testing_runtime_probe"},
    )
