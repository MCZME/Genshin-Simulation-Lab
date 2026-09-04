"""月结晶的水岩严格候选与月笼/累计器规划意图声明。"""

from __future__ import annotations

from genshin_sim.core.elements import AuraKind, Element
from genshin_sim.core.systems.damage import DamageProfile
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_LUNAR_REACTION
from genshin_sim.core.systems.reaction.mechanics.lunar_crystallize.keys import (
    LUNAR_CAGE_COUNT,
    LUNAR_CAGE_SPATIAL_PROFILE_KEY,
    LUNAR_CAGE_STATE_KEY,
    LUNAR_CAGE_TEAM_SCOPE,
    LUNAR_CRYSTALLIZE_CAPABILITY_KEY,
    LUNAR_CRYSTALLIZE_DAMAGE_KIND_KEY,
    LUNAR_CRYSTALLIZE_GEO_ON_HYDRO_PROFILE_KEY,
    LUNAR_CRYSTALLIZE_HANDLER_KEY,
    LUNAR_CRYSTALLIZE_REACTION_KEY,
    LUNAR_INCOMING_GEO_ON_HYDRO,
)
from genshin_sim.core.systems.reaction.models import (
    ElementalTransitionEffect,
    LunarCrystallizeReactionProfile,
    LunarCrystallizeStatePlanningIntent,
    ReactionDefinition,
    ReactionEvaluationRequest,
    ReactionOccurrence,
    ReactionResolution,
    ReactionTriggerSignature,
)
from genshin_sim.core.systems.reaction.participants import freeze_character_participants
from genshin_sim.core.systems.reaction.states import ReactionStateInstanceRef


class LunarCrystallizeRule:
    """只在角色触发、严格水岩签名和队伍准入同时成立时匹配。"""

    def evaluate(
        self,
        request: ReactionEvaluationRequest,
        definition: ReactionDefinition,
    ) -> ReactionResolution | None:
        if LUNAR_CRYSTALLIZE_CAPABILITY_KEY not in request.reaction_capability_keys:
            return None
        if not any(
            item.source_key == request.source_ref.source_key
            for item in request.character_source_refs
        ):
            return None
        if request.incoming_element is not Element.GEO:
            return None
        if (
            request.has_active_frozen_state
            or request.observed_aura.component_for(AuraKind.FROZEN) is not None
        ):
            return None
        hydro = request.observed_aura.component_for(AuraKind.HYDRO)
        if hydro is None or hydro.current_amount.is_zero:
            return None
        profile = definition.profile_for(LUNAR_INCOMING_GEO_ON_HYDRO)
        if not isinstance(profile, LunarCrystallizeReactionProfile):
            raise ValueError("月结晶方向必须使用 LunarCrystallizeReactionProfile")
        participants = freeze_character_participants(
            request.observed_aura,
            used_aura_kinds=(AuraKind.HYDRO,),
            character_source_refs=request.character_source_refs,
            triggering_source_ref=request.source_ref,
        )
        geo_consumed = request.incoming_amount.minimum(hydro.current_amount * 2)
        if geo_consumed.is_zero:
            return None
        aura_consumed = geo_consumed / 2
        occurrence_ref = f"{request.interaction_id}:occurrence:{request.order}"
        cage_instance_refs = tuple(
            ReactionStateInstanceRef(f"reaction-state:lunar-cage:{occurrence_ref}:{index}")
            for index in range(LUNAR_CAGE_COUNT)
        )
        cage_space_entity_refs = tuple(
            f"reaction_object:lunar_cage:{occurrence_ref}:{index}"
            for index in range(LUNAR_CAGE_COUNT)
        )
        intent = LunarCrystallizeStatePlanningIntent(
            intent_ref=f"{occurrence_ref}:lunar-crystallize-plan",
            parent_occurrence_ref=occurrence_ref,
            subject_ref=request.subject_ref,
            team_ref=LUNAR_CAGE_TEAM_SCOPE,
            trigger_source_ref=request.source_ref,
            participant_refs=participants.participant_refs,
            created_frame=request.frame,
            order=request.order,
            cage_instance_refs=cage_instance_refs,
            cage_space_entity_refs=cage_space_entity_refs,
        )
        occurrence = ReactionOccurrence(
            occurrence_ref=occurrence_ref,
            interaction_id=request.interaction_id,
            reaction_key=definition.reaction_key,
            direction_key=LUNAR_INCOMING_GEO_ON_HYDRO,
            profile_key=profile.profile_key,
            source_ref=request.source_ref,
            subject_ref=request.subject_ref,
            transition=ElementalTransitionEffect(
                aura_kind=AuraKind.HYDRO,
                incoming_before=request.incoming_amount,
                incoming_consumed=geo_consumed,
                incoming_remaining=request.incoming_amount - geo_consumed,
                aura_before=hydro.current_amount,
                aura_consumed=aura_consumed,
                aura_remaining=hydro.current_amount - aura_consumed,
            ),
            participant_refs=participants.participant_refs,
            lunar_crystallize_planning=intent,
        )
        return ReactionResolution(request, occurrence, None)


def lunar_crystallize_definition() -> ReactionDefinition:
    return ReactionDefinition(
        LUNAR_CRYSTALLIZE_REACTION_KEY,
        LUNAR_CRYSTALLIZE_HANDLER_KEY,
        (
            ReactionTriggerSignature(
                Element.GEO,
                AuraKind.HYDRO,
                LUNAR_INCOMING_GEO_ON_HYDRO,
            ),
        ),
        (
            LunarCrystallizeReactionProfile(
                LUNAR_CRYSTALLIZE_GEO_ON_HYDRO_PROFILE_KEY,
                LUNAR_CRYSTALLIZE_REACTION_KEY,
                LUNAR_INCOMING_GEO_ON_HYDRO,
                Element.GEO,
                LUNAR_CAGE_STATE_KEY,
                LUNAR_CAGE_SPATIAL_PROFILE_KEY,
            ),
        ),
        LunarCrystallizeRule(),
        selection_priority=100,
    )


def lunar_crystallize_damage_profiles() -> tuple[DamageProfile, ...]:
    return (
        DamageProfile(
            formula_key=FORMULA_KEY_LUNAR_REACTION,
            main_attack_tags=frozenset({LUNAR_CRYSTALLIZE_REACTION_KEY}),
        ),
    )


__all__ = (
    "LUNAR_CRYSTALLIZE_DAMAGE_KIND_KEY",
    "LunarCrystallizeRule",
    "lunar_crystallize_definition",
    "lunar_crystallize_damage_profiles",
)
