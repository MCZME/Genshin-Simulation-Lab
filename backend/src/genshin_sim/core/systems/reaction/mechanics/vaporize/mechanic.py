"""普通蒸发的两个明确方向。"""

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

VAPORIZE_REACTION_KEY = "reaction.vaporize"
VAPORIZE_HANDLER_KEY = "reaction_handler.vaporize"
HYDRO_ON_PYRO = "incoming_hydro_on_pyro"
PYRO_ON_HYDRO = "incoming_pyro_on_hydro"


class VaporizeRule:
    def evaluate(
        self,
        request: ReactionEvaluationRequest,
        definition: ReactionDefinition,
    ) -> ReactionResolution | None:
        if request.incoming_element is Element.HYDRO:
            aura_kind = AuraKind.PYRO
            direction = HYDRO_ON_PYRO
            incoming_used = request.incoming_amount.minimum(
                _amount_for(request, aura_kind) / AuraAmount(2)
            )
            aura_used = incoming_used * AuraAmount(2)
        elif request.incoming_element is Element.PYRO:
            aura_kind = AuraKind.HYDRO
            direction = PYRO_ON_HYDRO
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
            raise ValueError("蒸发方向必须使用 AmplifyingReactionProfile")
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


def vaporize_definition() -> ReactionDefinition:
    return ReactionDefinition(
        VAPORIZE_REACTION_KEY,
        VAPORIZE_HANDLER_KEY,
        (
            ReactionTriggerSignature(Element.HYDRO, AuraKind.PYRO, HYDRO_ON_PYRO),
            ReactionTriggerSignature(Element.PYRO, AuraKind.HYDRO, PYRO_ON_HYDRO),
        ),
        (
            ReactionProfile(
                "reaction_profile.vaporize.incoming_hydro_on_pyro",
                VAPORIZE_REACTION_KEY,
                HYDRO_ON_PYRO,
                Element.HYDRO,
                2.0,
            ),
            ReactionProfile(
                "reaction_profile.vaporize.incoming_pyro_on_hydro",
                VAPORIZE_REACTION_KEY,
                PYRO_ON_HYDRO,
                Element.PYRO,
                1.5,
            ),
        ),
        VaporizeRule(),
    )


def _amount_for(request: ReactionEvaluationRequest, aura_kind: AuraKind) -> AuraAmount:
    component = request.observed_aura.component_for(aura_kind)
    return AuraAmount.zero() if component is None else component.current_amount
