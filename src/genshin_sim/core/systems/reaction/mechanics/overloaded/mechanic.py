"""普通超载的两个明确方向。"""

from __future__ import annotations

from genshin_sim.core.elements import AuraAmount, AuraKind, Element
from genshin_sim.core.impacts import StrikeType
from genshin_sim.core.systems.damage import DamageElement
from genshin_sim.core.systems.reaction.gates import ReactionDamageGateDefinition
from genshin_sim.core.systems.reaction.models import (
    AreaAroundSubjectSelection,
    CapturedTransformativeScalingBasis,
    ElementalTransitionEffect,
    GeneratedDamageImpactEffect,
    ReactionDefinition,
    ReactionEffectExecutionScope,
    ReactionEffectGroup,
    ReactionEvaluationRequest,
    ReactionOccurrence,
    ReactionResolution,
    ReactionTriggerSignature,
    TransformativeReactionProfile,
)

OVERLOADED_REACTION_KEY = "reaction.overloaded"
OVERLOADED_HANDLER_KEY = "reaction_handler.overloaded"
PYRO_ON_ELECTRO = "incoming_pyro_on_electro"
ELECTRO_ON_PYRO = "incoming_electro_on_pyro"
OVERLOADED_DAMAGE_PROFILE_KEY = "damage_profile.reaction.overloaded"
OVERLOADED_GATE_DEFINITION_KEY = "reaction_gate.overloaded.damage"
OVERLOADED_DAMAGE_KIND_KEY = "reaction_damage.overloaded"


class OverloadedRule:
    def evaluate(
        self,
        request: ReactionEvaluationRequest,
        definition: ReactionDefinition,
    ) -> ReactionResolution | None:
        if request.incoming_element is Element.PYRO:
            aura_kind = AuraKind.ELECTRO
            direction = PYRO_ON_ELECTRO
        elif request.incoming_element is Element.ELECTRO:
            aura_kind = AuraKind.PYRO
            direction = ELECTRO_ON_PYRO
        else:
            return None
        aura_before = _amount_for(request, aura_kind)
        incoming_used = request.incoming_amount.minimum(aura_before)
        if aura_before.is_zero or incoming_used.is_zero:
            return None
        profile = definition.profile_for(direction)
        if not isinstance(profile, TransformativeReactionProfile):
            raise ValueError("超载方向必须使用 TransformativeReactionProfile")
        observation = request.transformative_source_observation
        if observation is None:
            raise ValueError("超载需要已捕获的剧变来源观察")
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
            reaction_profile_key=profile.profile_key,
            damage_profile_key=profile.damage_profile_key,
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
            main_attack_tag=OVERLOADED_REACTION_KEY,
            damage_profile_key=profile.damage_profile_key,
            damage_element=profile.damage_element,
            gate_definition_key=profile.gate_definition_key,
            damage_kind_key=profile.damage_kind_key,
            captured_scaling_basis=basis,
            transformative_base_multiplier=profile.base_multiplier,
            strike_type=StrikeType.BLUNT,
            audit_tags=("reaction.overloaded",),
        )
        group = ReactionEffectGroup(
            effect_group_ref=group_ref,
            parent_occurrence_ref=occurrence_ref,
            execution_scope=ReactionEffectExecutionScope.NEXT_SETTLEMENT_ROUND,
            emission_order=0,
            target_selection=AreaAroundSubjectSelection(
                selection_ref=f"{group_ref}:target_selection",
                anchor_subject_ref=request.subject_ref,
            ),
            effects=(effect,),
        )
        occurrence = ReactionOccurrence(
            occurrence_ref=occurrence_ref,
            interaction_id=request.interaction_id,
            reaction_key=definition.reaction_key,
            direction_key=direction,
            profile_key=profile.profile_key,
            source_ref=request.source_ref,
            subject_ref=request.subject_ref,
            transition=ElementalTransitionEffect(
                aura_kind=aura_kind,
                incoming_before=request.incoming_amount,
                incoming_consumed=incoming_used,
                incoming_remaining=request.incoming_amount - incoming_used,
                aura_before=aura_before,
                aura_consumed=incoming_used,
                aura_remaining=aura_before - incoming_used,
            ),
            effect_groups=(group,),
        )
        return ReactionResolution(request, occurrence, None)


def overloaded_definition() -> ReactionDefinition:
    return ReactionDefinition(
        OVERLOADED_REACTION_KEY,
        OVERLOADED_HANDLER_KEY,
        (
            ReactionTriggerSignature(Element.PYRO, AuraKind.ELECTRO, PYRO_ON_ELECTRO),
            ReactionTriggerSignature(Element.ELECTRO, AuraKind.PYRO, ELECTRO_ON_PYRO),
        ),
        (
            TransformativeReactionProfile(
                "reaction_profile.overloaded.incoming_pyro_on_electro",
                OVERLOADED_REACTION_KEY,
                PYRO_ON_ELECTRO,
                Element.PYRO,
                OVERLOADED_DAMAGE_PROFILE_KEY,
                DamageElement.PYRO,
                2.75,
                OVERLOADED_GATE_DEFINITION_KEY,
                OVERLOADED_DAMAGE_KIND_KEY,
            ),
            TransformativeReactionProfile(
                "reaction_profile.overloaded.incoming_electro_on_pyro",
                OVERLOADED_REACTION_KEY,
                ELECTRO_ON_PYRO,
                Element.ELECTRO,
                OVERLOADED_DAMAGE_PROFILE_KEY,
                DamageElement.PYRO,
                2.75,
                OVERLOADED_GATE_DEFINITION_KEY,
                OVERLOADED_DAMAGE_KIND_KEY,
            ),
        ),
        OverloadedRule(),
    )


def overloaded_gate_definitions() -> tuple[ReactionDamageGateDefinition, ...]:
    return (
        ReactionDamageGateDefinition(
            OVERLOADED_GATE_DEFINITION_KEY,
            OVERLOADED_DAMAGE_KIND_KEY,
            30,
            1,
        ),
    )


def _amount_for(request: ReactionEvaluationRequest, aura_kind: AuraKind) -> AuraAmount:
    component = request.observed_aura.component_for(aura_kind)
    return AuraAmount.zero() if component is None else component.current_amount
