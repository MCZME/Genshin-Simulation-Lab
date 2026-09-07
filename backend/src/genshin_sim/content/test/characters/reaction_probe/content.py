"""反应探针测试角色内容单元编译入口。"""

from __future__ import annotations

from collections.abc import Mapping

from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
)
from genshin_sim.content.registries import CharacterContentUnitRequest
from genshin_sim.content.test.characters.reaction_probe.actions import (
    ReactionProbeActionInterpreter,
    create_probe_action,
)
from genshin_sim.content.test.characters.reaction_probe.constants import (
    REACTION_PROBE_CONTENT_VERSION,
    TEST_A_ACTION_KEY,
    TEST_A_DISPLAY_NAME_BY_KEY,
    TEST_A_ELEMENT_BY_KEY,
    TEST_A_HANDLER_KEY,
    TEST_A_IMPACT_KEY,
    TEST_B_ACTION_KEY,
    TEST_B_DISPLAY_NAME_BY_KEY,
    TEST_B_ELEMENT_BY_KEY,
    TEST_B_HANDLER_KEY,
    TEST_B_IMPACT_KEY,
)
from genshin_sim.content.test.characters.reaction_probe.impacts import (
    ReactionProbeImpactFactory,
)
from genshin_sim.core.elements import Element


def create_test_a_content_unit(request: CharacterContentUnitRequest) -> ContentUnit:
    """test_a 内容单元工厂（火/冰/草/岩命中探针）。"""

    return _create_reaction_probe_content_unit(
        request,
        handler_key=TEST_A_HANDLER_KEY,
        action_key=TEST_A_ACTION_KEY,
        impact_key=TEST_A_IMPACT_KEY,
        element_by_key=TEST_A_ELEMENT_BY_KEY,
        display_name_by_key=TEST_A_DISPLAY_NAME_BY_KEY,
        purpose="testing_reaction_probe_a",
    )


def create_test_b_content_unit(request: CharacterContentUnitRequest) -> ContentUnit:
    """test_b 内容单元工厂（水/雷/风/物理命中探针）。"""

    return _create_reaction_probe_content_unit(
        request,
        handler_key=TEST_B_HANDLER_KEY,
        action_key=TEST_B_ACTION_KEY,
        impact_key=TEST_B_IMPACT_KEY,
        element_by_key=TEST_B_ELEMENT_BY_KEY,
        display_name_by_key=TEST_B_DISPLAY_NAME_BY_KEY,
        purpose="testing_reaction_probe_b",
    )


def _create_reaction_probe_content_unit(
    request: CharacterContentUnitRequest,
    *,
    handler_key: str,
    action_key: str,
    impact_key: str,
    element_by_key: Mapping[str, Element],
    display_name_by_key: Mapping[str, str],
    purpose: str,
) -> ContentUnit:
    return ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key=request.character_key,
        handler_key=request.handler_key,
        version=REACTION_PROBE_CONTENT_VERSION,
        slot=request.slot,
        action_interpreter=ReactionProbeActionInterpreter(
            handler_key=handler_key,
            action_key=action_key,
            element_by_key=element_by_key,
            display_name_by_key=display_name_by_key,
        ),
        actions=(create_probe_action(action_key, (impact_key,)),),
        impact_factories={impact_key: ReactionProbeImpactFactory(handler_key=handler_key)},
        metadata={"purpose": purpose},
    )
