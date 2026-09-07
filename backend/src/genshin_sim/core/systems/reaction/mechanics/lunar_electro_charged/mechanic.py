"""月感电的水雷严格候选与雷暴云创建/刷新声明。"""

from __future__ import annotations

from genshin_sim.core.elements import AuraAmount, AuraKind, Element
from genshin_sim.core.systems.damage import DamageProfile
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_LUNAR_REACTION
from genshin_sim.core.systems.reaction.gates import ReactionDamageGateDefinition
from genshin_sim.core.systems.reaction.mechanics.lunar_electro_charged.keys import (
    LUNAR_ELECTRO_CHARGED_CAPABILITY_KEY,
    LUNAR_ELECTRO_CHARGED_DAMAGE_KIND_KEY,
    LUNAR_ELECTRO_CHARGED_ELECTRO_ON_HYDRO_PROFILE_KEY,
    LUNAR_ELECTRO_CHARGED_GATE_DEFINITION_KEY,
    LUNAR_ELECTRO_CHARGED_HANDLER_KEY,
    LUNAR_ELECTRO_CHARGED_HYDRO_ON_ELECTRO_PROFILE_KEY,
    LUNAR_ELECTRO_CHARGED_REACTION_KEY,
    LUNAR_ELECTRO_ON_HYDRO,
    LUNAR_HYDRO_ON_ELECTRO,
    LUNAR_STORM_CLOUD_ATTACK_INTERVAL_FRAMES,
    LUNAR_STORM_CLOUD_FIRST_ATTACK_INTERVAL_FRAMES,
    LUNAR_STORM_CLOUD_LIFETIME_FRAMES,
    LUNAR_STORM_CLOUD_SPATIAL_PROFILE_KEY,
    LUNAR_STORM_CLOUD_STATE_KEY,
    LUNAR_STORM_CLOUD_TEAM_SCOPE,
)
from genshin_sim.core.systems.reaction.models import (
    ElementalTransitionEffect,
    LunarElectroChargedReactionProfile,
    LunarStormCloudStatePlanningIntent,
    PersistentIncomingAuraApplicationEffect,
    ReactionDefinition,
    ReactionEvaluationRequest,
    ReactionOccurrence,
    ReactionResolution,
    ReactionTriggerSignature,
    SpatialEntityCreationEffect,
)
from genshin_sim.core.systems.reaction.participants import freeze_character_participants
from genshin_sim.core.systems.reaction.states import ReactionStateInstanceRef


class LunarElectroChargedRule:
    """只在角色触发、严格水雷签名和队伍准入同时成立时匹配。"""

    def evaluate(
        self,
        request: ReactionEvaluationRequest,
        definition: ReactionDefinition,
    ) -> ReactionResolution | None:
        if LUNAR_ELECTRO_CHARGED_CAPABILITY_KEY not in request.reaction_capability_keys:
            return None
        if not any(
            item.source_key == request.source_ref.source_key
            for item in request.character_source_refs
        ):
            return None
        if request.incoming_element is Element.HYDRO:
            existing_kind = AuraKind.ELECTRO
            direction = LUNAR_HYDRO_ON_ELECTRO
        elif request.incoming_element is Element.ELECTRO:
            existing_kind = AuraKind.HYDRO
            direction = LUNAR_ELECTRO_ON_HYDRO
        else:
            return None
        existing_amount = _amount_for(request, existing_kind)
        if existing_amount.is_zero:
            return None
        profile = definition.profile_for(direction)
        if not isinstance(profile, LunarElectroChargedReactionProfile):
            raise ValueError("月感电方向必须使用 LunarElectroChargedReactionProfile")
        participants = freeze_character_participants(
            request.observed_aura,
            used_aura_kinds=(AuraKind.HYDRO, AuraKind.ELECTRO),
            character_source_refs=request.character_source_refs,
            triggering_source_ref=request.source_ref,
        )
        occurrence_ref = f"{request.interaction_id}:occurrence:{request.order}"
        instance_ref = ReactionStateInstanceRef(
            f"reaction-state:lunar-storm-cloud:{occurrence_ref}"
        )
        space_entity_ref = f"reaction_object:lunar_storm_cloud:{occurrence_ref}"
        intent = LunarStormCloudStatePlanningIntent(
            intent_ref=f"{occurrence_ref}:lunar-storm-cloud-plan",
            parent_occurrence_ref=occurrence_ref,
            instance_ref=instance_ref,
            subject_ref=request.subject_ref,
            space_entity_ref=space_entity_ref,
            trigger_source_ref=request.source_ref,
            team_ref=LUNAR_STORM_CLOUD_TEAM_SCOPE,
            created_frame=request.frame,
            expires_at_frame=request.frame + LUNAR_STORM_CLOUD_LIFETIME_FRAMES,
            first_attack_frame=(request.frame + LUNAR_STORM_CLOUD_FIRST_ATTACK_INTERVAL_FRAMES),
            attack_interval_frames=LUNAR_STORM_CLOUD_ATTACK_INTERVAL_FRAMES,
        )
        spatial_creation = SpatialEntityCreationEffect(
            effect_ref=f"{occurrence_ref}:lunar-storm-cloud-spatial-create",
            parent_occurrence_ref=occurrence_ref,
            space_entity_ref=space_entity_ref,
            owner_key=LUNAR_STORM_CLOUD_TEAM_SCOPE,
            source_key=instance_ref.value,
            tags=(LUNAR_STORM_CLOUD_STATE_KEY, LUNAR_STORM_CLOUD_SPATIAL_PROFILE_KEY),
            created_frame=request.frame,
            expires_at_frame=request.frame + LUNAR_STORM_CLOUD_LIFETIME_FRAMES,
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
            participant_refs=participants.participant_refs,
            persistent_incoming_aura_application=PersistentIncomingAuraApplicationEffect(
                f"{occurrence_ref}:persistent-incoming-aura"
            ),
            lunar_storm_cloud_state_planning=intent,
            spatial_entity_creation=spatial_creation,
        )
        return ReactionResolution(request, occurrence, None)


def lunar_electro_charged_definition() -> ReactionDefinition:
    return ReactionDefinition(
        LUNAR_ELECTRO_CHARGED_REACTION_KEY,
        LUNAR_ELECTRO_CHARGED_HANDLER_KEY,
        (
            ReactionTriggerSignature(
                Element.HYDRO,
                AuraKind.ELECTRO,
                LUNAR_HYDRO_ON_ELECTRO,
            ),
            ReactionTriggerSignature(
                Element.ELECTRO,
                AuraKind.HYDRO,
                LUNAR_ELECTRO_ON_HYDRO,
            ),
        ),
        (
            LunarElectroChargedReactionProfile(
                LUNAR_ELECTRO_CHARGED_HYDRO_ON_ELECTRO_PROFILE_KEY,
                LUNAR_ELECTRO_CHARGED_REACTION_KEY,
                LUNAR_HYDRO_ON_ELECTRO,
                Element.HYDRO,
                LUNAR_STORM_CLOUD_STATE_KEY,
                LUNAR_STORM_CLOUD_SPATIAL_PROFILE_KEY,
            ),
            LunarElectroChargedReactionProfile(
                LUNAR_ELECTRO_CHARGED_ELECTRO_ON_HYDRO_PROFILE_KEY,
                LUNAR_ELECTRO_CHARGED_REACTION_KEY,
                LUNAR_ELECTRO_ON_HYDRO,
                Element.ELECTRO,
                LUNAR_STORM_CLOUD_STATE_KEY,
                LUNAR_STORM_CLOUD_SPATIAL_PROFILE_KEY,
            ),
        ),
        LunarElectroChargedRule(),
        selection_priority=100,
    )


def lunar_electro_charged_damage_profiles() -> tuple[DamageProfile, ...]:
    return (
        DamageProfile(
            formula_key=FORMULA_KEY_LUNAR_REACTION,
            main_attack_tags=frozenset({LUNAR_ELECTRO_CHARGED_REACTION_KEY}),
        ),
    )


def lunar_electro_charged_gate_definitions() -> tuple[ReactionDamageGateDefinition, ...]:
    return (
        ReactionDamageGateDefinition(
            LUNAR_ELECTRO_CHARGED_GATE_DEFINITION_KEY,
            LUNAR_ELECTRO_CHARGED_DAMAGE_KIND_KEY,
            window_frames=120,
            max_damage_instances=1,
        ),
    )


def _amount_for(request: ReactionEvaluationRequest, aura_kind: AuraKind) -> AuraAmount:
    component = request.observed_aura.component_for(aura_kind)
    return AuraAmount.zero() if component is None else component.current_amount
