from __future__ import annotations

import pytest

from genshin_sim.core.elements import Element
from genshin_sim.core.events import EventEngine, EventType
from genshin_sim.core.systems.infusion import (
    EffectiveElementReason,
    InfusionDefinitionRegistry,
    InfusionMode,
    InfusionResolver,
    InfusionRuntime,
    InfusionStore,
    InfusionSystemError,
)
from tests.helpers.infusion import CHARACTER, make_definition, make_request


def test_conversion_overrides_active_infusion():
    infusion = make_definition(element=Element.PYRO)
    conversion = make_definition(
        definition_key="infusion.test.conversion",
        mode=InfusionMode.CONVERSION,
        element=Element.CRYO,
    )
    runtime = _runtime(infusion, conversion)
    runtime.apply(make_request("req:1", infusion, frame=0))
    runtime.apply(make_request("req:2", conversion, frame=1))

    resolution = runtime.resolve_effective_element(1, CHARACTER, Element.PHYSICAL)
    assert resolution.element is Element.CRYO
    assert resolution.mode is InfusionMode.CONVERSION
    assert resolution.reason is EffectiveElementReason.CONVERSION
    assert len(resolution.source_refs) == 1
    assert len(runtime.infusion_store.active(1, character_ref=CHARACTER)) == 2


def test_infusion_cannot_override_conversion_and_recovers_after_expiry():
    conversion = make_definition(
        definition_key="infusion.test.conversion",
        mode=InfusionMode.CONVERSION,
        element=Element.CRYO,
        duration_frames=5,
    )
    infusion = make_definition(element=Element.PYRO, duration_frames=10)
    runtime = _runtime(conversion, infusion)
    runtime.apply(make_request("req:1", conversion, frame=0))
    runtime.apply(make_request("req:2", infusion, frame=1))

    during = runtime.resolve_effective_element(1, CHARACTER, Element.PHYSICAL)
    assert during.element is Element.CRYO
    assert during.mode is InfusionMode.CONVERSION

    runtime.update_frame(None, 5)
    after = runtime.resolve_effective_element(5, CHARACTER, Element.PHYSICAL)
    assert after.element is Element.PYRO
    assert after.mode is InfusionMode.INFUSION
    assert after.reason is EffectiveElementReason.SINGLE_SOURCE
    assert runtime.event_engine.frame_events[-1].event_type is EventType.INFUSION_REMOVED


def test_fresh_infusion_during_conversion_does_not_override():
    conversion = make_definition(
        definition_key="infusion.test.conversion",
        mode=InfusionMode.CONVERSION,
        element=Element.CRYO,
        duration_frames=10,
    )
    infusion = make_definition(element=Element.PYRO)
    runtime = _runtime(conversion, infusion)
    runtime.apply(make_request("req:1", conversion, frame=0))
    runtime.apply(make_request("req:2", infusion, frame=2))

    resolution = runtime.resolve_effective_element(2, CHARACTER, Element.PHYSICAL)
    assert resolution.element is Element.CRYO
    assert resolution.mode is InfusionMode.CONVERSION
    assert resolution.weapon_gauge is not None


def test_resolver_rejects_multiple_active_conversions():
    first = make_definition(
        definition_key="infusion.test.conversion.1",
        mode=InfusionMode.CONVERSION,
        element=Element.CRYO,
    )
    second = make_definition(
        definition_key="infusion.test.conversion.2",
        mode=InfusionMode.CONVERSION,
        element=Element.HYDRO,
    )
    resolver = InfusionResolver()
    from genshin_sim.core.systems.infusion import InfusionInstanceRef
    from tests.helpers.infusion import make_record

    records = (
        make_record(InfusionInstanceRef(1), first),
        make_record(InfusionInstanceRef(2), second),
    )
    with pytest.raises(InfusionSystemError, match="多个转化来源"):
        resolver.resolve_effective_element(
            0,
            CHARACTER,
            Element.PHYSICAL,
            records,
        )


def _runtime(*definitions) -> InfusionRuntime:
    return InfusionRuntime(
        definition_registry=InfusionDefinitionRegistry(tuple(definitions)),
        resolver=InfusionResolver(),
        infusion_store=InfusionStore(),
        event_engine=EventEngine(),
    )
