"""普通冻结的两个水冰方向；派生 Aura/State 由协调器原子提交。"""

from __future__ import annotations

from genshin_sim.core.elements import AuraAmount, AuraKind, Element
from genshin_sim.core.systems.reaction.mechanics.frozen.keys import (
    CRYO_ON_HYDRO,
    CRYO_ON_HYDRO_PROFILE_KEY,
    FROZEN_HANDLER_KEY,
    FROZEN_REACTION_KEY,
    HYDRO_ON_CRYO,
    HYDRO_ON_CRYO_PROFILE_KEY,
)
from genshin_sim.core.systems.reaction.models import (
    ElementalTransitionEffect,
    ReactionDefinition,
    ReactionEvaluationRequest,
    ReactionOccurrence,
    ReactionResolution,
    ReactionTriggerSignature,
    StateReactionProfile,
)


class FrozenRule:
    def evaluate(
        self,
        request: ReactionEvaluationRequest,
        definition: ReactionDefinition,
    ) -> ReactionResolution | None:
        if request.incoming_element is Element.HYDRO:
            aura_kind = AuraKind.CRYO
            direction = HYDRO_ON_CRYO
        elif request.incoming_element is Element.CRYO:
            aura_kind = AuraKind.HYDRO
            direction = CRYO_ON_HYDRO
        else:
            return None
        aura_before = _amount_for(request, aura_kind)
        reaction_amount = request.incoming_amount.minimum(aura_before)
        if reaction_amount.is_zero:
            return None
        profile = definition.profile_for(direction)
        if not isinstance(profile, StateReactionProfile):
            raise ValueError("冻结方向必须使用 StateReactionProfile")
        occurrence_ref = f"{request.interaction_id}:occurrence:{request.order}"
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
                incoming_consumed=reaction_amount,
                incoming_remaining=request.incoming_amount - reaction_amount,
                aura_before=aura_before,
                aura_consumed=reaction_amount,
                aura_remaining=aura_before - reaction_amount,
            ),
        )
        return ReactionResolution(request, occurrence, None)


def frozen_definition() -> ReactionDefinition:
    return ReactionDefinition(
        FROZEN_REACTION_KEY,
        FROZEN_HANDLER_KEY,
        (
            ReactionTriggerSignature(Element.HYDRO, AuraKind.CRYO, HYDRO_ON_CRYO),
            ReactionTriggerSignature(Element.CRYO, AuraKind.HYDRO, CRYO_ON_HYDRO),
        ),
        (
            StateReactionProfile(
                HYDRO_ON_CRYO_PROFILE_KEY,
                FROZEN_REACTION_KEY,
                HYDRO_ON_CRYO,
                Element.HYDRO,
            ),
            StateReactionProfile(
                CRYO_ON_HYDRO_PROFILE_KEY,
                FROZEN_REACTION_KEY,
                CRYO_ON_HYDRO,
                Element.CRYO,
            ),
        ),
        FrozenRule(),
    )


def _amount_for(request: ReactionEvaluationRequest, aura_kind: AuraKind) -> AuraAmount:
    component = request.observed_aura.component_for(aura_kind)
    return AuraAmount.zero() if component is None else component.current_amount
