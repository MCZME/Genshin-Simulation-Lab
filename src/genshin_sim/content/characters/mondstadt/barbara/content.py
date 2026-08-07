from __future__ import annotations

from genshin_sim.content.characters.mondstadt.barbara.actions import (
    BarbaraActionInterpreter,
    create_barbara_actions,
)
from genshin_sim.content.characters.mondstadt.barbara.constants import (
    BARBARA_HIT_IMPACT_KEYS,
)
from genshin_sim.content.characters.mondstadt.barbara.impacts import (
    BarbaraActionImpactFactory,
)
from genshin_sim.content.characters.mondstadt.barbara.state import (
    barbara_state_schema,
)
from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
)
from genshin_sim.content.registries import CharacterContentUnitRequest

VERSION = "dev-action"


def create_barbara_content_unit(
    request: CharacterContentUnitRequest,
) -> ContentUnit:
    """新模型内容单元工厂（芭芭拉动作状态机）。"""

    impact_factory = BarbaraActionImpactFactory()
    owner_ref = f"character:slot_{request.slot}"
    return ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key=request.character_key,
        handler_key=request.handler_key,
        version=VERSION,
        slot=request.slot,
        action_interpreter=BarbaraActionInterpreter(),
        actions=create_barbara_actions(),
        state_schema=barbara_state_schema(owner_ref),
        impact_factories={impact_key: impact_factory for impact_key in BARBARA_HIT_IMPACT_KEYS},
        metadata={"purpose": "barbara_action_state_machine"},
    )
