from __future__ import annotations

import pytest

from genshin_sim.core.elements import AuraAmount, Element
from genshin_sim.core.events import EventEngine
from genshin_sim.core.impacts import (
    DamageImpactSpec,
    ImpactKind,
    ImpactRequest,
)
from genshin_sim.core.systems.aura import AuraStrength
from genshin_sim.core.systems.infusion import (
    InfusionDamageElementAdapter,
    InfusionDefinitionRegistry,
    InfusionImpactContractError,
    InfusionImpactRequestHandler,
    InfusionResolver,
    InfusionRuntime,
    InfusionStore,
    UnsupportedWeaponAuraRuleError,
)
from tests.helpers.infusion import (
    CHARACTER,
    SOURCE,
    make_definition,
)


class _Context:
    space_runtime = None


def test_apply_infusion_impact_adapts_and_records():
    definition = make_definition()
    runtime = _runtime(definition)
    handler = InfusionImpactRequestHandler(runtime)
    request = ImpactRequest(
        frame=5,
        kind=ImpactKind.APPLY_INFUSION,
        impact_key="impact.test_infusion",
        owner_slot=1,
        request_id="impact:infusion:1",
        source_impact_point_id="impact-point:infusion",
        target_refs=("character:slot_1",),
        params={
            "infusion": {
                "definition_key": definition.definition_key,
                "applier_ref": {
                    "kind": "character",
                    "entity_id": "character:slot_1",
                },
            }
        },
    )

    results = handler.handle_impact_request(_Context(), request)

    assert len(results) == 1
    assert results[0].definition_key == definition.definition_key
    assert results[0].character_ref == CHARACTER
    assert results[0].applier_ref == CHARACTER
    assert results[0].request_id.startswith("infusion-impact")
    assert len(handler.records) == 1
    record = handler.records[0]
    assert record.frame == 5
    assert record.infusion_requests[0].source_context == SOURCE
    assert len(runtime.infusion_store.active(5, character_ref=CHARACTER)) == 1


def test_apply_infusion_impact_rejects_invalid_contracts():
    definition = make_definition()
    runtime = _runtime(definition)
    handler = InfusionImpactRequestHandler(runtime)
    base = {
        "frame": 0,
        "kind": ImpactKind.APPLY_INFUSION,
        "impact_key": "impact.test_infusion",
        "owner_slot": 1,
    }

    with pytest.raises(InfusionImpactContractError, match="params.infusion"):
        handler.handle_impact_request(
            _Context(),
            ImpactRequest(**base, target_refs=("character:slot_1",)),
        )
    with pytest.raises(InfusionImpactContractError, match="不是受支持字段"):
        handler.handle_impact_request(
            _Context(),
            ImpactRequest(
                **base,
                request_id="impact:bad",
                target_refs=("character:slot_1",),
                params={"infusion": {"definition_key": definition.definition_key, "x": 1}},
            ),
        )
    with pytest.raises(InfusionImpactContractError, match="target_refs 不能为空"):
        handler.handle_impact_request(
            _Context(),
            ImpactRequest(
                **base,
                request_id="impact:empty",
                params={"infusion": {"definition_key": definition.definition_key}},
            ),
        )
    with pytest.raises(InfusionImpactContractError, match="只支持 character"):
        handler.handle_impact_request(
            _Context(),
            ImpactRequest(
                **base,
                request_id="impact:bad-applier",
                target_refs=("character:slot_1",),
                params={
                    "infusion": {
                        "definition_key": definition.definition_key,
                        "applier_ref": {"kind": "target", "entity_id": "target:1"},
                    }
                },
            ),
        )
    with pytest.raises(InfusionImpactContractError, match="必须提供"):
        handler.handle_impact_request(
            _Context(),
            ImpactRequest(
                **base,
                target_refs=("character:slot_1",),
                params={"infusion": {"definition_key": definition.definition_key}},
            ),
        )
    assert runtime.infusion_store.records == ()


def test_damage_element_adapter_replaces_element_and_injects_gauge():
    definition = make_definition(
        element=Element.PYRO,
        applicable_attack_tags=frozenset({"普通攻击1"}),
    )
    runtime = _runtime(definition)
    runtime.apply(_apply_request(definition, frame=1))
    adapter = InfusionDamageElementAdapter(runtime)
    spec = _physical_spec(icd=True)

    resolved, record = adapter.apply(
        1,
        CHARACTER,
        spec,
        impact_key="melee.normal.1",
        request_id="impact:na",
    )

    assert record.applied is True
    assert record.base_element is Element.PHYSICAL
    assert resolved.element is Element.PYRO
    assert resolved.elemental_strength is AuraStrength.WEAK
    assert resolved.elemental_amount == AuraAmount(1)
    assert resolved.icd_tag_key == "普攻"
    assert resolved.icd_sequence_key == "默认"
    assert record.resolution.weapon_gauge == AuraAmount(1)
    assert adapter.records == (record,)


def test_damage_element_adapter_keeps_existing_elemental_fields():
    definition = make_definition(
        element=Element.PYRO,
        applicable_attack_tags=frozenset({"普通攻击1"}),
    )
    runtime = _runtime(definition)
    runtime.apply(_apply_request(definition, frame=1))
    adapter = InfusionDamageElementAdapter(runtime)
    spec = DamageImpactSpec(
        impact_ref="impact:na",
        main_attack_tag="普通攻击1",
        element=Element.HYDRO,
        elemental_strength=AuraStrength.MEDIUM,
        elemental_amount=AuraAmount("3/2"),
    )

    resolved, _ = adapter.apply(
        1,
        CHARACTER,
        spec,
        impact_key="melee.normal.1",
        request_id="impact:na",
    )

    assert resolved.element is Element.PYRO
    assert resolved.elemental_strength is AuraStrength.MEDIUM
    assert resolved.elemental_amount == AuraAmount("3/2")


def test_damage_element_adapter_ignores_uncovered_attack_tags_and_empty_state():
    definition = make_definition(
        element=Element.PYRO,
        applicable_attack_tags=frozenset({"普通攻击1"}),
    )
    runtime = _runtime(definition)
    adapter = InfusionDamageElementAdapter(runtime)
    spec = _physical_spec(icd=False)

    untouched, empty_record = adapter.apply(
        0,
        CHARACTER,
        spec,
        impact_key="melee.normal.1",
        request_id="impact:empty",
    )
    assert empty_record.applied is False
    assert untouched is spec

    runtime.apply(_apply_request(definition, frame=1))
    skill_spec = DamageImpactSpec(
        impact_ref="impact:skill",
        main_attack_tag="元素战技",
        element=Element.PHYSICAL,
    )
    untouched_skill, skill_record = adapter.apply(
        1,
        CHARACTER,
        skill_spec,
        impact_key="melee.skill",
        request_id="impact:skill",
    )
    assert skill_record.applied is False
    assert untouched_skill.element is Element.PHYSICAL


def test_damage_element_adapter_maps_configured_gauge_to_strength():
    definition = make_definition(
        element=Element.PYRO,
        weapon_gauge=AuraAmount(2),
        applicable_attack_tags=frozenset({"普通攻击1"}),
    )
    runtime = _runtime(definition)
    runtime.apply(_apply_request(definition, frame=1))
    adapter = InfusionDamageElementAdapter(runtime)

    resolved, _ = adapter.apply(
        1,
        CHARACTER,
        _physical_spec(icd=False),
        impact_key="melee.normal.1",
        request_id="impact:gauge",
    )
    assert resolved.elemental_strength is AuraStrength.STRONG
    assert resolved.elemental_amount == AuraAmount(2)

    unsupported = make_definition(
        definition_key="infusion.test.unsupported_gauge",
        element=Element.CRYO,
        weapon_gauge=AuraAmount(3),
        applicable_attack_tags=frozenset({"普通攻击1"}),
    )
    unsupported_runtime = _runtime(unsupported)
    unsupported_runtime.apply(_apply_request(unsupported, frame=1))
    unsupported_adapter = InfusionDamageElementAdapter(unsupported_runtime)
    with pytest.raises(UnsupportedWeaponAuraRuleError, match="附着强度"):
        unsupported_adapter.apply(
            1,
            CHARACTER,
            _physical_spec(icd=False),
            impact_key="melee.normal.1",
            request_id="impact:bad-gauge",
        )


def _physical_spec(*, icd: bool) -> DamageImpactSpec:
    return DamageImpactSpec(
        impact_ref="impact:na",
        main_attack_tag="普通攻击1",
        element=Element.PHYSICAL,
        icd_tag_key=("普攻" if icd else None),
        icd_sequence_key=("默认" if icd else None),
    )


def _apply_request(definition, *, frame: int):
    from tests.helpers.infusion import make_request

    return make_request(f"req:{frame}", definition, frame=frame)


def _runtime(*definitions) -> InfusionRuntime:
    return InfusionRuntime(
        definition_registry=InfusionDefinitionRegistry(tuple(definitions)),
        resolver=InfusionResolver(),
        infusion_store=InfusionStore(),
        event_engine=EventEngine(),
    )
