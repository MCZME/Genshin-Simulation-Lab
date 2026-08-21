"""芭芭拉战技影响点工厂规格快照。"""

from __future__ import annotations

from typing import cast

import pytest

from genshin_sim.content.characters.mondstadt.barbara.data import (
    BARBARA_ELEMENTAL_SKILL_ACTION_KEY,
    BARBARA_ELEMENTAL_SKILL_IMPACT_KEY,
    BARBARA_ELEMENTAL_SKILL_RING_CREATE_IMPACT_KEY,
    BARBARA_ELEMENTAL_SKILL_SELF_WET_IMPACT_KEY,
    BARBARA_RING_OBJECT_KEY,
)
from genshin_sim.core.actions import ActionOwnerRef, CandidateTargetRef
from genshin_sim.core.elements import AuraAmount
from genshin_sim.core.impacts import ActionImpactContext, ImpactKind
from genshin_sim.core.space import ACTIVE_CHARACTER_ENTITY_ID
from genshin_sim.core.systems.aura import AuraStrength


def test_barbara_elemental_skill_impact_factory_emits_damage_self_wet_and_ring(
    barbara_content_unit,
):
    # 与集成（tests/integration/content/barbara/test_elemental_skill.py::
    # test_barbara_elemental_skill_cast_resolves_damage_self_wet_and_ring）共存；
    # 本用例只锁定 impact 工厂的规格编译，最终数值由集成用例锁定。
    unit = barbara_content_unit(talent_levels={"normal_attack": 1, "elemental_skill": 1})
    damage_factory = unit.impact_factories[BARBARA_ELEMENTAL_SKILL_IMPACT_KEY]
    damage_requests = damage_factory.create_requests(
        ActionImpactContext(
            frame=44,
            impact_point_id="action:1:elemental_skill",
            source_instance_id=1,
            owner=ActionOwnerRef.character(1),
            action_key=BARBARA_ELEMENTAL_SKILL_ACTION_KEY,
            impact_key=BARBARA_ELEMENTAL_SKILL_IMPACT_KEY,
            target_refs=(CandidateTargetRef("target:target_1", "target_1"),),
        )
    )
    assert len(damage_requests) == 1
    assert damage_requests[0].kind is ImpactKind.DAMAGE
    assert damage_requests[0].damage_spec is not None
    spec = damage_requests[0].damage_spec
    assert spec.main_attack_tag == "元素战技"
    assert spec.scaling_terms[0].coefficient == pytest.approx(0.584)
    assert spec.elemental_strength is AuraStrength.WEAK
    assert spec.elemental_amount == AuraAmount.one()
    assert spec.icd_tag_key == "元素战技"
    assert spec.icd_sequence_key == "默认"
    assert spec.area is not None
    assert spec.area.shape == "球"
    assert spec.area.radius == pytest.approx(3.0)

    wet_factory = unit.impact_factories[BARBARA_ELEMENTAL_SKILL_SELF_WET_IMPACT_KEY]
    wet_requests = wet_factory.create_requests(
        ActionImpactContext(
            frame=5,
            impact_point_id="action:1:elemental_skill:wet",
            source_instance_id=1,
            owner=ActionOwnerRef.character(1),
            action_key=BARBARA_ELEMENTAL_SKILL_ACTION_KEY,
            impact_key=BARBARA_ELEMENTAL_SKILL_SELF_WET_IMPACT_KEY,
        )
    )
    assert len(wet_requests) == 1
    assert wet_requests[0].kind is ImpactKind.APPLY_AURA
    assert wet_requests[0].anchor_entity_id == ACTIVE_CHARACTER_ENTITY_ID
    assert wet_requests[0].elemental_application_spec is not None
    assert wet_requests[0].elemental_application_spec.element.value == "hydro"

    ring_factory = unit.impact_factories[BARBARA_ELEMENTAL_SKILL_RING_CREATE_IMPACT_KEY]
    ring_requests = ring_factory.create_requests(
        ActionImpactContext(
            frame=2,
            impact_point_id="action:1:elemental_skill:ring",
            source_instance_id=1,
            owner=ActionOwnerRef.character(1),
            action_key=BARBARA_ELEMENTAL_SKILL_ACTION_KEY,
            impact_key=BARBARA_ELEMENTAL_SKILL_RING_CREATE_IMPACT_KEY,
        )
    )
    assert len(ring_requests) == 1
    assert ring_requests[0].kind is ImpactKind.CREATE_ENTITY
    assert ring_requests[0].params["object_key"] == BARBARA_RING_OBJECT_KEY
    assert ring_requests[0].params["duration_frames"] == 907
    assert ring_requests[0].params["follow_entity_id"] == ACTIVE_CHARACTER_ENTITY_ID
    tick_schedules = cast(
        tuple[object, ...],
        ring_requests[0].params["tick_schedules"],
    )
    assert len(tick_schedules) == 2
