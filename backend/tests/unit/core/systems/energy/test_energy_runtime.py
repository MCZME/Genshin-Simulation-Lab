from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import pytest

from genshin_sim.core.attributes import AttributeQuery, AttributeResolveOptions, AttributeSubjectRef
from genshin_sim.core.entity_states import CharacterRuntimeState
from genshin_sim.core.events import EnergyPickupSettledPayload, EventEngine, EventType
from genshin_sim.core.simulation import TeamRuntimeState
from genshin_sim.core.systems.energy import (
    CharacterEnergyProfile,
    CharacterEnergyStore,
    DrainEnergyRequest,
    DuplicateEnergyRequestError,
    EnergyElement,
    EnergyPickupKind,
    EnergyReentrancyError,
    EnergyRuntime,
    EnergyTransitQueue,
    InvalidEnergyAttributeError,
    RestoreEnergyRequest,
    SpawnEnergyPickupRequest,
    SpendBurstEnergyRequest,
    UnsupportedEnergyResourceError,
)


@dataclass
class _Resolution:
    final_value: float


class _Resolver:
    def __init__(self, values: dict[str, float], *, fail_entity_id: str | None = None) -> None:
        self.values = values
        self.fail_entity_id = fail_entity_id

    def resolve(
        self,
        query: AttributeQuery,
        *,
        options: AttributeResolveOptions | None = None,
    ) -> _Resolution:
        del options
        if query.subject_ref.entity_id == self.fail_entity_id:
            raise RuntimeError("injected failure")
        return _Resolution(self.values.get(query.subject_ref.entity_id, 0.0))


def _rig(
    elements: tuple[EnergyElement, ...],
    capacities: tuple[float, ...],
    recharge: tuple[float, ...] = (),
) -> tuple[EnergyRuntime, TeamRuntimeState, EventEngine]:
    characters = tuple(
        CharacterRuntimeState(slot=index, character_key=f"character:{index}", level=90)
        for index in range(1, len(elements) + 1)
    )
    team = TeamRuntimeState(characters)
    entries = []
    values = {}
    for character, element, capacity in zip(characters, elements, capacities, strict=True):
        ref = AttributeSubjectRef.character(character.combat_entity_id)
        entries.append(
            (
                CharacterEnergyProfile(ref, character.character_key, element, capacity),
                character.energy,
            )
        )
        values[character.combat_entity_id] = recharge[character.slot - 1] if recharge else 0.0
    events = EventEngine()
    runtime = EnergyRuntime(
        _Resolver(values), team, CharacterEnergyStore(entries), EnergyTransitQueue(), events
    )
    return runtime, team, events


def _ref(slot: int) -> AttributeSubjectRef:
    return AttributeSubjectRef.character(f"character:slot_{slot}")


def test_four_person_pyro_particle_matches_golden_case_a():
    runtime, _team, events = _rig(
        (EnergyElement.PYRO, EnergyElement.PYRO, EnergyElement.HYDRO, EnergyElement.CRYO),
        (80, 80, 80, 0),
        (0, 0, 0.5, 0),
    )

    runtime.spawn_pickup(
        SpawnEnergyPickupRequest(
            "pickup:a", 10, EnergyPickupKind.PARTICLE, EnergyElement.PYRO, 1, 0
        )
    )
    runtime.update_frame(None, 10)

    assert runtime.get_current_energy(_ref(1)) == 3.0
    assert runtime.get_current_energy(_ref(2)) == pytest.approx(1.8)
    assert runtime.get_current_energy(_ref(3)) == pytest.approx(0.9)
    assert runtime.get_current_energy(_ref(4)) == 0.0
    settled = [
        event
        for event in events.frame_events
        if event.event_type is EventType.ENERGY_PICKUP_SETTLED
    ]
    assert len(settled) == 1
    payload = cast(EnergyPickupSettledPayload, settled[0].payload)
    assert payload.result.recipients[3].status.value == "no_elemental_energy_resource"


def test_three_person_clear_orb_matches_golden_case_b():
    runtime, _team, _events = _rig(
        (EnergyElement.PYRO, EnergyElement.HYDRO, EnergyElement.CRYO), (80, 80, 80)
    )
    runtime.spawn_pickup(
        SpawnEnergyPickupRequest("pickup:b", 0, EnergyPickupKind.ORB, EnergyElement.CLEAR, 1, 0)
    )
    runtime.update_frame(None, 0)

    assert runtime.get_current_energy(_ref(1)) == 6.0
    assert runtime.get_current_energy(_ref(2)) == pytest.approx(4.2)
    assert runtime.get_current_energy(_ref(3)) == pytest.approx(4.2)


def test_one_person_pickup_uses_active_multiplier_without_background_rule():
    runtime, _team, _events = _rig((EnergyElement.ANEMO,), (80,))
    runtime.spawn_pickup(
        SpawnEnergyPickupRequest(
            "pickup:solo", 0, EnergyPickupKind.PARTICLE, EnergyElement.ANEMO, 1, 0
        )
    )
    runtime.update_frame(None, 0)

    assert runtime.get_current_energy(_ref(1)) == 3.0


def test_pickup_uses_settlement_frame_active_slot_and_recharge():
    runtime, team, _events = _rig((EnergyElement.CRYO, EnergyElement.CRYO), (80, 80))
    runtime.spawn_pickup(
        SpawnEnergyPickupRequest(
            "pickup:switch", 10, EnergyPickupKind.PARTICLE, EnergyElement.CRYO, 1, 30
        )
    )
    team.switch_to(2, 39)
    runtime.update_frame(None, 40)

    assert runtime.get_current_energy(_ref(1)) == pytest.approx(2.4)
    assert runtime.get_current_energy(_ref(2)) == 3.0


def test_direct_restore_is_capped_and_does_not_read_recharge():
    runtime, _team, events = _rig((EnergyElement.HYDRO,), (10,), (999.0,))
    result = runtime.restore(RestoreEnergyRequest("restore:1", 5, _ref(1), 20))

    assert result.effective_amount == 10
    assert result.unapplied_amount == 10
    assert runtime.get_current_energy(_ref(1)) == 10
    assert [event.event_type for event in events.frame_events] == [
        EventType.DIRECT_ENERGY_CHANGE_RESOLVED,
        EventType.CHARACTER_ENERGY_CHANGED,
    ]


def test_direct_change_id_is_idempotent_across_restore_and_drain():
    runtime, _team, events = _rig((EnergyElement.HYDRO,), (10,))
    runtime.restore(RestoreEnergyRequest("change:shared", 1, _ref(1), 10))

    with pytest.raises(DuplicateEnergyRequestError):
        runtime.drain(DrainEnergyRequest("change:shared", 2, _ref(1), 3))
    with pytest.raises(DuplicateEnergyRequestError):
        runtime.spend_burst(SpendBurstEnergyRequest("change:shared", 3, _ref(1), "action:1"))

    assert runtime.get_current_energy(_ref(1)) == 10
    assert [event.event_type for event in events.frame_events] == [
        EventType.DIRECT_ENERGY_CHANGE_RESOLVED,
        EventType.CHARACTER_ENERGY_CHANGED,
    ]


def test_direct_change_id_cannot_block_internal_pickup_settlement():
    runtime, _team, _events = _rig((EnergyElement.HYDRO,), (10,))
    request_id = "shared"
    runtime.restore(
        RestoreEnergyRequest(f"pickup-settlement:energy-pickup:{request_id}", 1, _ref(1), 5)
    )
    runtime.spawn_pickup(
        SpawnEnergyPickupRequest(
            request_id, 2, EnergyPickupKind.PARTICLE, EnergyElement.HYDRO, 1, 0
        )
    )

    runtime.update_frame(None, 2)

    assert runtime.get_current_energy(_ref(1)) == 8
    assert runtime.transit_queue.is_empty()


def test_energy_write_is_blocked_during_fact_event_publish():
    runtime, _team, events = _rig((EnergyElement.HYDRO,), (10,))
    blocked: list[str] = []

    def reenter(_event):
        with pytest.raises(EnergyReentrancyError):
            runtime.restore(RestoreEnergyRequest("restore:inner", 1, _ref(1), 3))
        blocked.append("blocked")

    events.subscribe(EventType.DIRECT_ENERGY_CHANGE_RESOLVED, reenter)

    result = runtime.restore(RestoreEnergyRequest("restore:outer", 1, _ref(1), 2))

    assert result.energy_after == 2
    assert runtime.get_current_energy(_ref(1)) == 2
    assert blocked == ["blocked"]
    assert [event.event_type for event in events.frame_events] == [
        EventType.DIRECT_ENERGY_CHANGE_RESOLVED,
        EventType.CHARACTER_ENERGY_CHANGED,
    ]


def test_capacity_zero_rejects_direct_operations_and_is_never_burst_ready():
    runtime, _team, _events = _rig((EnergyElement.HYDRO,), (0,))

    assert not runtime.has_elemental_energy_resource(_ref(1))
    assert not runtime.is_burst_ready(_ref(1))
    with pytest.raises(UnsupportedEnergyResourceError):
        runtime.restore(RestoreEnergyRequest("restore:zero", 0, _ref(1), 1))
    with pytest.raises(UnsupportedEnergyResourceError):
        runtime.spend_burst(SpendBurstEnergyRequest("burst:zero", 0, _ref(1), "action:1"))


def test_bad_recharge_is_atomic_and_leaves_pickup_queued():
    runtime, _team, _events = _rig((EnergyElement.PYRO, EnergyElement.PYRO), (80, 80))
    runtime.attribute_resolver = _Resolver({}, fail_entity_id="character:slot_2")
    record = runtime.spawn_pickup(
        SpawnEnergyPickupRequest(
            "pickup:atomic", 0, EnergyPickupKind.PARTICLE, EnergyElement.PYRO, 1, 0
        )
    )

    with pytest.raises(InvalidEnergyAttributeError):
        runtime.update_frame(None, 0)

    assert runtime.get_current_energy(_ref(1)) == 0
    assert runtime.get_current_energy(_ref(2)) == 0
    assert runtime.transit_queue.records == (record,)
    assert not runtime.is_idle()


def test_burst_spend_requires_full_capacity_then_clears_energy():
    runtime, _team, _events = _rig((EnergyElement.ELECTRO,), (60,))
    runtime.restore(RestoreEnergyRequest("restore:full", 1, _ref(1), 60))

    result = runtime.spend_burst(SpendBurstEnergyRequest("burst:1", 2, _ref(1), "action:1"))

    assert result.energy_after == 0
    assert result.change_kind.value == "burst_spend"
    assert runtime.get_current_energy(_ref(1)) == 0


def test_same_frame_burst_spend_happens_before_arriving_pickup():
    runtime, _team, _events = _rig((EnergyElement.ELECTRO,), (60,))
    runtime.restore(RestoreEnergyRequest("restore:ready", 1, _ref(1), 60))
    runtime.spawn_pickup(
        SpawnEnergyPickupRequest(
            "pickup:after-burst",
            5,
            EnergyPickupKind.PARTICLE,
            EnergyElement.ELECTRO,
            1,
            0,
        )
    )

    runtime.spend_burst(SpendBurstEnergyRequest("burst:same-frame", 5, _ref(1), "action:1"))
    runtime.update_frame(None, 5)

    assert runtime.get_current_energy(_ref(1)) == 3.0


def test_snapshot_serializes_profiles_and_pending_pickups_in_stable_order():
    runtime, _team, _events = _rig((EnergyElement.PYRO, EnergyElement.HYDRO), (40, 60))
    runtime.spawn_pickup(
        SpawnEnergyPickupRequest(
            "pickup:later", 2, EnergyPickupKind.PARTICLE, EnergyElement.PYRO, 1, 5
        )
    )
    runtime.spawn_pickup(
        SpawnEnergyPickupRequest(
            "pickup:earlier", 1, EnergyPickupKind.ORB, EnergyElement.CLEAR, 1, 1
        )
    )

    snapshot = runtime.snapshot(1).to_dict()

    characters = cast(tuple[dict[str, object], ...], snapshot["characters"])
    pending_pickups = cast(tuple[dict[str, object], ...], snapshot["pending_pickups"])
    assert [character["character_key"] for character in characters] == [
        "character:1",
        "character:2",
    ]
    assert [pickup["request_id"] for pickup in pending_pickups] == [
        "pickup:earlier",
        "pickup:later",
    ]
