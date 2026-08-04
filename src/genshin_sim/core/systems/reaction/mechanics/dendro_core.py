"""普通绽放与月绽放共享的草原核创建计划。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from genshin_sim.core.elements import AuraKind, Element
from genshin_sim.core.systems.reaction.models import (
    DendroCoreStateCreationIntent,
    DynamicTransformativeScalingBasis,
    ElementalTransitionEffect,
    ReactionEvaluationRequest,
    SpatialEntityCreationEffect,
)
from genshin_sim.core.systems.reaction.states import ReactionStateInstanceRef

DENDRO_CORE_LIFETIME_FRAMES = 360
DENDRO_CORE_POOL_CAPACITY = 5
DENDRO_CORE_STATE_KEY = "reaction_state.dendro_core"
DENDRO_CORE_SPATIAL_PROFILE_KEY = "reaction_spatial_profile.dendro_core"
DENDRO_CORE_TERMINATION_DAMAGE_PROFILE_KEY = "damage_profile.reaction.bloom_explosion"
PLAYER_TEAM_DENDRO_CORE_POOL_SCOPE = "player_team"


class DendroCoreCreationProfile(Protocol):
    @property
    def profile_key(self) -> str: ...

    @property
    def core_state_profile_key(self) -> str: ...

    @property
    def core_spatial_profile_key(self) -> str: ...

    @property
    def lifetime_frames(self) -> int: ...


@dataclass(frozen=True, slots=True)
class DendroCoreCreationPlan:
    occurrence_ref: str
    transition: ElementalTransitionEffect
    state_creation: DendroCoreStateCreationIntent
    spatial_creation: SpatialEntityCreationEffect


def plan_dendro_core_creation(
    request: ReactionEvaluationRequest,
    *,
    aura_kind: AuraKind,
    profile: DendroCoreCreationProfile,
) -> DendroCoreCreationPlan | None:
    """按水草消费关系准备草原核 State 与 Space 创建声明。"""

    component = request.observed_aura.component_for(aura_kind)
    if component is None:
        return None
    aura_amount = component.current_amount
    if aura_amount.is_zero or request.incoming_amount.is_zero:
        return None
    if request.incoming_element is Element.HYDRO:
        hydro_used = min(request.incoming_amount, aura_amount * 2)
        dendro_used = hydro_used / 2
        incoming_consumed, aura_consumed = hydro_used, dendro_used
    elif request.incoming_element is Element.DENDRO:
        dendro_used = min(request.incoming_amount, aura_amount / 2)
        hydro_used = dendro_used * 2
        incoming_consumed, aura_consumed = dendro_used, hydro_used
    else:
        raise ValueError("草原核只能由水草元素交互创建")
    if incoming_consumed.is_zero or aura_consumed.is_zero:
        return None

    transition = ElementalTransitionEffect(
        aura_kind=aura_kind,
        incoming_before=request.incoming_amount,
        incoming_consumed=incoming_consumed,
        incoming_remaining=request.incoming_amount - incoming_consumed,
        aura_before=aura_amount,
        aura_consumed=aura_consumed,
        aura_remaining=aura_amount - aura_consumed,
    )
    occurrence_ref = f"{request.interaction_id}:occurrence:{request.order}"
    instance_ref = ReactionStateInstanceRef(f"reaction-state:dendro-core:{occurrence_ref}")
    space_entity_ref = f"reaction_object:dendro_core:{occurrence_ref}"
    dynamic_basis = DynamicTransformativeScalingBasis(
        basis_ref=f"{occurrence_ref}:dynamic-basis",
        source_ref=request.source_ref,
        source_observation_profile_key="reaction_source_observation.character_transformative",
        reaction_profile_key=profile.profile_key,
        damage_profile_key=DENDRO_CORE_TERMINATION_DAMAGE_PROFILE_KEY,
    )
    state_creation = DendroCoreStateCreationIntent(
        intent_ref=f"{occurrence_ref}:dendro-core-create",
        parent_occurrence_ref=occurrence_ref,
        instance_ref=instance_ref,
        subject_ref=request.subject_ref,
        space_entity_ref=space_entity_ref,
        core_creator_ref=request.source_ref,
        dynamic_scaling_basis=dynamic_basis,
        pool_scope=PLAYER_TEAM_DENDRO_CORE_POOL_SCOPE,
        created_frame=request.frame,
        expires_at_frame=request.frame + profile.lifetime_frames,
        # 状态规划器在批次投影中分配全局单调递增的创建序号。
        creation_sequence=0,
    )
    spatial_creation = SpatialEntityCreationEffect(
        effect_ref=f"{occurrence_ref}:dendro-core-spatial-create",
        parent_occurrence_ref=occurrence_ref,
        space_entity_ref=space_entity_ref,
        owner_key=PLAYER_TEAM_DENDRO_CORE_POOL_SCOPE,
        source_key=instance_ref.value,
        tags=(profile.core_state_profile_key, profile.core_spatial_profile_key),
        created_frame=request.frame,
        expires_at_frame=request.frame + profile.lifetime_frames,
    )
    return DendroCoreCreationPlan(
        occurrence_ref,
        transition,
        state_creation,
        spatial_creation,
    )
