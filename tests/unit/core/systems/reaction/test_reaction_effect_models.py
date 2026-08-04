from __future__ import annotations

from dataclasses import replace

import pytest

from genshin_sim.core.elements import (
    ElementalSourceRef,
    ElementalSubjectRef,
    TransformativeReactionSourceKind,
)
from genshin_sim.core.systems.damage import DamageElement
from genshin_sim.core.systems.reaction import (
    CapturedTransformativeScalingBasis,
    CurrentSubjectSelection,
    GeneratedDamageImpactEffect,
    ReactionEffectExecutionScope,
    ReactionEffectGroup,
    ReactionStateInstanceRef,
    ReactionStatusEffect,
    ScheduledStateTickCause,
    ScheduledStateTickKind,
)


def test_generated_damage_effect_supports_single_target_physical_transformative_damage():
    subject = ElementalSubjectRef.target("target:target_1")
    effect = GeneratedDamageImpactEffect(
        effect_ref="effect:shattered",
        effect_group_ref="group:shattered",
        effect_order=0,
        parent_occurrence_ref="occurrence:shattered",
        main_attack_tag="reaction.shattered",
        damage_profile_key="damage_profile.reaction.shattered",
        damage_element=DamageElement.PHYSICAL,
        gate_definition_key="reaction_gate.shattered.damage",
        damage_kind_key="reaction_damage.shattered",
        captured_scaling_basis=CapturedTransformativeScalingBasis(
            basis_ref="basis:shattered",
            captured_frame=0,
            source_ref=ElementalSourceRef("character:slot_1"),
            source_kind=TransformativeReactionSourceKind.CHARACTER,
            source_level=90,
            elemental_mastery=0.0,
            reaction_bonus=0.0,
            reaction_profile_key="reaction_profile.shattered",
            damage_profile_key="damage_profile.reaction.shattered",
            level_multiplier_table_key="character",
            level_multiplier=1446.853,
            source_observation_ref="observation:shattered",
            source_owner_slot=1,
        ),
        transformative_base_multiplier=3.0,
    )
    group = ReactionEffectGroup(
        effect_group_ref="group:shattered",
        parent_occurrence_ref="occurrence:shattered",
        execution_scope=ReactionEffectExecutionScope.NEXT_SETTLEMENT_ROUND,
        emission_order=0,
        target_selection=CurrentSubjectSelection("selection:shattered", subject),
        effects=(effect,),
    )

    assert isinstance(group.target_selection, CurrentSubjectSelection)
    assert isinstance(group.effects[0], GeneratedDamageImpactEffect)
    assert group.target_selection.subject_ref == subject
    assert group.effects[0].damage_element is DamageElement.PHYSICAL
    assert group.effects[0].transformative_base_multiplier == 3.0

    with pytest.raises(ValueError, match="必须为正数"):
        replace(effect, transformative_base_multiplier=0)


def test_scheduled_status_effect_uses_cause_without_an_occurrence_projection():
    subject = ElementalSubjectRef.target("target:target_1")
    cause = ScheduledStateTickCause(
        state_instance_ref=ReactionStateInstanceRef("reaction-state-instance:status"),
        scheduled_frame=30,
        tick_kind=ScheduledStateTickKind.BURNING_DAMAGE,
        tick_index=2,
    )
    effect = ReactionStatusEffect(
        effect_ref="effect:scheduled-status",
        effect_group_ref="group:scheduled-status",
        effect_order=0,
        parent_occurrence_ref=None,
        status_profile_key="status_profile:scheduled",
        duration_frames=60,
        value=0.2,
        cause=cause,
    )
    group = ReactionEffectGroup(
        effect_group_ref="group:scheduled-status",
        parent_occurrence_ref=None,
        execution_scope=ReactionEffectExecutionScope.NEXT_SETTLEMENT_ROUND,
        emission_order=0,
        target_selection=CurrentSubjectSelection("selection:scheduled-status", subject),
        effects=(effect,),
        cause=cause,
    )

    assert effect.parent_occurrence_ref is None
    assert group.parent_occurrence_ref is None
    assert group.cause == cause
