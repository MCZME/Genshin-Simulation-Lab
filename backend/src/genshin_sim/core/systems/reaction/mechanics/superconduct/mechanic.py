"""普通超导的两个明确方向。"""

from __future__ import annotations

from genshin_sim.core.elements import AuraAmount, AuraKind, Element
from genshin_sim.core.systems.damage import DamageProfile
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_TRANSFORMATIVE_REACTION
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
    ReactionStatusEffect,
    ReactionTriggerSignature,
    TransformativeReactionProfile,
)

SUPERCONDUCT_REACTION_KEY = "reaction.superconduct"
SUPERCONDUCT_HANDLER_KEY = "reaction_handler.superconduct"
CRYO_ON_ELECTRO = "incoming_cryo_on_electro"
ELECTRO_ON_CRYO = "incoming_electro_on_cryo"
SUPERCONDUCT_DAMAGE_PROFILE_KEY = "damage_profile.reaction.superconduct"
SUPERCONDUCT_GATE_DEFINITION_KEY = "reaction_gate.superconduct.damage"
SUPERCONDUCT_DAMAGE_KIND_KEY = "reaction_damage.superconduct"
SUPERCONDUCT_STATUS_PROFILE_KEY = (
    "reaction_status_profile.superconduct.physical_resistance_reduction"
)


class SuperconductRule:
    def evaluate(
        self,
        request: ReactionEvaluationRequest,
        definition: ReactionDefinition,
    ) -> ReactionResolution | None:
        if request.incoming_element is Element.CRYO:
            aura_kind = AuraKind.ELECTRO
            direction = CRYO_ON_ELECTRO
        elif request.incoming_element is Element.ELECTRO:
            aura_kind = AuraKind.CRYO
            direction = ELECTRO_ON_CRYO
        else:
            return None
        aura_before = _amount_for(request, aura_kind)
        incoming_used = request.incoming_amount.minimum(aura_before)
        if aura_before.is_zero or incoming_used.is_zero:
            return None
        profile = definition.profile_for(direction)
        if not isinstance(profile, TransformativeReactionProfile):
            raise ValueError("超导方向必须使用 TransformativeReactionProfile")
        observation = request.transformative_source_observation
        if observation is None:
            raise ValueError("超导需要已捕获的剧变来源观察")
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
        damage = GeneratedDamageImpactEffect(
            effect_ref=f"{group_ref}:effect:0",
            effect_group_ref=group_ref,
            effect_order=0,
            parent_occurrence_ref=occurrence_ref,
            main_attack_tag=SUPERCONDUCT_REACTION_KEY,
            damage_profile_key=profile.damage_profile_key,
            damage_element=profile.damage_element,
            gate_definition_key=profile.gate_definition_key,
            damage_kind_key=profile.damage_kind_key,
            captured_scaling_basis=basis,
            transformative_base_multiplier=profile.base_multiplier,
            audit_tags=("reaction.superconduct",),
        )
        status = ReactionStatusEffect(
            effect_ref=f"{group_ref}:effect:1",
            effect_group_ref=group_ref,
            effect_order=1,
            parent_occurrence_ref=occurrence_ref,
            status_profile_key=SUPERCONDUCT_STATUS_PROFILE_KEY,
            duration_frames=720,
            value=-0.40,
            audit_tags=("reaction.superconduct", "resistance.physical"),
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
            effects=(damage, status),
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


def superconduct_definition() -> ReactionDefinition:
    return ReactionDefinition(
        SUPERCONDUCT_REACTION_KEY,
        SUPERCONDUCT_HANDLER_KEY,
        (
            ReactionTriggerSignature(Element.CRYO, AuraKind.ELECTRO, CRYO_ON_ELECTRO),
            ReactionTriggerSignature(Element.ELECTRO, AuraKind.CRYO, ELECTRO_ON_CRYO),
        ),
        (
            TransformativeReactionProfile(
                "reaction_profile.superconduct.incoming_cryo_on_electro",
                SUPERCONDUCT_REACTION_KEY,
                CRYO_ON_ELECTRO,
                Element.CRYO,
                SUPERCONDUCT_DAMAGE_PROFILE_KEY,
                Element.CRYO,
                1.5,
                SUPERCONDUCT_GATE_DEFINITION_KEY,
                SUPERCONDUCT_DAMAGE_KIND_KEY,
            ),
            TransformativeReactionProfile(
                "reaction_profile.superconduct.incoming_electro_on_cryo",
                SUPERCONDUCT_REACTION_KEY,
                ELECTRO_ON_CRYO,
                Element.ELECTRO,
                SUPERCONDUCT_DAMAGE_PROFILE_KEY,
                Element.CRYO,
                1.5,
                SUPERCONDUCT_GATE_DEFINITION_KEY,
                SUPERCONDUCT_DAMAGE_KIND_KEY,
            ),
        ),
        SuperconductRule(),
    )


def superconduct_gate_definitions() -> tuple[ReactionDamageGateDefinition, ...]:
    return (
        ReactionDamageGateDefinition(
            SUPERCONDUCT_GATE_DEFINITION_KEY,
            SUPERCONDUCT_DAMAGE_KIND_KEY,
            30,
            2,
        ),
    )


def superconduct_damage_profile() -> DamageProfile:
    """普通超导使用的生产剧变 Damage Profile。"""

    return DamageProfile(
        formula_key=FORMULA_KEY_TRANSFORMATIVE_REACTION,
        main_attack_tags=frozenset({SUPERCONDUCT_REACTION_KEY}),
    )


def _amount_for(request: ReactionEvaluationRequest, aura_kind: AuraKind) -> AuraAmount:
    component = request.observed_aura.component_for(aura_kind)
    return AuraAmount.zero() if component is None else component.current_amount
