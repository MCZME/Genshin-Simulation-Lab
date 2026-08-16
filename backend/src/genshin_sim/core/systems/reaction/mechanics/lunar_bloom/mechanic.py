"""独立月绽放反应的候选、草原核与草露资源计划。"""

from __future__ import annotations

from genshin_sim.core.elements import AuraKind, Element
from genshin_sim.core.systems.damage import DamageProfile, DamageType
from genshin_sim.core.systems.reaction.mechanics.dendro_core import (
    DENDRO_CORE_SPATIAL_PROFILE_KEY,
    DENDRO_CORE_STATE_KEY,
    plan_dendro_core_creation,
)
from genshin_sim.core.systems.reaction.mechanics.lunar_bloom.keys import (
    LUNAR_BLOOM_CAPABILITY_KEY,
    LUNAR_BLOOM_DAMAGE_PROFILE_KEY,
    LUNAR_BLOOM_DENDRO_ON_HYDRO_PROFILE_KEY,
    LUNAR_BLOOM_HANDLER_KEY,
    LUNAR_BLOOM_HYDRO_ON_DENDRO_PROFILE_KEY,
    LUNAR_BLOOM_REACTION_KEY,
    LUNAR_DENDRO_ON_HYDRO,
    LUNAR_HYDRO_ON_DENDRO,
)
from genshin_sim.core.systems.reaction.models import (
    LunarBloomReactionProfile,
    ReactionDecisionSequence,
    ReactionDecisionStep,
    ReactionDefinition,
    ReactionEvaluationRequest,
    ReactionOccurrence,
    ReactionResolution,
    ReactionTriggerSignature,
)
from genshin_sim.core.systems.reaction.participants import freeze_character_participants


class LunarBloomRule:
    """只在角色触发、严格水草签名和队伍准入同时成立时匹配。"""

    def evaluate(
        self,
        request: ReactionEvaluationRequest,
        definition: ReactionDefinition,
    ) -> ReactionResolution | None:
        if LUNAR_BLOOM_CAPABILITY_KEY not in request.reaction_capability_keys:
            return None
        if not any(
            item.source_key == request.source_ref.source_key
            for item in request.character_source_refs
        ):
            return None
        direction, aura_kind = _direction_for(request)
        if direction is None or aura_kind is None:
            return None
        profile = definition.profile_for(direction)
        if not isinstance(profile, LunarBloomReactionProfile):
            raise ValueError("月绽放方向必须使用 LunarBloomReactionProfile")
        participants = freeze_character_participants(
            request.observed_aura,
            used_aura_kinds=(aura_kind,),
            character_source_refs=request.character_source_refs,
            triggering_source_ref=request.source_ref,
        )
        core_plan = plan_dendro_core_creation(
            request,
            aura_kind=aura_kind,
            profile=profile,
        )
        if core_plan is None:
            return None

        occurrence = ReactionOccurrence(
            occurrence_ref=core_plan.occurrence_ref,
            interaction_id=request.interaction_id,
            reaction_key=definition.reaction_key,
            direction_key=direction,
            profile_key=profile.profile_key,
            source_ref=request.source_ref,
            subject_ref=request.subject_ref,
            transition=core_plan.transition,
            participant_refs=participants.participant_refs,
            dendro_core_state_creation=core_plan.state_creation,
            spatial_entity_creation=core_plan.spatial_creation,
        )
        return ReactionResolution(
            request,
            occurrence,
            None,
            ReactionDecisionSequence(
                (
                    ReactionDecisionStep(
                        0,
                        (definition.reaction_key,),
                        (core_plan.transition,),
                        (),
                        (occurrence,),
                    ),
                )
            ),
        )


def lunar_bloom_definition() -> ReactionDefinition:
    return ReactionDefinition(
        LUNAR_BLOOM_REACTION_KEY,
        LUNAR_BLOOM_HANDLER_KEY,
        (
            ReactionTriggerSignature(Element.HYDRO, AuraKind.DENDRO, LUNAR_HYDRO_ON_DENDRO),
            ReactionTriggerSignature(Element.DENDRO, AuraKind.HYDRO, LUNAR_DENDRO_ON_HYDRO),
        ),
        (
            LunarBloomReactionProfile(
                LUNAR_BLOOM_HYDRO_ON_DENDRO_PROFILE_KEY,
                LUNAR_BLOOM_REACTION_KEY,
                LUNAR_HYDRO_ON_DENDRO,
                Element.HYDRO,
                AuraKind.DENDRO,
                DENDRO_CORE_STATE_KEY,
                DENDRO_CORE_SPATIAL_PROFILE_KEY,
            ),
            LunarBloomReactionProfile(
                LUNAR_BLOOM_DENDRO_ON_HYDRO_PROFILE_KEY,
                LUNAR_BLOOM_REACTION_KEY,
                LUNAR_DENDRO_ON_HYDRO,
                Element.DENDRO,
                AuraKind.HYDRO,
                DENDRO_CORE_STATE_KEY,
                DENDRO_CORE_SPATIAL_PROFILE_KEY,
            ),
        ),
        LunarBloomRule(),
        selection_priority=100,
    )


def lunar_bloom_damage_profiles() -> tuple[DamageProfile, ...]:
    return (
        DamageProfile(
            LUNAR_BLOOM_DAMAGE_PROFILE_KEY,
            DamageType.LUNAR_REACTION,
            frozenset({LUNAR_BLOOM_REACTION_KEY}),
        ),
    )


def _direction_for(
    request: ReactionEvaluationRequest,
) -> tuple[str | None, AuraKind | None]:
    if request.incoming_element is Element.HYDRO:
        component = request.observed_aura.component_for(AuraKind.DENDRO)
        if component is not None and not component.current_amount.is_zero:
            return LUNAR_HYDRO_ON_DENDRO, AuraKind.DENDRO
    elif request.incoming_element is Element.DENDRO:
        component = request.observed_aura.component_for(AuraKind.HYDRO)
        if component is not None and not component.current_amount.is_zero:
            return LUNAR_DENDRO_ON_HYDRO, AuraKind.HYDRO
    return None, None
