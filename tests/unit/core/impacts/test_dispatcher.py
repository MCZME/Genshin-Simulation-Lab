from __future__ import annotations

import pytest

from genshin_sim.core.actions import ActionOwnerRef
from genshin_sim.core.impacts import (
    ActionImpactContext,
    ImpactDispatcher,
    ImpactKind,
    ImpactRequest,
)


class RecordingImpactFactory:
    def __init__(self, *requests: ImpactRequest) -> None:
        self.requests = requests
        self.seen_contexts: list[ActionImpactContext] = []

    def create_requests(self, context: ActionImpactContext) -> tuple[ImpactRequest, ...]:
        self.seen_contexts.append(context)
        return self.requests


def _context() -> ActionImpactContext:
    return ActionImpactContext(
        frame=10,
        impact_point_id="action:1:hit",
        source_instance_id=1,
        owner=ActionOwnerRef.character(1),
        action_key="character.test.skill",
        impact_key="character.test.skill.hit",
    )


def test_impact_dispatcher_dispatches_by_impact_key():
    damage_request = ImpactRequest(
        frame=10,
        kind=ImpactKind.DAMAGE,
        impact_key="generic.damage",
        owner_slot=1,
        action_key="character.test.skill",
        scaling_ref="skill.hit",
        tags=("skill",),
    )
    factory = RecordingImpactFactory(damage_request)
    dispatcher = ImpactDispatcher({"character.test.skill.hit": factory})
    context = _context()

    requests = dispatcher.dispatch(context)

    assert requests == (damage_request,)
    assert factory.seen_contexts == [context]


def test_impact_dispatcher_reports_missing_factory():
    dispatcher = ImpactDispatcher()
    context = _context()

    with pytest.raises(KeyError, match="未注册 impact factory：character.test.skill.hit"):
        dispatcher.dispatch(context)
