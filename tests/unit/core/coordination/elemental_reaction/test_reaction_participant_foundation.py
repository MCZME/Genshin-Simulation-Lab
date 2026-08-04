from __future__ import annotations

from genshin_sim.core.elements import (
    AuraKind,
    Element,
    ElementalSourceRef,
    ElementalSubjectRef,
)
from genshin_sim.core.systems.aura import AuraApplicationRequest, AuraRuntime, AuraStrength
from genshin_sim.core.systems.reaction import (
    ReactionParticipantSnapshot,
    freeze_character_participants,
)

TARGET = ElementalSubjectRef.target("target:test")
SOURCE_A = ElementalSourceRef("character:slot_1")
SOURCE_B = ElementalSourceRef("character:slot_2")
SOURCE_C = ElementalSourceRef("character:slot_3")
ENVIRONMENT = ElementalSourceRef("environment:water")


def _apply_request(
    source_ref: ElementalSourceRef,
    request_id: str,
    order: int,
    element: Element,
) -> AuraApplicationRequest:
    return AuraApplicationRequest(
        request_id,
        f"{request_id}:application",
        f"impact:{request_id}",
        0,
        order,
        source_ref,
        TARGET,
        element,
        AuraStrength.WEAK,
    )


def test_freeze_character_participants_includes_active_contributors_and_trigger():
    runtime = AuraRuntime()
    runtime.apply(_apply_request(SOURCE_A, "water:a", 0, Element.HYDRO))
    runtime.apply(_apply_request(SOURCE_B, "water:b", 1, Element.HYDRO))
    runtime.apply(_apply_request(ENVIRONMENT, "water:environment", 2, Element.HYDRO))

    snapshot = freeze_character_participants(
        runtime.view(TARGET),
        used_aura_kinds=(AuraKind.HYDRO,),
        character_source_refs=(SOURCE_A, SOURCE_B, SOURCE_C),
        triggering_source_ref=SOURCE_C,
    )

    assert snapshot == ReactionParticipantSnapshot((SOURCE_A, SOURCE_B, SOURCE_C))


def test_freeze_character_participants_filters_unused_elements_and_deduplicates():
    runtime = AuraRuntime()
    runtime.apply(_apply_request(SOURCE_A, "water:a", 0, Element.HYDRO))
    runtime.apply(_apply_request(SOURCE_B, "electro:b", 1, Element.ELECTRO))

    snapshot = freeze_character_participants(
        runtime.view(TARGET),
        used_aura_kinds=(AuraKind.HYDRO,),
        character_source_refs=(SOURCE_A, SOURCE_B, SOURCE_C),
        triggering_source_ref=SOURCE_A,
    )

    assert snapshot.participant_refs == (SOURCE_A,)
    assert snapshot.to_dict() == {
        "participant_refs": [SOURCE_A.to_dict()],
    }


def test_participant_snapshot_canonicalizes_duplicate_sources():
    snapshot = ReactionParticipantSnapshot((SOURCE_B, SOURCE_A, SOURCE_B))

    assert snapshot.participant_refs == (SOURCE_A, SOURCE_B)
