"""普通燃烧的首次建立与无 occurrence 来源维护。"""

from __future__ import annotations

from genshin_sim.core.elements import AuraAmount, AuraKind, Element, ElementalStateLinkRef
from genshin_sim.core.systems.aura import AuraApplicationProfile, AuraDecayProfilePolicy
from genshin_sim.core.systems.damage import DamageElement, DamageProfile, DamageType
from genshin_sim.core.systems.reaction.gates import ReactionDamageGateDefinition
from genshin_sim.core.systems.reaction.models import (
    AreaAroundSubjectSelection,
    BurningStateEstablishmentIntent,
    BurningStateMaintenanceIntent,
    CapturedTransformativeScalingBasis,
    ElementalTransitionEffect,
    GeneratedDamageImpactEffect,
    ReactionDecisionSequence,
    ReactionDecisionStep,
    ReactionDefinition,
    ReactionEffectExecutionScope,
    ReactionEffectGroup,
    ReactionEvaluationRequest,
    ReactionOccurrence,
    ReactionResolution,
    ReactionTriggerSignature,
    TransformativeReactionProfile,
)

BURNING_REACTION_KEY = "reaction.burning"
BURNING_HANDLER_KEY = "reaction_handler.burning"
PYRO_ON_DENDRO = "incoming_pyro_on_dendro"
PYRO_ON_QUICKEN = "incoming_pyro_on_quicken"
DENDRO_ON_PYRO = "incoming_dendro_on_pyro"
PYRO_ON_DENDRO_PROFILE_KEY = "reaction_profile.burning.incoming_pyro_on_dendro"
PYRO_ON_QUICKEN_PROFILE_KEY = "reaction_profile.burning.incoming_pyro_on_quicken"
DENDRO_ON_PYRO_PROFILE_KEY = "reaction_profile.burning.incoming_dendro_on_pyro"
BURNING_DAMAGE_PROFILE_KEY = "damage_profile.reaction.burning"
BURNING_GATE_DEFINITION_KEY = "reaction_gate.burning.damage"
BURNING_DAMAGE_KIND_KEY = "reaction_damage.burning"
BURNING_PYRO_AURA_APPLICATION_PROFILE_KEY = (
    "aura_application_profile.reaction.burning.periodic_pyro"
)
BURNING_AMOUNT = AuraAmount(2)
BURNING_PYRO_APPLICATION_AMOUNT = AuraAmount(1)
BURNING_DAMAGE_BASE_MULTIPLIER = 0.25
BURNING_DAMAGE_WINDOW_FRAMES = 120
BURNING_DAMAGE_MAX_INSTANCES = 8
FIRST_DAMAGE_INTERVAL_FRAMES = 15
FIRST_PYRO_APPLICATION_INTERVAL_FRAMES = 15


class BurningRule:
    def evaluate(
        self,
        request: ReactionEvaluationRequest,
        definition: ReactionDefinition,
    ) -> ReactionResolution | None:
        if request.incoming_element is Element.PYRO:
            existing_kind = (
                AuraKind.DENDRO
                if not _amount_for(request, AuraKind.DENDRO).is_zero
                else AuraKind.QUICKEN
            )
            direction = PYRO_ON_DENDRO if existing_kind is AuraKind.DENDRO else PYRO_ON_QUICKEN
        elif request.incoming_element is Element.DENDRO:
            existing_kind = AuraKind.PYRO
            direction = DENDRO_ON_PYRO
        else:
            return None
        if request.incoming_amount.is_zero:
            return None
        existing_amount = _amount_for(request, existing_kind)
        if existing_amount.is_zero and request.observed_burning_state is None:
            return None
        profile = definition.profile_for(direction)
        if not isinstance(profile, TransformativeReactionProfile):
            raise ValueError("燃烧方向必须使用 TransformativeReactionProfile")
        observation = request.transformative_source_observation
        if observation is None:
            raise ValueError("燃烧需要已捕获的剧变来源观察")
        basis = CapturedTransformativeScalingBasis(
            basis_ref=f"{request.interaction_id}:basis",
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
        transition = ElementalTransitionEffect(
            aura_kind=existing_kind,
            incoming_before=request.incoming_amount,
            incoming_consumed=AuraAmount.zero(),
            incoming_remaining=request.incoming_amount,
            aura_before=existing_amount,
            aura_consumed=AuraAmount.zero(),
            aura_remaining=existing_amount,
        )
        current = request.observed_burning_state
        if current is not None:
            if not request.state_maintenance_allowed:
                return None
            intent = BurningStateMaintenanceIntent(
                intent_ref=f"{request.interaction_id}:burning-maintenance",
                subject_ref=request.subject_ref,
                frame=request.frame,
                expected_state_instance_ref=current.instance_ref,
                expected_state_revision=current.revision,
                application_ref=f"{request.target_impact_ref}:application",
                effect_owner_ref=request.source_ref,
                captured_scaling_basis=basis,
            )
            return ReactionResolution(
                request,
                None,
                None,
                decision_sequence=ReactionDecisionSequence(
                    (
                        ReactionDecisionStep(
                            0,
                            (definition.reaction_key,),
                            (transition,),
                            (),
                            (),
                            (intent,),
                        ),
                    )
                ),
            )

        if existing_amount.is_zero:
            return None

        occurrence_ref = f"{request.interaction_id}:occurrence:{request.order}"
        group_ref = f"{occurrence_ref}:effect_group:0"
        state_link_ref = ElementalStateLinkRef(f"elemental-state-link:burning:{occurrence_ref}")
        effect = GeneratedDamageImpactEffect(
            effect_ref=f"{group_ref}:effect:0",
            effect_group_ref=group_ref,
            effect_order=0,
            parent_occurrence_ref=occurrence_ref,
            main_attack_tag=BURNING_REACTION_KEY,
            damage_profile_key=profile.damage_profile_key,
            damage_element=DamageElement.PYRO,
            gate_definition_key=profile.gate_definition_key,
            damage_kind_key=profile.damage_kind_key,
            transformative_base_multiplier=profile.base_multiplier,
            captured_scaling_basis=basis,
            audit_tags=(BURNING_REACTION_KEY,),
        )
        group = ReactionEffectGroup(
            effect_group_ref=group_ref,
            parent_occurrence_ref=occurrence_ref,
            execution_scope=ReactionEffectExecutionScope.NEXT_SETTLEMENT_ROUND,
            emission_order=0,
            target_selection=AreaAroundSubjectSelection(
                selection_ref=f"{group_ref}:target_selection",
                anchor_subject_ref=request.subject_ref,
                radius=1.0,
                include_anchor=True,
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
            transition=transition,
            effect_groups=(group,),
        )
        intent = BurningStateEstablishmentIntent(
            intent_ref=f"{occurrence_ref}:burning-establishment",
            subject_ref=request.subject_ref,
            occurrence_ref=occurrence_ref,
            frame=request.frame,
            burning_aura_link_ref=state_link_ref,
            dendro_like_link_refs=tuple(
                sorted(
                    (
                        state_link_ref,
                        *(
                            ()
                            if request.observed_quicken_state is None
                            else (request.observed_quicken_state.quicken_aura_link_ref,)
                        ),
                    ),
                    key=lambda item: item.link_key,
                )
            ),
            effect_owner_ref=request.source_ref,
            captured_scaling_basis=basis,
        )
        return ReactionResolution(
            request,
            occurrence,
            None,
            decision_sequence=ReactionDecisionSequence(
                (
                    ReactionDecisionStep(
                        0,
                        (definition.reaction_key,),
                        (transition,),
                        (),
                        (occurrence,),
                        (intent,),
                    ),
                )
            ),
        )


def burning_definition() -> ReactionDefinition:
    return ReactionDefinition(
        BURNING_REACTION_KEY,
        BURNING_HANDLER_KEY,
        (
            ReactionTriggerSignature(Element.PYRO, AuraKind.DENDRO, PYRO_ON_DENDRO),
            ReactionTriggerSignature(Element.PYRO, AuraKind.QUICKEN, PYRO_ON_QUICKEN),
            ReactionTriggerSignature(Element.DENDRO, AuraKind.PYRO, DENDRO_ON_PYRO),
        ),
        (
            TransformativeReactionProfile(
                PYRO_ON_DENDRO_PROFILE_KEY,
                BURNING_REACTION_KEY,
                PYRO_ON_DENDRO,
                Element.PYRO,
                BURNING_DAMAGE_PROFILE_KEY,
                DamageElement.PYRO,
                BURNING_DAMAGE_BASE_MULTIPLIER,
                BURNING_GATE_DEFINITION_KEY,
                BURNING_DAMAGE_KIND_KEY,
            ),
            TransformativeReactionProfile(
                PYRO_ON_QUICKEN_PROFILE_KEY,
                BURNING_REACTION_KEY,
                PYRO_ON_QUICKEN,
                Element.PYRO,
                BURNING_DAMAGE_PROFILE_KEY,
                DamageElement.PYRO,
                BURNING_DAMAGE_BASE_MULTIPLIER,
                BURNING_GATE_DEFINITION_KEY,
                BURNING_DAMAGE_KIND_KEY,
            ),
            TransformativeReactionProfile(
                DENDRO_ON_PYRO_PROFILE_KEY,
                BURNING_REACTION_KEY,
                DENDRO_ON_PYRO,
                Element.DENDRO,
                BURNING_DAMAGE_PROFILE_KEY,
                DamageElement.PYRO,
                BURNING_DAMAGE_BASE_MULTIPLIER,
                BURNING_GATE_DEFINITION_KEY,
                BURNING_DAMAGE_KIND_KEY,
            ),
        ),
        BurningRule(),
    )


def _amount_for(request: ReactionEvaluationRequest, aura_kind: AuraKind) -> AuraAmount:
    component = request.observed_aura.component_for(aura_kind)
    return AuraAmount.zero() if component is None else component.current_amount


def burning_damage_profile() -> DamageProfile:
    """普通燃烧使用的剧变伤害 Profile。"""

    return DamageProfile(
        profile_key=BURNING_DAMAGE_PROFILE_KEY,
        damage_type=DamageType.TRANSFORMATIVE_REACTION,
        main_attack_tags=frozenset({BURNING_REACTION_KEY}),
    )


def burning_pyro_aura_application_profile() -> AuraApplicationProfile:
    """燃烧周期火使用的普通持久 Aura 附着 Profile。"""

    return AuraApplicationProfile(
        profile_key=BURNING_PYRO_AURA_APPLICATION_PROFILE_KEY,
        decay_profile_policy=AuraDecayProfilePolicy.REGULAR_FROM_RAW_AMOUNT,
    )


def burning_gate_definitions() -> tuple[ReactionDamageGateDefinition, ...]:
    """每个来源、目标与燃烧伤害种类独立的 120 帧伤害窗口。"""

    return (
        ReactionDamageGateDefinition(
            BURNING_GATE_DEFINITION_KEY,
            BURNING_DAMAGE_KIND_KEY,
            BURNING_DAMAGE_WINDOW_FRAMES,
            BURNING_DAMAGE_MAX_INSTANCES,
        ),
    )
