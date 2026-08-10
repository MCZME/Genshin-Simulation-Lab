from __future__ import annotations

import json

from genshin_sim.core.attributes import RuntimeSourceKind, RuntimeSourceRef
from genshin_sim.core.elements import AuraAmount, Element
from genshin_sim.core.events import EventEngine, EventType
from genshin_sim.core.systems.infusion import (
    EffectiveElementReason,
    InfusionDefinitionRegistry,
    InfusionResolver,
    InfusionRuntime,
    InfusionStore,
    RefreshPolicy,
)
from tests.helpers.infusion import CHARACTER, make_definition, make_request


def test_electro_charged_side_expiry_falls_back_to_hydro():
    hydro = _definition(Element.HYDRO, duration=10)
    electro = _definition(Element.ELECTRO, duration=2)
    runtime = _runtime(hydro, electro)
    _apply(runtime, hydro, 0)
    _apply(runtime, electro, 1)
    runtime.update_frame(None, 3)
    resolution = runtime.resolve_effective_element(3, CHARACTER, Element.PHYSICAL)
    assert resolution.element is Element.HYDRO
    assert resolution.reason is EffectiveElementReason.SINGLE_SOURCE


def test_periodic_refresh_reapplies_after_consumption_gap():
    electro = _definition(Element.ELECTRO, duration=10)
    cryo = _definition(
        Element.CRYO,
        definition_key="infusion.test.cryo_periodic",
        refresh_policy=RefreshPolicy.PERIODIC,
        period=2,
        duration=6,
    )
    runtime = _runtime(electro, cryo)
    _apply(runtime, electro, 0)
    _apply(runtime, cryo, 1)
    gap = runtime.resolve_effective_element(1, CHARACTER, Element.PHYSICAL)
    assert gap.element is Element.PHYSICAL
    assert gap.reason is EffectiveElementReason.CONSUMED

    runtime.update_frame(None, 3)
    refreshed = runtime.resolve_effective_element(3, CHARACTER, Element.PHYSICAL)
    assert refreshed.element is Element.CRYO
    assert refreshed.reason is EffectiveElementReason.SINGLE_SOURCE
    assert runtime.event_engine.frame_events[-1].event_type is EventType.INFUSION_APPLIED


def test_periodic_refresh_extends_lifecycle_and_expires():
    pyro = _definition(
        Element.PYRO,
        definition_key="infusion.test.pyro_periodic",
        refresh_policy=RefreshPolicy.PERIODIC,
        period=2,
        duration=4,
    )
    runtime = _runtime(pyro)
    applied = runtime.apply(make_request("req:1", pyro, frame=0))
    assert applied.next_refresh_frame_after == 2

    runtime.update_frame(None, 2)
    record = runtime.infusion_store.require(applied.instance_ref)
    assert record.last_applied_frame == 2
    assert record.expires_at_frame == 6
    assert record.next_refresh_frame == 4
    assert runtime.resolve_effective_element(2, CHARACTER, Element.PHYSICAL).element is (
        Element.PYRO
    )

    runtime.update_frame(None, 4)
    assert runtime.infusion_store.require(applied.instance_ref).expires_at_frame == 8
    runtime.update_frame(None, 8)
    assert runtime.infusion_store.require(applied.instance_ref).is_active_at(8) is False
    assert runtime.event_engine.frame_events[-1].event_type is EventType.INFUSION_REMOVED
    assert runtime.resolve_effective_element(8, CHARACTER, Element.PHYSICAL).reason is (
        EffectiveElementReason.NO_ACTIVE_SOURCE
    )


def test_fire_entering_electro_charged_processes_electro_then_hydro():
    electro = _definition(Element.ELECTRO)
    hydro = _definition(Element.HYDRO)
    pyro = _definition(Element.PYRO, weapon_gauge=AuraAmount(5))
    runtime = _runtime(electro, hydro, pyro)
    _apply(runtime, electro, 0)
    _apply(runtime, hydro, 1)
    _apply(runtime, pyro, 2)
    resolution = runtime.resolve_effective_element(2, CHARACTER, Element.PHYSICAL)
    assert resolution.element is Element.PYRO
    assert resolution.reason is EffectiveElementReason.SINGLE_SOURCE


def test_cryo_entering_electro_charged_can_freeze_hydro():
    electro = _definition(Element.ELECTRO)
    hydro = _definition(Element.HYDRO)
    cryo = _definition(Element.CRYO, weapon_gauge=AuraAmount(2))
    runtime = _runtime(electro, hydro, cryo)
    _apply(runtime, electro, 0)
    _apply(runtime, hydro, 1)
    _apply(runtime, cryo, 2)
    resolution = runtime.resolve_effective_element(2, CHARACTER, Element.PHYSICAL)
    assert resolution.element is Element.CRYO
    assert resolution.reason is EffectiveElementReason.FREEZE


def test_uneven_melt_can_consume_both_sides():
    pyro = _definition(Element.PYRO)
    cryo = _definition(Element.CRYO, weapon_gauge=AuraAmount(2))
    runtime = _runtime(pyro, cryo)
    _apply(runtime, cryo, 0)
    _apply(runtime, pyro, 1)
    resolution = runtime.resolve_effective_element(1, CHARACTER, Element.PHYSICAL)
    assert resolution.element is Element.PHYSICAL
    assert resolution.reason is EffectiveElementReason.CONSUMED


def test_period_equals_duration_refreshes_before_expiry():
    pyro = _definition(
        Element.PYRO,
        definition_key="infusion.test.pyro_equal",
        refresh_policy=RefreshPolicy.PERIODIC,
        period=4,
        duration=4,
    )
    runtime = _runtime(pyro)
    applied = runtime.apply(make_request("req:1", pyro, frame=0))
    runtime.update_frame(None, 4)
    record = runtime.infusion_store.require(applied.instance_ref)
    assert record.is_active_at(4)
    assert record.expires_at_frame == 8
    assert runtime.event_engine.frame_events[-1].event_type is EventType.INFUSION_APPLIED


def test_snapshot_exposes_remaining_gauge_and_frozen():
    hydro = _definition(Element.HYDRO)
    cryo = _definition(Element.CRYO)
    runtime = _runtime(hydro, cryo)
    _apply(runtime, hydro, 0)
    _apply(runtime, cryo, 1)
    snapshot = json.loads(json.dumps(runtime.snapshot(1).to_dict()))
    instances = snapshot["instances"]
    assert len(instances) == 2
    frozen = next(item for item in instances if item["frozen"] is True)
    assert frozen["element"] == "cryo"
    assert frozen["remaining_gauge"]["numerator"] == 0
    hydro_snapshot = next(item for item in instances if item["element"] == "hydro")
    assert hydro_snapshot["remaining_gauge"]["numerator"] == 0


def _definition(
    element: Element,
    *,
    definition_key: str | None = None,
    refresh_policy: RefreshPolicy = RefreshPolicy.ONCE,
    period: int | None = None,
    duration: int = 10,
    weapon_gauge: AuraAmount | None = None,
):
    return make_definition(
        definition_key=definition_key or f"infusion.test.{element.value}",
        mechanic_key=f"mechanic.test_infusion.{element.value}",
        element=element,
        refresh_policy=refresh_policy,
        period_frames=period,
        duration_frames=duration,
        weapon_gauge=weapon_gauge if weapon_gauge is not None else AuraAmount(1),
    )


def _apply(runtime: InfusionRuntime, definition, frame: int) -> None:
    runtime.apply(
        make_request(
            f"req:{definition.definition_key}:{frame}",
            definition,
            frame=frame,
            source_context=RuntimeSourceRef(
                RuntimeSourceKind.MECHANIC,
                definition.mechanic_key,
                "infusion",
            ),
        )
    )


def _runtime(*definitions) -> InfusionRuntime:
    return InfusionRuntime(
        definition_registry=InfusionDefinitionRegistry(tuple(definitions)),
        resolver=InfusionResolver(),
        infusion_store=InfusionStore(),
        event_engine=EventEngine(),
    )
