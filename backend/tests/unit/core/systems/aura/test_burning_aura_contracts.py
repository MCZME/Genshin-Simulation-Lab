from __future__ import annotations

import pytest

from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
    ElementalSourceRef,
    ElementalStateLinkRef,
    ElementalSubjectRef,
    aura_kind_for_element,
)
from genshin_sim.core.systems.aura import (
    AuraApplicationRequest,
    AuraDecayMode,
    AuraRuntime,
    AuraStateLinkMutationRequest,
    AuraStrength,
    BurningAuraApplicationRequest,
    UnsupportedAuraCombinationError,
)

SOURCE = ElementalSourceRef("character:slot_1", "ability:test")
TARGET = ElementalSubjectRef.target("target:test")
LINK_A = ElementalStateLinkRef("elemental-state-link:a")
LINK_B = ElementalStateLinkRef("elemental-state-link:b")


def test_dendro_is_a_persistent_aura_but_pyro_remains_ordinary_pyro():
    assert aura_kind_for_element(Element.DENDRO) is AuraKind.DENDRO
    assert aura_kind_for_element(Element.PYRO) is AuraKind.PYRO
    assert AuraKind.BURNING is not aura_kind_for_element(Element.PYRO)


def test_dendro_and_cryo_are_an_explicit_legal_persistent_combination():
    runtime = AuraRuntime()
    runtime.apply(_application("aura:dendro", Element.DENDRO))
    runtime.apply(_application("aura:cryo", Element.CRYO))

    assert tuple(component.aura_kind for component in runtime.view(TARGET).components) == (
        AuraKind.CRYO,
        AuraKind.DENDRO,
    )


def test_ordinary_application_cannot_directly_create_pyro_dendro_residual_state():
    runtime = AuraRuntime()
    runtime.apply(_application("aura:dendro", Element.DENDRO))

    with pytest.raises(UnsupportedAuraCombinationError, match="dendro 与 pyro"):
        runtime.apply(_application("aura:pyro", Element.PYRO))


def test_burning_requires_linked_dendro_and_suspends_ordinary_dendro_decay():
    runtime = AuraRuntime()
    planner = runtime.begin_batch(0, "burning-establishment")
    planner.apply(_application("aura:dendro", Element.DENDRO, order=0))
    planner.mutate_state_links(
        AuraStateLinkMutationRequest(
            request_id="aura:dendro:burning-link",
            frame=0,
            order=1,
            target_ref=TARGET,
            aura_kind=AuraKind.DENDRO,
            add_link_refs=(LINK_A,),
            decay_mode=AuraDecayMode.REACTION_MANAGED,
        )
    )
    planner.apply_burning(_burning_request(order=2))
    runtime.commit_prevalidated(planner.seal())

    before = runtime.view(TARGET)
    dendro = before.component_for(AuraKind.DENDRO)
    burning = before.component_for(AuraKind.BURNING)
    assert dendro is not None
    assert burning is not None
    assert dendro.state_link_refs == (LINK_A,)
    assert dendro.decay_mode is AuraDecayMode.REACTION_MANAGED
    assert burning.state_link_refs == (LINK_A,)
    assert burning.decay_mode is AuraDecayMode.STATE_LINKED

    runtime.update_frame(None, 120)
    paused = runtime.view(TARGET)
    assert paused.component_for(AuraKind.DENDRO).current_amount == dendro.current_amount  # type: ignore[union-attr]
    assert paused.component_for(AuraKind.BURNING).current_amount == burning.current_amount  # type: ignore[union-attr]

    cleanup = runtime.begin_batch(120, "burning-termination")
    cleanup.consume(
        interaction_id="aura:burning:depleted",
        subject_ref=TARGET,
        aura_kind=AuraKind.BURNING,
        amount=burning.current_amount,
    )
    cleanup.mutate_state_links(
        AuraStateLinkMutationRequest(
            request_id="aura:dendro:remove-burning-link",
            frame=120,
            order=0,
            target_ref=TARGET,
            aura_kind=AuraKind.DENDRO,
            remove_link_refs=(LINK_A,),
            decay_mode=AuraDecayMode.STANDARD,
        )
    )
    runtime.commit_prevalidated(cleanup.seal())

    runtime.update_frame(None, 240)
    restored = runtime.view(TARGET).component_for(AuraKind.DENDRO)
    assert restored is not None
    assert restored.state_link_refs == ()
    assert restored.decay_mode is AuraDecayMode.STANDARD
    assert restored.current_amount < dendro.current_amount


def test_burning_request_rejects_unlinked_dendro():
    runtime = AuraRuntime()
    planner = runtime.begin_batch(0, "burning-missing-link")
    planner.apply(_application("aura:dendro", Element.DENDRO, order=0))

    with pytest.raises(ValueError, match="携带同一 Link 的类草 Aura"):
        planner.apply_burning(_burning_request(order=1))


def test_burning_request_rejects_linked_dendro_with_standard_decay():
    runtime = AuraRuntime()
    planner = runtime.begin_batch(0, "burning-standard-dendro")
    planner.apply(_application("aura:dendro", Element.DENDRO, order=0))
    planner.mutate_state_links(
        AuraStateLinkMutationRequest(
            request_id="aura:dendro:add-link",
            frame=0,
            order=1,
            target_ref=TARGET,
            aura_kind=AuraKind.DENDRO,
            add_link_refs=(LINK_A,),
        )
    )

    with pytest.raises(ValueError, match="受 Reaction 管理"):
        planner.apply_burning(_burning_request(order=2))


def test_link_mutation_keeps_stable_order_and_rejects_duplicate_additions():
    runtime = AuraRuntime()
    planner = runtime.begin_batch(0, "link-order")
    planner.apply(_application("aura:dendro", Element.DENDRO, order=0))
    planner.mutate_state_links(
        AuraStateLinkMutationRequest(
            request_id="aura:dendro:add-b",
            frame=0,
            order=1,
            target_ref=TARGET,
            aura_kind=AuraKind.DENDRO,
            add_link_refs=(LINK_B,),
        )
    )
    component = planner.mutate_state_links(
        AuraStateLinkMutationRequest(
            request_id="aura:dendro:add-a",
            frame=0,
            order=2,
            target_ref=TARGET,
            aura_kind=AuraKind.DENDRO,
            add_link_refs=(LINK_A,),
        )
    )

    assert component.state_link_refs == (LINK_A, LINK_B)
    with pytest.raises(ValueError, match="重复添加"):
        planner.mutate_state_links(
            AuraStateLinkMutationRequest(
                request_id="aura:dendro:add-a-again",
                frame=0,
                order=3,
                target_ref=TARGET,
                aura_kind=AuraKind.DENDRO,
                add_link_refs=(LINK_A,),
            )
        )


def _application(request_id: str, element: Element, *, order: int = 0) -> AuraApplicationRequest:
    return AuraApplicationRequest(
        request_id=request_id,
        application_id=f"{request_id}:application",
        impact_ref=f"impact:{request_id}",
        frame=0,
        order=order,
        source_ref=SOURCE,
        target_ref=TARGET,
        element=element,
        base_strength=AuraStrength.WEAK,
    )


def _burning_request(*, order: int) -> BurningAuraApplicationRequest:
    return BurningAuraApplicationRequest(
        request_id="aura:burning",
        application_id="aura:burning:application",
        impact_ref="impact:burning",
        frame=0,
        order=order,
        source_ref=SOURCE,
        target_ref=TARGET,
        state_link_ref=LINK_A,
        amount=AuraAmount("2"),
    )
