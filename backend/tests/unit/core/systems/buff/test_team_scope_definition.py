# 单一关注点：队伍作用域 Buff 定义（target kinds 声明与词条接受）。
from __future__ import annotations

import pytest

from genshin_sim.core.attributes import STAT_ATK_TOTAL, AttributeSubjectKind, ModifierStage
from tests.helpers.buff import (
    make_attribute_buff_definition,
    make_marker_buff_definition,
)

TEAM = AttributeSubjectKind.TEAM
ACTIVE_CHARACTER = AttributeSubjectKind.ACTIVE_CHARACTER


@pytest.mark.parametrize("kind", (TEAM, ACTIVE_CHARACTER), ids=("team", "active_character"))
def test_team_scope_kinds_are_accepted_in_definitions(kind: AttributeSubjectKind):
    """队伍作用域 kind 与 character / target 一视同仁：marker 与词条定义都不设额外门槛。"""

    marker_definition = make_marker_buff_definition(
        kind=kind,
        definition_key=f"buff.test.team_scope_marker.{kind.value}",
        conflict_key=f"test.conflict.team_scope_marker.{kind.value}",
        tags=frozenset({"test_team_buff"}),
    )
    modifier_definition = make_attribute_buff_definition(
        kind=kind,
        definition_key=f"buff.test.team_scope_with_modifiers.{kind.value}",
        conflict_key=f"test.conflict.team_scope_with_modifiers.{kind.value}",
        term_key="atk_bonus",
        target_key=STAT_ATK_TOTAL,
        stage=ModifierStage.PERCENT_ADD,
    )

    assert marker_definition.target_kinds == frozenset({kind})
    assert marker_definition.marker_only is True
    assert marker_definition.attribute_modifiers == ()
    assert modifier_definition.target_kinds == frozenset({kind})
    assert modifier_definition.marker_only is False
    assert len(modifier_definition.attribute_modifiers) == 1
