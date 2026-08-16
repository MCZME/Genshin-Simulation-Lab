from __future__ import annotations

import pytest

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.elements import Element
from genshin_sim.core.systems.infusion import (
    EffectiveElementReason,
    InfusionApplicationOutcome,
    InfusionInstanceRef,
    InfusionMode,
    InfusionResolver,
    InfusionSystemError,
    UnsupportedWeaponAuraRuleError,
)
from tests.helpers.infusion import (
    CHARACTER,
    CHARACTER_2,
    SOURCE,
    make_definition,
    make_record,
    make_request,
)


def test_resolver_create_and_refresh_same_definition():
    resolver = InfusionResolver()
    definition = make_definition(duration_frames=10)
    created = resolver.resolve_apply(
        definition,
        make_request("req:1", definition),
        active_records=(),
        allocated_ref=InfusionInstanceRef(1),
    )
    assert created.result.outcome is InfusionApplicationOutcome.CREATED
    record = created.replacement_records[0]
    assert record.expires_at_frame == 10
    assert record.next_refresh_frame is None

    refreshed = resolver.resolve_apply(
        definition,
        make_request("req:2", definition, frame=2),
        active_records=(record,),
        allocated_ref=None,
    )
    assert refreshed.result.outcome is InfusionApplicationOutcome.REFRESHED
    assert refreshed.replacement_records[0].instance_ref == record.instance_ref
    assert refreshed.replacement_records[0].expires_at_frame == 12
    assert refreshed.result.expires_at_before == 10

    shorter = resolver.resolve_apply(
        definition,
        make_request("req:3", definition, frame=3),
        active_records=(refreshed.replacement_records[0],),
        allocated_ref=None,
    )
    assert shorter.replacement_records[0].expires_at_frame == 13


def test_resolver_same_element_different_definition_keeps_separate_records():
    resolver = InfusionResolver()
    first = make_definition(definition_key="infusion.test.first")
    second = make_definition(definition_key="infusion.test.second")
    one = resolver.resolve_apply(
        first,
        make_request("req:1", first),
        active_records=(),
        allocated_ref=InfusionInstanceRef(1),
    )
    two = resolver.resolve_apply(
        second,
        make_request("req:2", second, frame=1),
        active_records=one.replacement_records,
        allocated_ref=InfusionInstanceRef(2),
    )
    assert two.result.outcome is InfusionApplicationOutcome.CREATED
    assert any(record.instance_ref == InfusionInstanceRef(2) for record in two.replacement_records)


def test_resolver_conversion_replaces_existing_conversion():
    resolver = InfusionResolver()
    first = make_definition(
        definition_key="infusion.test.conversion.1",
        mode=InfusionMode.CONVERSION,
        element=Element.HYDRO,
    )
    second = make_definition(
        definition_key="infusion.test.conversion.2",
        mode=InfusionMode.CONVERSION,
        element=Element.CRYO,
    )
    created = resolver.resolve_apply(
        first,
        make_request("req:1", first),
        active_records=(),
        allocated_ref=InfusionInstanceRef(1),
    )
    replaced = resolver.resolve_apply(
        second,
        make_request("req:2", second, frame=1),
        active_records=created.replacement_records,
        allocated_ref=InfusionInstanceRef(2),
    )
    assert replaced.result.outcome is InfusionApplicationOutcome.REPLACED
    assert replaced.result.replaced_instance_refs == (InfusionInstanceRef(1),)
    assert len(replaced.removals) == 1
    assert len(replaced.replacement_records) == 2
    new_record = next(
        record
        for record in replaced.replacement_records
        if record.instance_ref == InfusionInstanceRef(2)
    )
    assert new_record.element is Element.CRYO


def test_resolver_effective_element_precedence_and_guards():
    resolver = InfusionResolver()
    infusion = make_definition(element=Element.PYRO)
    conversion = make_definition(
        definition_key="infusion.test.conversion",
        mode=InfusionMode.CONVERSION,
        element=Element.CRYO,
    )
    infusion_record = make_record(InfusionInstanceRef(1), infusion)
    conversion_record = make_record(InfusionInstanceRef(2), conversion)

    empty = resolver.resolve_effective_element(
        0,
        CHARACTER,
        Element.PHYSICAL,
        (),
    )
    assert empty.element is Element.PHYSICAL
    assert empty.mode is None
    assert empty.reason is EffectiveElementReason.NO_ACTIVE_SOURCE

    single = resolver.resolve_effective_element(
        0,
        CHARACTER,
        Element.PHYSICAL,
        (infusion_record,),
    )
    assert single.element is Element.PYRO
    assert single.mode is InfusionMode.INFUSION
    assert single.reason is EffectiveElementReason.SINGLE_SOURCE

    converted = resolver.resolve_effective_element(
        0,
        CHARACTER,
        Element.PHYSICAL,
        (infusion_record, conversion_record),
    )
    assert converted.element is Element.CRYO
    assert converted.mode is InfusionMode.CONVERSION
    assert converted.reason is EffectiveElementReason.CONVERSION

    other = make_record(
        InfusionInstanceRef(3),
        make_definition(definition_key="infusion.test.other", element=Element.CRYO),
    )
    with pytest.raises(UnsupportedWeaponAuraRuleError, match="不支持的武器附着组合"):
        resolver.resolve_effective_element(
            0,
            CHARACTER,
            Element.PHYSICAL,
            (infusion_record, other),
        )

    other_character = make_record(
        InfusionInstanceRef(4),
        infusion,
        character_ref=CHARACTER_2,
    )
    isolated = resolver.resolve_effective_element(
        0,
        CHARACTER,
        Element.PHYSICAL,
        (infusion_record, other_character),
    )
    assert isolated.element is Element.PYRO
    assert isolated.source_refs == (SOURCE,)

    with pytest.raises(InfusionSystemError, match="base_element"):
        resolver.resolve_effective_element(0, CHARACTER, "pyro", ())  # type: ignore[arg-type]
    with pytest.raises(InfusionSystemError, match="角色主体"):
        resolver.resolve_effective_element(
            0,
            AttributeSubjectRef.target("target:target_1"),
            Element.PHYSICAL,
            (),
        )
