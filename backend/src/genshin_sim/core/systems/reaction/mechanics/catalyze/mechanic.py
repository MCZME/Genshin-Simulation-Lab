"""原激化、超激化与蔓激化的生产 Definition 与 Rule。"""

from __future__ import annotations

from genshin_sim.core.elements import AuraAmount, AuraKind, Element, ElementalStateLinkRef
from genshin_sim.core.systems.reaction.models import (
    AdditiveReactionProfile,
    CatalyzeCurrentImpactDamageAdjustment,
    ElementalTransitionEffect,
    QuickenStateCoverageIntent,
    QuickenStateEstablishmentIntent,
    ReactionDecisionSequence,
    ReactionDecisionStep,
    ReactionDefinition,
    ReactionEvaluationRequest,
    ReactionOccurrence,
    ReactionResolution,
    ReactionTriggerSignature,
    StateReactionProfile,
)

QUICKEN_REACTION_KEY = "reaction.quicken"
QUICKEN_HANDLER_KEY = "reaction_handler.quicken"
AGGRAVATE_REACTION_KEY = "reaction.aggravate"
AGGRAVATE_HANDLER_KEY = "reaction_handler.aggravate"
SPREAD_REACTION_KEY = "reaction.spread"
SPREAD_HANDLER_KEY = "reaction_handler.spread"

ELECTRO_ON_DENDRO = "incoming_electro_on_dendro"
DENDRO_ON_ELECTRO = "incoming_dendro_on_electro"
ELECTRO_ON_QUICKEN = "incoming_electro_on_quicken"
DENDRO_ON_QUICKEN = "incoming_dendro_on_quicken"

QUICKEN_ELECTRO_ON_DENDRO_PROFILE_KEY = "reaction_profile.quicken.incoming_electro_on_dendro"
QUICKEN_DENDRO_ON_ELECTRO_PROFILE_KEY = "reaction_profile.quicken.incoming_dendro_on_electro"
AGGRAVATE_PROFILE_KEY = "reaction_profile.aggravate.incoming_electro_on_quicken"
SPREAD_PROFILE_KEY = "reaction_profile.spread.incoming_dendro_on_quicken"
AGGRAVATE_MULTIPLIER = 1.15
SPREAD_MULTIPLIER = 1.25


class QuickenRule:
    def evaluate(
        self,
        request: ReactionEvaluationRequest,
        definition: ReactionDefinition,
    ) -> ReactionResolution | None:
        if request.incoming_element is Element.ELECTRO:
            aura_kind = AuraKind.DENDRO
            direction = ELECTRO_ON_DENDRO
        elif request.incoming_element is Element.DENDRO:
            aura_kind = AuraKind.ELECTRO
            direction = DENDRO_ON_ELECTRO
        else:
            return None
        aura_before = _amount_for(request, aura_kind)
        reaction_amount = request.incoming_amount.minimum(aura_before)
        if reaction_amount.is_zero:
            return None
        profile = definition.profile_for(direction)
        if not isinstance(profile, StateReactionProfile):
            raise ValueError("原激化方向必须使用 StateReactionProfile")
        occurrence_ref = f"{request.interaction_id}:occurrence:{request.order}"
        transition = ElementalTransitionEffect(
            aura_kind=aura_kind,
            incoming_before=request.incoming_amount,
            incoming_consumed=reaction_amount,
            incoming_remaining=request.incoming_amount - reaction_amount,
            aura_before=aura_before,
            aura_consumed=reaction_amount,
            aura_remaining=aura_before - reaction_amount,
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
        )
        current = request.observed_quicken_state
        if current is None:
            link_ref = ElementalStateLinkRef(f"elemental-state-link:quicken:{occurrence_ref}")
            intent = QuickenStateEstablishmentIntent(
                intent_ref=f"{occurrence_ref}:quicken-establishment",
                subject_ref=request.subject_ref,
                occurrence_ref=occurrence_ref,
                frame=request.frame,
                quicken_aura_link_ref=link_ref,
            )
        else:
            intent = QuickenStateCoverageIntent(
                intent_ref=f"{occurrence_ref}:quicken-coverage",
                subject_ref=request.subject_ref,
                occurrence_ref=occurrence_ref,
                frame=request.frame,
                expected_state_instance_ref=current.instance_ref,
                expected_state_revision=current.revision,
                quicken_aura_link_ref=current.quicken_aura_link_ref,
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


class AggravateRule:
    def evaluate(
        self,
        request: ReactionEvaluationRequest,
        definition: ReactionDefinition,
    ) -> ReactionResolution | None:
        return _evaluate_additive(
            request,
            definition,
            trigger_element=Element.ELECTRO,
            direction=ELECTRO_ON_QUICKEN,
            reaction_multiplier=AGGRAVATE_MULTIPLIER,
        )


class SpreadRule:
    def evaluate(
        self,
        request: ReactionEvaluationRequest,
        definition: ReactionDefinition,
    ) -> ReactionResolution | None:
        return _evaluate_additive(
            request,
            definition,
            trigger_element=Element.DENDRO,
            direction=DENDRO_ON_QUICKEN,
            reaction_multiplier=SPREAD_MULTIPLIER,
        )


def quicken_definition() -> ReactionDefinition:
    return ReactionDefinition(
        QUICKEN_REACTION_KEY,
        QUICKEN_HANDLER_KEY,
        (
            ReactionTriggerSignature(Element.ELECTRO, AuraKind.DENDRO, ELECTRO_ON_DENDRO),
            ReactionTriggerSignature(Element.DENDRO, AuraKind.ELECTRO, DENDRO_ON_ELECTRO),
        ),
        (
            StateReactionProfile(
                QUICKEN_ELECTRO_ON_DENDRO_PROFILE_KEY,
                QUICKEN_REACTION_KEY,
                ELECTRO_ON_DENDRO,
                Element.ELECTRO,
            ),
            StateReactionProfile(
                QUICKEN_DENDRO_ON_ELECTRO_PROFILE_KEY,
                QUICKEN_REACTION_KEY,
                DENDRO_ON_ELECTRO,
                Element.DENDRO,
            ),
        ),
        QuickenRule(),
    )


def aggravate_definition() -> ReactionDefinition:
    return ReactionDefinition(
        AGGRAVATE_REACTION_KEY,
        AGGRAVATE_HANDLER_KEY,
        (ReactionTriggerSignature(Element.ELECTRO, AuraKind.QUICKEN, ELECTRO_ON_QUICKEN),),
        (
            AdditiveReactionProfile(
                AGGRAVATE_PROFILE_KEY,
                AGGRAVATE_REACTION_KEY,
                ELECTRO_ON_QUICKEN,
                Element.ELECTRO,
                AGGRAVATE_MULTIPLIER,
            ),
        ),
        AggravateRule(),
    )


def spread_definition() -> ReactionDefinition:
    return ReactionDefinition(
        SPREAD_REACTION_KEY,
        SPREAD_HANDLER_KEY,
        (ReactionTriggerSignature(Element.DENDRO, AuraKind.QUICKEN, DENDRO_ON_QUICKEN),),
        (
            AdditiveReactionProfile(
                SPREAD_PROFILE_KEY,
                SPREAD_REACTION_KEY,
                DENDRO_ON_QUICKEN,
                Element.DENDRO,
                SPREAD_MULTIPLIER,
            ),
        ),
        SpreadRule(),
    )


def _evaluate_additive(
    request: ReactionEvaluationRequest,
    definition: ReactionDefinition,
    *,
    trigger_element: Element,
    direction: str,
    reaction_multiplier: float,
) -> ReactionResolution | None:
    if request.incoming_element is not trigger_element or request.incoming_amount.is_zero:
        return None
    quicken_before = _amount_for(request, AuraKind.QUICKEN)
    if quicken_before.is_zero or request.observed_quicken_state is None:
        return None
    if not _has_additive_damage_qualification(request, trigger_element):
        return None
    profile = definition.profile_for(direction)
    if not isinstance(profile, AdditiveReactionProfile):
        raise ValueError("附加激化方向必须使用 AdditiveReactionProfile")
    occurrence_ref = f"{request.interaction_id}:occurrence:{request.order}"
    transition = ElementalTransitionEffect(
        aura_kind=AuraKind.QUICKEN,
        incoming_before=request.incoming_amount,
        incoming_consumed=AuraAmount.zero(),
        incoming_remaining=request.incoming_amount,
        aura_before=quicken_before,
        aura_consumed=AuraAmount.zero(),
        aura_remaining=quicken_before,
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
    )
    adjustment = CatalyzeCurrentImpactDamageAdjustment(
        adjustment_ref=f"{occurrence_ref}:catalyze-adjustment",
        target_impact_ref=request.target_impact_ref,
        occurrence_ref=occurrence_ref,
        reaction_profile_key=profile.profile_key,
        trigger_element=trigger_element,
        reaction_multiplier=reaction_multiplier,
        reaction_bonus=0.0,
    )
    return ReactionResolution(
        request,
        occurrence,
        adjustment,
        decision_sequence=ReactionDecisionSequence(
            (
                ReactionDecisionStep(
                    0,
                    (definition.reaction_key,),
                    (transition,),
                    (),
                    (occurrence,),
                ),
            )
        ),
    )


def _has_additive_damage_qualification(
    request: ReactionEvaluationRequest,
    trigger_element: Element,
) -> bool:
    if request.current_damage_element is not trigger_element:
        return False
    qualification = request.catalyze_impact_qualification
    if qualification is None:
        return False
    return (
        qualification.target_impact_ref == request.target_impact_ref
        and qualification.damage_element is trigger_element
        and qualification.has_positive_scaling_coefficient
    )


def _amount_for(request: ReactionEvaluationRequest, aura_kind: AuraKind) -> AuraAmount:
    component = request.observed_aura.component_for(aura_kind)
    return AuraAmount.zero() if component is None else component.current_amount
