"""普通感电的水雷双 Aura 建立、来源刷新与首个脉冲声明。"""

from __future__ import annotations

from genshin_sim.core.elements import AuraAmount, AuraKind, Element
from genshin_sim.core.systems.damage import DamageProfile, DamageType
from genshin_sim.core.systems.reaction.gates import ReactionDamageGateDefinition
from genshin_sim.core.systems.reaction.models import (
    CapturedTransformativeScalingBasis,
    ElectroChargedPropagationSelection,
    ElectroChargedStateApplicationEffect,
    ElementalTransitionEffect,
    GeneratedDamageImpactEffect,
    PersistentIncomingAuraApplicationEffect,
    ReactionDefinition,
    ReactionEffectExecutionScope,
    ReactionEffectGroup,
    ReactionEvaluationRequest,
    ReactionOccurrence,
    ReactionResolution,
    ReactionTriggerSignature,
    TransformativeReactionProfile,
)

ELECTRO_CHARGED_REACTION_KEY = "reaction.electro_charged"
ELECTRO_CHARGED_HANDLER_KEY = "reaction_handler.electro_charged"
HYDRO_ON_ELECTRO = "incoming_hydro_on_electro"
ELECTRO_ON_HYDRO = "incoming_electro_on_hydro"
HYDRO_ON_ELECTRO_PROFILE_KEY = "reaction_profile.electro_charged.incoming_hydro_on_electro"
ELECTRO_ON_HYDRO_PROFILE_KEY = "reaction_profile.electro_charged.incoming_electro_on_hydro"
ELECTRO_CHARGED_DAMAGE_PROFILE_KEY = "damage_profile.reaction.electro_charged"
ELECTRO_CHARGED_GATE_DEFINITION_KEY = "reaction_gate.electro_charged.damage"
ELECTRO_CHARGED_DAMAGE_KIND_KEY = "reaction_damage.electro_charged"
ELECTRO_CHARGED_BASE_MULTIPLIER = 2.0


class ElectroChargedRule:
    def evaluate(
        self,
        request: ReactionEvaluationRequest,
        definition: ReactionDefinition,
    ) -> ReactionResolution | None:
        if request.incoming_element is Element.HYDRO:
            existing_kind = AuraKind.ELECTRO
            direction = HYDRO_ON_ELECTRO
        elif request.incoming_element is Element.ELECTRO:
            existing_kind = AuraKind.HYDRO
            direction = ELECTRO_ON_HYDRO
        else:
            return None
        existing_amount = _amount_for(request, existing_kind)
        if existing_amount.is_zero:
            return None
        profile = definition.profile_for(direction)
        if not isinstance(profile, TransformativeReactionProfile):
            raise ValueError("感电方向必须使用 TransformativeReactionProfile")
        observation = request.transformative_source_observation
        if observation is None:
            raise ValueError("感电需要已捕获的剧变来源观察")
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
            main_attack_tag=ELECTRO_CHARGED_REACTION_KEY,
            damage_profile_key=profile.damage_profile_key,
            damage_element=Element.ELECTRO,
            gate_definition_key=profile.gate_definition_key,
            damage_kind_key=profile.damage_kind_key,
            captured_scaling_basis=basis,
            transformative_base_multiplier=profile.base_multiplier,
            audit_tags=(ELECTRO_CHARGED_REACTION_KEY,),
        )
        groups = (
            ()
            if request.observed_electro_charged_state is not None
            else (
                ReactionEffectGroup(
                    effect_group_ref=group_ref,
                    parent_occurrence_ref=occurrence_ref,
                    execution_scope=ReactionEffectExecutionScope.NEXT_SETTLEMENT_ROUND,
                    emission_order=0,
                    target_selection=ElectroChargedPropagationSelection(
                        selection_ref=f"{group_ref}:target_selection",
                        primary_subject_ref=request.subject_ref,
                    ),
                    effects=(effect,),
                ),
            )
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
                aura_kind=existing_kind,
                incoming_before=request.incoming_amount,
                incoming_consumed=AuraAmount.zero(),
                incoming_remaining=request.incoming_amount,
                aura_before=existing_amount,
                aura_consumed=AuraAmount.zero(),
                aura_remaining=existing_amount,
            ),
            effect_groups=groups,
            persistent_incoming_aura_application=PersistentIncomingAuraApplicationEffect(
                f"{occurrence_ref}:persistent-incoming-aura"
            ),
            electro_charged_state_application=ElectroChargedStateApplicationEffect(
                f"{occurrence_ref}:state-application",
                basis,
            ),
        )
        return ReactionResolution(request, occurrence, None)


def electro_charged_definition() -> ReactionDefinition:
    return ReactionDefinition(
        ELECTRO_CHARGED_REACTION_KEY,
        ELECTRO_CHARGED_HANDLER_KEY,
        (
            ReactionTriggerSignature(Element.HYDRO, AuraKind.ELECTRO, HYDRO_ON_ELECTRO),
            ReactionTriggerSignature(Element.ELECTRO, AuraKind.HYDRO, ELECTRO_ON_HYDRO),
        ),
        (
            TransformativeReactionProfile(
                HYDRO_ON_ELECTRO_PROFILE_KEY,
                ELECTRO_CHARGED_REACTION_KEY,
                HYDRO_ON_ELECTRO,
                Element.HYDRO,
                ELECTRO_CHARGED_DAMAGE_PROFILE_KEY,
                Element.ELECTRO,
                ELECTRO_CHARGED_BASE_MULTIPLIER,
                ELECTRO_CHARGED_GATE_DEFINITION_KEY,
                ELECTRO_CHARGED_DAMAGE_KIND_KEY,
            ),
            TransformativeReactionProfile(
                ELECTRO_ON_HYDRO_PROFILE_KEY,
                ELECTRO_CHARGED_REACTION_KEY,
                ELECTRO_ON_HYDRO,
                Element.ELECTRO,
                ELECTRO_CHARGED_DAMAGE_PROFILE_KEY,
                Element.ELECTRO,
                ELECTRO_CHARGED_BASE_MULTIPLIER,
                ELECTRO_CHARGED_GATE_DEFINITION_KEY,
                ELECTRO_CHARGED_DAMAGE_KIND_KEY,
            ),
        ),
        ElectroChargedRule(),
    )


def electro_charged_gate_definitions() -> tuple[ReactionDamageGateDefinition, ...]:
    return (
        ReactionDamageGateDefinition(
            ELECTRO_CHARGED_GATE_DEFINITION_KEY,
            ELECTRO_CHARGED_DAMAGE_KIND_KEY,
            30,
            1,
        ),
    )


def electro_charged_damage_profile() -> DamageProfile:
    """普通感电使用的生产剧变 Damage Profile。"""

    return DamageProfile(
        profile_key=ELECTRO_CHARGED_DAMAGE_PROFILE_KEY,
        damage_type=DamageType.TRANSFORMATIVE_REACTION,
        main_attack_tags=frozenset({ELECTRO_CHARGED_REACTION_KEY}),
    )


def _amount_for(request: ReactionEvaluationRequest, aura_kind: AuraKind) -> AuraAmount:
    component = request.observed_aura.component_for(aura_kind)
    return AuraAmount.zero() if component is None else component.current_amount
