from __future__ import annotations

import pytest

from genshin_sim.core.impacts import ImpactDispatcher, ImpactKind, ImpactRequest


class RecordingImpactFactory:
    def __init__(self, *requests: ImpactRequest) -> None:
        self.requests = requests
        self.seen_requests: list[ImpactRequest] = []

    def create_impact_requests(self, request: ImpactRequest) -> tuple[ImpactRequest, ...]:
        self.seen_requests.append(request)
        return self.requests


def test_impact_dispatcher_dispatches_by_impact_key():
    seed = ImpactRequest(
        frame=10,
        kind=ImpactKind.DAMAGE,
        impact_key="character.test.skill.hit",
        owner_slot=1,
        action_key="keyboard.e",
    )
    damage_request = ImpactRequest(
        frame=10,
        kind=ImpactKind.DAMAGE,
        impact_key="generic.damage",
        owner_slot=1,
        action_key="keyboard.e",
        scaling_ref="skill.hit",
        tags=("skill",),
    )
    factory = RecordingImpactFactory(damage_request)
    dispatcher = ImpactDispatcher({"character.test.skill.hit": factory})

    requests = dispatcher.dispatch(seed)

    assert requests == (damage_request,)
    assert factory.seen_requests == [seed]


def test_impact_dispatcher_reports_missing_factory():
    dispatcher = ImpactDispatcher()
    request = ImpactRequest(
        frame=1,
        kind=ImpactKind.HEAL,
        impact_key="missing.impact",
        owner_slot=1,
    )

    with pytest.raises(KeyError, match="未注册 impact factory：missing.impact"):
        dispatcher.dispatch(request)
