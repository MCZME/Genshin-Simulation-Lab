"""星超导候选：满足资格时替代普通超导，并声明极星辉域。"""

from __future__ import annotations

from genshin_sim.core.elements import AuraKind, Element
from genshin_sim.core.systems.reaction.mechanics.stellar_conduct.keys import (
    STELLAR_CONDUCT_CAPABILITY_KEY,
    STELLAR_CONDUCT_CRYO_ON_ELECTRO_PROFILE_KEY,
    STELLAR_CONDUCT_ELECTRO_ON_CRYO_PROFILE_KEY,
    STELLAR_CONDUCT_FIELD_SPATIAL_PROFILE_KEY,
    STELLAR_CONDUCT_FIELD_STATE_KEY,
    STELLAR_CONDUCT_HANDLER_KEY,
    STELLAR_CONDUCT_INCOMING_CRYO_ON_ELECTRO,
    STELLAR_CONDUCT_INCOMING_ELECTRO_ON_CRYO,
    STELLAR_CONDUCT_REACTION_KEY,
    STELLAR_CONDUCT_TEAM_SCOPE,
)
from genshin_sim.core.systems.reaction.models import (
    ElementalTransitionEffect,
    PolestarFieldStatePlanningIntent,
    ReactionDefinition,
    ReactionEvaluationRequest,
    ReactionOccurrence,
    ReactionResolution,
    ReactionTriggerSignature,
    SpatialEntityCreationEffect,
    StateReactionProfile,
)
from genshin_sim.core.systems.reaction.states import (
    STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES,
    ReactionStateInstanceRef,
)


def stellar_conduct_direct_multiplier(stacks: int) -> float:
    """按 4 秒周期层数计算直伤星烁基础系数。"""
    if isinstance(stacks, bool) or not isinstance(stacks, int) or stacks < 0:
        raise ValueError("stacks 必须是非负整数")
    return 1.0 if stacks == 0 else min(1.4 + 0.05 * stacks, 2.0)


def stellar_conduct_elemental_bonus(stacks: int) -> float:
    """按层数返回领域内冰/雷普通伤害增益。"""
    if isinstance(stacks, bool) or not isinstance(stacks, int) or stacks < 0:
        raise ValueError("stacks 必须是非负整数")
    return 0.20 if stacks == 0 else min(0.28 + 0.01 * stacks, 0.40)


class StellarConductRule:
    def evaluate(
        self, request: ReactionEvaluationRequest, definition: ReactionDefinition
    ) -> ReactionResolution | None:
        if STELLAR_CONDUCT_CAPABILITY_KEY not in request.reaction_capability_keys:
            return None
        if not any(
            item.source_key == request.source_ref.source_key
            for item in request.character_source_refs
        ):
            return None
        if request.incoming_element is Element.CRYO:
            aura_kind, direction = AuraKind.ELECTRO, STELLAR_CONDUCT_INCOMING_CRYO_ON_ELECTRO
        elif request.incoming_element is Element.ELECTRO:
            aura_kind, direction = AuraKind.CRYO, STELLAR_CONDUCT_INCOMING_ELECTRO_ON_CRYO
        else:
            return None
        aura = request.observed_aura.component_for(aura_kind)
        if aura is None or aura.current_amount.is_zero:
            return None
        profile = definition.profile_for(direction)
        if not isinstance(profile, StateReactionProfile):
            raise ValueError("星超导方向必须使用 ReactionStateProfile")
        consumed = request.incoming_amount.minimum(aura.current_amount)
        occurrence_ref = f"{request.interaction_id}:occurrence:{request.order}"
        instance_ref = ReactionStateInstanceRef(f"reaction-state:polestar-field:{occurrence_ref}")
        spatial_ref = f"reaction_object:polestar_field:{occurrence_ref}"
        field_planning = PolestarFieldStatePlanningIntent(
            intent_ref=f"{occurrence_ref}:polestar-field-plan",
            parent_occurrence_ref=occurrence_ref,
            instance_ref=instance_ref,
            subject_ref=request.subject_ref,
            space_entity_ref=spatial_ref,
            trigger_source_ref=request.source_ref,
            team_ref=STELLAR_CONDUCT_TEAM_SCOPE,
            created_frame=request.frame,
            expires_at_frame=request.frame + STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES,
            excluded_attack_ref=request.target_impact_ref,
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
                incoming_consumed=consumed,
                incoming_remaining=request.incoming_amount - consumed,
                aura_before=aura.current_amount,
                aura_consumed=consumed,
                aura_remaining=aura.current_amount - consumed,
            ),
            polestar_field_state_planning=field_planning,
            spatial_entity_creation=SpatialEntityCreationEffect(
                effect_ref=f"{occurrence_ref}:polestar-field-spatial-create",
                parent_occurrence_ref=occurrence_ref,
                space_entity_ref=spatial_ref,
                owner_key=STELLAR_CONDUCT_TEAM_SCOPE,
                source_key=instance_ref.value,
                tags=(STELLAR_CONDUCT_FIELD_STATE_KEY, STELLAR_CONDUCT_FIELD_SPATIAL_PROFILE_KEY),
                created_frame=request.frame,
                expires_at_frame=request.frame + STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES,
            ),
        )
        return ReactionResolution(request, occurrence, None)


def stellar_conduct_definition() -> ReactionDefinition:
    return ReactionDefinition(
        STELLAR_CONDUCT_REACTION_KEY,
        STELLAR_CONDUCT_HANDLER_KEY,
        (
            ReactionTriggerSignature(
                Element.CRYO, AuraKind.ELECTRO, STELLAR_CONDUCT_INCOMING_CRYO_ON_ELECTRO
            ),
            ReactionTriggerSignature(
                Element.ELECTRO, AuraKind.CRYO, STELLAR_CONDUCT_INCOMING_ELECTRO_ON_CRYO
            ),
        ),
        (
            StateReactionProfile(
                STELLAR_CONDUCT_CRYO_ON_ELECTRO_PROFILE_KEY,
                STELLAR_CONDUCT_REACTION_KEY,
                STELLAR_CONDUCT_INCOMING_CRYO_ON_ELECTRO,
                Element.CRYO,
            ),
            StateReactionProfile(
                STELLAR_CONDUCT_ELECTRO_ON_CRYO_PROFILE_KEY,
                STELLAR_CONDUCT_REACTION_KEY,
                STELLAR_CONDUCT_INCOMING_ELECTRO_ON_CRYO,
                Element.ELECTRO,
            ),
        ),
        StellarConductRule(),
        selection_priority=110,
    )
