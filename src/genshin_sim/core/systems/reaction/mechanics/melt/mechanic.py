"""普通融化的两个明确方向。"""

from __future__ import annotations

from genshin_sim.core.elements import AuraAmount, AuraKind, Element
from genshin_sim.core.systems.reaction.models import (
    AmplifyingReactionProfile,
    CurrentImpactDamageAdjustment,
    ElementalTransitionEffect,
    ReactionDefinition,
    ReactionEvaluationRequest,
    ReactionOccurrence,
    ReactionProfile,
    ReactionResolution,
    ReactionTriggerSignature,
)

MELT_REACTION_KEY = "reaction.melt"
MELT_HANDLER_KEY = "reaction_handler.melt"
PYRO_ON_CRYO = "incoming_pyro_on_cryo"
CRYO_ON_PYRO = "incoming_cryo_on_pyro"


class MeltRule:
    def evaluate(
        self,
        request: ReactionEvaluationRequest,
        definition: ReactionDefinition,
    ) -> ReactionResolution | None:
        if request.incoming_element is Element.PYRO:
            aura_kind = AuraKind.CRYO
            direction = PYRO_ON_CRYO
            incoming_used = request.incoming_amount.minimum(
                _amount_for(request, aura_kind) / AuraAmount(2)
            )
            aura_used = incoming_used * AuraAmount(2)
        elif request.incoming_element is Element.CRYO:
            aura_kind = AuraKind.PYRO
            direction = CRYO_ON_PYRO
            incoming_used = request.incoming_amount.minimum(
                _amount_for(request, aura_kind) * AuraAmount(2)
            )
            aura_used = incoming_used / AuraAmount(2)
        else:
            return None
        aura_before = _amount_for(request, aura_kind)
        if aura_before.is_zero or incoming_used.is_zero:
            return None
        profile = definition.profile_for(direction)
        if not isinstance(profile, AmplifyingReactionProfile):
            raise ValueError("融化方向必须使用 AmplifyingReactionProfile")
        transition = ElementalTransitionEffect(
            aura_kind,
            request.incoming_amount,
            incoming_used,
            request.incoming_amount - incoming_used,
            aura_before,
            aura_used,
            aura_before - aura_used,
        )
        occurrence = ReactionOccurrence(
            f"{request.interaction_id}:occurrence:{request.order}",
            request.interaction_id,
            definition.reaction_key,
            direction,
            profile.profile_key,
            request.source_ref,
            request.subject_ref,
            transition,
        )
        adjustment = None
        if request.current_damage_element is request.incoming_element:
            adjustment = CurrentImpactDamageAdjustment(
                request.target_impact_ref,
                occurrence.occurrence_ref,
                profile.profile_key,
                request.incoming_element,
                profile.base_multiplier,
            )
        return ReactionResolution(request, occurrence, adjustment)


def melt_definition() -> ReactionDefinition:
    return ReactionDefinition(
        MELT_REACTION_KEY,
        MELT_HANDLER_KEY,
        (
            ReactionTriggerSignature(Element.PYRO, AuraKind.CRYO, PYRO_ON_CRYO),
            ReactionTriggerSignature(Element.CRYO, AuraKind.PYRO, CRYO_ON_PYRO),
        ),
        (
            ReactionProfile(
                "reaction_profile.melt.incoming_pyro_on_cryo",
                MELT_REACTION_KEY,
                PYRO_ON_CRYO,
                Element.PYRO,
                2.0,
            ),
            ReactionProfile(
                "reaction_profile.melt.incoming_cryo_on_pyro",
                MELT_REACTION_KEY,
                CRYO_ON_PYRO,
                Element.CRYO,
                1.5,
            ),
        ),
        MeltRule(),
    )


def _amount_for(request: ReactionEvaluationRequest, aura_kind: AuraKind) -> AuraAmount:
    component = request.observed_aura.component_for(aura_kind)
    return AuraAmount.zero() if component is None else component.current_amount
