from __future__ import annotations

import pytest

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.coordination.character_damage_taken import CharacterIncomingDamage
from genshin_sim.core.coordination.elemental_reaction import CrystallizeShardPickupRequest
from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
)
from genshin_sim.core.impacts import ElementalApplicationSpec, ImpactKind, ImpactRequest
from genshin_sim.core.systems.aura import AuraStrength
from genshin_sim.core.systems.reaction import (
    CrystallizeShardLifecycleState,
    ReactionStateInstanceRef,
)
from genshin_sim.core.systems.shield import ShieldProtectionRef
from tests.helpers.reactions import apply_aura, target_subject


@pytest.mark.parametrize(
    ("aura_element", "expected_aura", "expected_shard_element"),
    (
        (Element.PYRO, AuraKind.PYRO, Element.PYRO),
        (Element.HYDRO, AuraKind.HYDRO, Element.HYDRO),
        (Element.ELECTRO, AuraKind.ELECTRO, Element.ELECTRO),
        (Element.CRYO, AuraKind.CRYO, Element.CRYO),
    ),
)
def test_production_assembly_creates_a_bound_crystallize_shard(
    golden_assembled,
    aura_element: Element,
    expected_aura: AuraKind,
    expected_shard_element: Element,
):
    assembled = golden_assembled(meta_name="crystallize golden", max_frames=900)
    apply_aura(assembled, aura_element, "golden:initial", strength=AuraStrength.WEAK)

    record = assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        _geo_request("golden:crystallize"),
    )

    assert len(record.reaction_occurrence_refs) == 1
    assert len(record.reaction_state_binding_refs) == 1
    assert len(record.spatial_entity_refs) == 1
    assert len(record.establishment_gate_resolution_refs) == 1
    shard_ref = ReactionStateInstanceRef(record.reaction_state_binding_refs[0])
    shard = assembled.reaction_runtime.crystallize_shard_state_for(shard_ref)
    entity = assembled.space_runtime.get_entity(record.spatial_entity_refs[0])
    aura = assembled.aura_runtime.view(target_subject()).component_for(expected_aura)

    assert shard is not None
    assert entity is not None
    assert shard.element is expected_shard_element
    assert shard.space_entity_ref == entity.entity_id
    assert entity.source_key == shard_ref.value
    assert shard.expires_at_frame == 900
    assert aura is not None


def test_production_pickup_grants_and_consumes_crystallize_shield(
    golden_assembled,
):
    assembled = golden_assembled(meta_name="crystallize golden", max_frames=900)
    apply_aura(assembled, Element.PYRO, "golden:pickup:initial", strength=AuraStrength.WEAK)
    record = assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        _geo_request("golden:pickup:crystallize"),
    )
    shard_ref = ReactionStateInstanceRef(record.reaction_state_binding_refs[0])
    assembled.elemental_state_frame_coordinator.normalize(assembled.context, 1)

    pickup = assembled.crystallize_shard_pickup_coordinator.pickup(
        assembled.context,
        CrystallizeShardPickupRequest(
            operation_id="golden:pickup:one",
            frame=1,
            shard_ref=shard_ref,
            protection_ref=ShieldProtectionRef.active_team(),
        ),
    )

    assert pickup.shield_grant.resolution.granted_absorption == (
        pickup.captured_shield_basis.native_absorption
    )
    assert pickup.shield_grant.expires_at_after == 901
    shard = assembled.reaction_runtime.crystallize_shard_state_for(shard_ref)
    assert shard is not None
    assert shard.lifecycle_state is CrystallizeShardLifecycleState.PICKED
    assert assembled.space_runtime.get_entity(record.spatial_entity_refs[0]) is None
    assert len(assembled.shield_store.active_records) == 1

    target_ref = AttributeSubjectRef.character("character:slot_1")
    damage = assembled.character_damage_taken_coordinator.apply(
        CharacterIncomingDamage(
            damage_id="golden:pickup:damage",
            frame=1,
            target_ref=target_ref,
            amount=10.0,
            element=Element.PYRO,
        )
    )
    assert damage.shield_result.protected_damage == 10.0
    assert damage.health_result.effective_amount == 0.0


def test_gate_blocks_then_expiry_removes_the_production_shard(golden_assembled):
    assembled = golden_assembled(meta_name="crystallize golden", max_frames=900)
    apply_aura(assembled, Element.PYRO, "golden:initial", strength=AuraStrength.WEAK)
    first = assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        _geo_request("golden:crystallize:first"),
    )
    shard_ref = ReactionStateInstanceRef(first.reaction_state_binding_refs[0])
    entity_ref = first.spatial_entity_refs[0]

    blocked = assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        _geo_request("golden:crystallize:blocked"),
    )

    assert blocked.reaction_occurrence_refs == ()
    assert blocked.reaction_state_binding_refs == ()
    assert blocked.spatial_entity_refs == ()
    assert len(blocked.establishment_gate_resolution_refs) == 1
    assert len(assembled.reaction_runtime.state_records) == 1

    assembled.elemental_settlement_coordinator.update_frame(assembled.context, 900)

    shard = assembled.reaction_runtime.crystallize_shard_state_for(shard_ref)
    assert shard is not None
    assert shard.lifecycle_state is CrystallizeShardLifecycleState.EXPIRED
    assert shard.terminal_frame == 900
    assert assembled.space_runtime.get_entity(entity_ref) is None
    reaction_snapshot = assembled.reaction_runtime.snapshot(900)
    assert reaction_snapshot.state_records == (shard,)
    assert len(reaction_snapshot.establishment_gate_records) == 1
    assert (
        reaction_snapshot.establishment_gate_records[0].last_occurrence_ref
        == first.reaction_occurrence_refs[0]
    )
    assert all(
        entity.entity_id != entity_ref
        for entity in assembled.space_runtime.space.snapshot(900).entities
    )


def test_water_electro_uses_gate_to_block_second_crystallize(
    golden_assembled,
):
    assembled = golden_assembled(meta_name="crystallize golden", max_frames=900)
    apply_aura(assembled, Element.HYDRO, "golden:water-electro:hydro", strength=AuraStrength.WEAK)
    apply_aura(
        assembled,
        Element.ELECTRO,
        "golden:water-electro:electro",
        strength=AuraStrength.WEAK,
    )

    record = assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        _geo_request(
            "golden:water-electro:geo",
            elemental_amount=AuraAmount(3),
        ),
    )

    assert len(record.establishment_gate_resolution_refs) == 2
    assert len(record.reaction_occurrence_refs) == 1
    assert len(record.reaction_state_binding_refs) == 1
    shard = assembled.reaction_runtime.crystallize_shard_state_for(
        ReactionStateInstanceRef(record.reaction_state_binding_refs[0])
    )
    aura = assembled.aura_runtime.view(target_subject())
    assert shard is not None
    assert shard.element is Element.ELECTRO
    assert aura.component_for(AuraKind.ELECTRO) is None
    assert aura.component_for(AuraKind.HYDRO) is not None
    assert (
        assembled.reaction_runtime.establishment_gate_records[0].last_occurrence_ref
        == record.reaction_occurrence_refs[0]
    )


def _geo_request(
    request_id: str,
    *,
    elemental_amount: AuraAmount | None = None,
) -> ImpactRequest:
    return ImpactRequest(
        frame=0,
        kind=ImpactKind.APPLY_AURA,
        impact_key="golden.crystallize.geo",
        owner_slot=1,
        request_id=request_id,
        target_refs=("target_1",),
        elemental_application_spec=ElementalApplicationSpec(
            impact_ref=f"{request_id}:impact",
            element=Element.GEO,
            elemental_strength=AuraStrength.WEAK,
            elemental_amount=(AuraAmount.one() if elemental_amount is None else elemental_amount),
        ),
    )
