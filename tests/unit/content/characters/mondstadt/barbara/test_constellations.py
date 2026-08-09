"""芭芭拉命座内容单元：C4 去重逻辑与效果请求校验。"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from genshin_sim.content.characters.mondstadt.barbara import (
    BARBARA_CONSTELLATION_C3_HANDLER_KEY,
    create_barbara_constellation_c1,
    create_barbara_constellation_c3,
    create_barbara_constellation_c4,
)
from genshin_sim.content.characters.mondstadt.barbara import (
    hooks as barbara_hooks_module,
)
from genshin_sim.content.characters.mondstadt.barbara.data import (
    BARBARA_CHARGED_ATTACK_ACTION_KEY,
)
from genshin_sim.content.characters.mondstadt.barbara.hooks import (
    BarbaraConstellationC4EnergyHook,
)
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.impacts import ImpactKind, ImpactRequest
from tests.helpers import barbara as barbara_helpers


class _FakeEvent:
    def __init__(self, frame: int, payload: object | None = None) -> None:
        self.frame = frame
        self.payload = payload


class _FakeResult:
    def __init__(
        self,
        request_id: str,
        source_ref: AttributeSubjectRef,
        target_ref: AttributeSubjectRef,
    ) -> None:
        self.request_id = request_id
        self.source_ref = source_ref
        self.target_ref = target_ref


class _FakePayload:
    def __init__(self, result: object) -> None:
        self.result = result


class _FakeImpactRequest:
    def __init__(
        self,
        *,
        action_key: str,
        source_impact_point_id: str | None,
        request_id: str,
    ) -> None:
        self.action_key = action_key
        self.source_impact_point_id = source_impact_point_id
        self.request_id = request_id


class _FakeRecord:
    def __init__(self, result: object, impact_request: object) -> None:
        self.result = result
        self.impact_request = impact_request


class _FakeHandler:
    def __init__(self, records: Sequence[object]) -> None:
        self.records = tuple(records)


class _FakeSimulation:
    def __init__(self, handler: _FakeHandler) -> None:
        self._handler = handler

    def get_system(self, system_type: type[object]) -> object | None:
        del system_type
        return self._handler


class _FakeContext:
    def __init__(self, handler: _FakeHandler) -> None:
        self.simulation = _FakeSimulation(handler)


def test_c4_dedup_targets_and_caps_at_five(monkeypatch):
    monkeypatch.setattr(barbara_hooks_module, "DamageRequestHandler", _FakeHandler)
    hook = BarbaraConstellationC4EnergyHook(
        owner_ref="character:slot_1",
        slot=1,
        amount=1.0,
        max_per_action=5,
    )
    records: list[_FakeRecord] = []
    for index in range(6):
        result = _FakeResult(
            request_id=f"req-{index}",
            source_ref=AttributeSubjectRef.character("character:slot_1"),
            target_ref=AttributeSubjectRef.target(f"target:t{index}"),
        )
        impact = _FakeImpactRequest(
            action_key=BARBARA_CHARGED_ATTACK_ACTION_KEY,
            source_impact_point_id="action:7:character.barbara.charged_attack.hit",
            request_id="impact-1",
        )
        records.append(_FakeRecord(result, impact))
    context = _FakeContext(_FakeHandler(records))

    requests = []
    for index in range(6):
        event = _FakeEvent(55, _FakePayload(records[index].result))
        for request in hook.handle(event, context).impact_requests:
            assert isinstance(request, ImpactRequest)
            requests.append(request)

    assert len(requests) == 5
    assert all(request.kind is ImpactKind.ENERGY for request in requests)
    assert all(request.target_refs == ("character:slot_1",) for request in requests)
    target_ids = [request.request_id.rsplit(":", 1)[-1] for request in requests]
    assert target_ids == ["t0", "t1", "t2", "t3", "t4"]


def test_constellation_factories_reject_invalid_params_and_owner():
    with pytest.raises(ContentUnitValidationError, match="components"):
        create_barbara_constellation_c1(barbara_helpers.c1_request(params={"components": []}))
    with pytest.raises(ContentUnitValidationError, match="数值必须为正数"):
        create_barbara_constellation_c1(
            barbara_helpers.c1_request(
                params={
                    "components": [
                        {"kind": "numeric", "values": [0.0]},
                        {"kind": "numeric", "values": [1.0]},
                    ]
                }
            )
        )
    with pytest.raises(ContentUnitValidationError, match="必须是整数"):
        create_barbara_constellation_c3(
            barbara_helpers.effect_request(
                BARBARA_CONSTELLATION_C3_HANDLER_KEY,
                effect_key="character:10000014:constellation:c3",
                params={
                    "components": [
                        {"kind": "numeric", "values": [2.5]},
                        {"kind": "numeric", "values": [15.0]},
                    ]
                },
            )
        )
    with pytest.raises(ContentUnitValidationError, match="芭芭拉资产"):
        create_barbara_constellation_c4(barbara_helpers.c4_request(owner_key="character:99999999"))
