from __future__ import annotations

import pytest

from genshin_sim.application.assembly.reaction_capabilities import (
    build_static_reaction_eligibility_port,
)
from genshin_sim.content.models import ContentRuntimeContribution
from genshin_sim.core.elements import ElementalSubjectRef


def _character_contribution(
    *,
    slot: int,
    handler_key: str,
    capability_keys: tuple[str, ...],
) -> ContentRuntimeContribution:
    return ContentRuntimeContribution(
        owner_type="character",
        owner_key=f"character:test_{slot}",
        handler_key=handler_key,
        slot=slot,
        reaction_capability_keys=capability_keys,
    )


def test_static_reaction_eligibility_port_collects_all_character_providers():
    port = build_static_reaction_eligibility_port(
        (
            _character_contribution(
                slot=1,
                handler_key="character.test.one",
                capability_keys=("reaction_capability:lunar_charged",),
            ),
            _character_contribution(
                slot=2,
                handler_key="character.test.two",
                capability_keys=(
                    "reaction_capability:lunar_charged",
                    "reaction_capability:lunar_bloom",
                ),
            ),
        )
    )

    view = port.evidence_for(30, "team:test")

    assert view.team_ref == "team:test"
    assert view.frame == 30
    assert view.has("reaction_capability:lunar_charged")
    assert view.providers_for("reaction_capability:lunar_charged") == (
        ElementalSubjectRef.character("character:slot_1"),
        ElementalSubjectRef.character("character:slot_2"),
    )
    assert tuple(
        item.entity_id for item in view.providers_for("reaction_capability:lunar_charged")
    ) == (
        "character:slot_1",
        "character:slot_2",
    )


def test_content_capability_keys_are_character_only_and_validated():
    with pytest.raises(ValueError, match="只有角色 content"):
        ContentRuntimeContribution(
            owner_type="weapon",
            owner_key="weapon:test",
            handler_key="weapon.test",
            slot=1,
            reaction_capability_keys=("reaction_capability:lunar_charged",),
        )

    with pytest.raises(ValueError, match="reaction_capability"):
        ContentRuntimeContribution(
            owner_type="character",
            owner_key="character:test",
            handler_key="character.test",
            slot=1,
            reaction_capability_keys=("lunar_charged",),
        )


def test_static_reaction_eligibility_port_is_empty_without_content_capabilities():
    port = build_static_reaction_eligibility_port(
        (
            ContentRuntimeContribution(
                owner_type="character",
                owner_key="character:test",
                handler_key="character.test",
                slot=1,
            ),
        )
    )

    assert port.evidence_for(0, "team:test").evidence == ()
