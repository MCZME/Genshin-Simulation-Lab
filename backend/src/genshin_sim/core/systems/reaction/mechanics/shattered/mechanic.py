"""钝击触发的普通碎冰。"""

from __future__ import annotations

from genshin_sim.core.elements import AuraAmount, AuraKind, Element
from genshin_sim.core.impacts import StrikeType
from genshin_sim.core.systems.reaction.gates import ReactionDamageGateDefinition
from genshin_sim.core.systems.reaction.models import (
    CapturedTransformativeScalingBasis,
    CurrentSubjectSelection,
    ElementalTransitionEffect,
    GeneratedDamageImpactEffect,
    ReactionDefinition,
    ReactionEffectExecutionScope,
    ReactionEffectGroup,
    ReactionEntryKind,
    ReactionEvaluationRequest,
    ReactionOccurrence,
    ReactionResolution,
)

SHATTERED_REACTION_KEY = "reaction.shattered"
SHATTERED_HANDLER_KEY = "reaction_handler.shattered"
SHATTERED_PROFILE_KEY = "reaction_profile.shattered"
SHATTERED_DAMAGE_PROFILE_KEY = "damage_profile.reaction.shattered"
SHATTERED_DAMAGE_KIND_KEY = "reaction_damage.shattered"
SHATTERED_GATE_DEFINITION_KEY = "reaction_gate.shattered.damage"
SHATTERED_BASE_MULTIPLIER = 3.0


class ShatteredRule:
    def evaluate(
        self,
        request: ReactionEvaluationRequest,
        definition: ReactionDefinition,
    ) -> ReactionResolution | None:
        if (
            request.trigger_context is None
            or request.trigger_context.strike_type is not StrikeType.BLUNT
            or request.observed_frozen_state is None
        ):
            return None
        frozen = request.observed_aura.component_for(AuraKind.FROZEN)
        if frozen is None or frozen.current_amount.is_zero:
            return None
        observation = request.transformative_source_observation
        if observation is None:
            raise ValueError("碎冰需要已捕获的剧变来源观察")
        occurrence_ref = f"{request.interaction_id}:occurrence:{request.order}"
        group_ref = f"{occurrence_ref}:effect_group:0"
        basis = CapturedTransformativeScalingBasis(
            basis_ref=f"{group_ref}:basis",
            captured_frame=request.frame,
            source_ref=observation.source_ref,
            source_kind=observation.source_kind,
            source_level=observation.source_level,
            elemental_mastery=observation.elemental_mastery,
            reaction_bonus=0.0,
            reaction_profile_key=SHATTERED_PROFILE_KEY,
            damage_profile_key=SHATTERED_DAMAGE_PROFILE_KEY,
            level_multiplier_table_key=observation.level_multiplier_table_key,
            level_multiplier=observation.level_multiplier,
            source_observation_ref=observation.source_observation_ref,
            source_owner_slot=observation.source_owner_slot,
        )
        effect = GeneratedDamageImpactEffect(
            effect_ref=f"{group_ref}:effect:0",
            effect_group_ref=group_ref,
            effect_order=0,
            parent_occurrence_ref=occurrence_ref,
            main_attack_tag=SHATTERED_REACTION_KEY,
            damage_profile_key=SHATTERED_DAMAGE_PROFILE_KEY,
            damage_element=Element.PHYSICAL,
            gate_definition_key=SHATTERED_GATE_DEFINITION_KEY,
            damage_kind_key=SHATTERED_DAMAGE_KIND_KEY,
            captured_scaling_basis=basis,
            transformative_base_multiplier=SHATTERED_BASE_MULTIPLIER,
            audit_tags=(SHATTERED_REACTION_KEY,),
        )
        group = ReactionEffectGroup(
            effect_group_ref=group_ref,
            parent_occurrence_ref=occurrence_ref,
            execution_scope=ReactionEffectExecutionScope.NEXT_SETTLEMENT_ROUND,
            emission_order=0,
            target_selection=CurrentSubjectSelection(
                selection_ref=f"{group_ref}:target_selection",
                subject_ref=request.subject_ref,
            ),
            effects=(effect,),
        )
        occurrence = ReactionOccurrence(
            occurrence_ref=occurrence_ref,
            interaction_id=request.interaction_id,
            reaction_key=definition.reaction_key,
            direction_key="blunt_on_frozen",
            profile_key=SHATTERED_PROFILE_KEY,
            source_ref=request.source_ref,
            subject_ref=request.subject_ref,
            transition=ElementalTransitionEffect(
                aura_kind=AuraKind.FROZEN,
                incoming_before=request.incoming_amount,
                incoming_consumed=AuraAmount.zero(),
                incoming_remaining=request.incoming_amount,
                aura_before=frozen.current_amount,
                aura_consumed=frozen.current_amount,
                aura_remaining=AuraAmount.zero(),
            ),
            effect_groups=(group,),
        )
        return ReactionResolution(request, occurrence, None)


def shattered_definition() -> ReactionDefinition:
    return ReactionDefinition(
        SHATTERED_REACTION_KEY,
        SHATTERED_HANDLER_KEY,
        (),
        (),
        ShatteredRule(),
        ReactionEntryKind.STATE_TRIGGER,
    )


def shattered_gate_definitions() -> tuple[ReactionDamageGateDefinition, ...]:
    return (
        ReactionDamageGateDefinition(
            SHATTERED_GATE_DEFINITION_KEY,
            SHATTERED_DAMAGE_KIND_KEY,
            30,
            2,
        ),
    )
