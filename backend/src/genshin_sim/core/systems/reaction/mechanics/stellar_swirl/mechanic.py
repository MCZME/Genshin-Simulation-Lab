"""星扩散候选：满足资格时替代普通扩散，并声明星辉风旋与反应星烁伤害。"""

from __future__ import annotations

from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
    ElementalSourceRef,
)
from genshin_sim.core.space import Vector3
from genshin_sim.core.systems.aura.profiles import (
    AuraApplicationProfile,
    AuraDecayProfilePolicy,
)
from genshin_sim.core.systems.damage import FORMULA_KEY_STELLAR_REACTION
from genshin_sim.core.systems.damage.models import DamageProfile
from genshin_sim.core.systems.reaction.gates import ReactionDamageGateDefinition
from genshin_sim.core.systems.reaction.mechanics.stellar_swirl.keys import (
    STELLAR_SWIRL_ANEMO_ON_CRYO_PROFILE_KEY,
    STELLAR_SWIRL_CAPABILITY_KEY,
    STELLAR_SWIRL_EXPLOSION_RADIUS_LARGE,
    STELLAR_SWIRL_EXPLOSION_RADIUS_SMALL,
    STELLAR_SWIRL_HANDLER_KEY,
    STELLAR_SWIRL_ICE_AURA_APPLICATION_PROFILE_KEY,
    STELLAR_SWIRL_ICE_BASE_MULTIPLIER_HIGH,
    STELLAR_SWIRL_ICE_BASE_MULTIPLIER_LOW,
    STELLAR_SWIRL_ICE_DAMAGE_KIND_KEY,
    STELLAR_SWIRL_ICE_DAMAGE_PROFILE_KEY,
    STELLAR_SWIRL_ICE_DAMAGE_TAG,
    STELLAR_SWIRL_INCOMING_ANEMO_ON_CRYO,
    STELLAR_SWIRL_REACTION_KEY,
    STELLAR_SWIRL_VORTEX_SCOPE,
    STELLAR_SWIRL_VORTEX_SPATIAL_PROFILE_KEY,
    STELLAR_SWIRL_VORTEX_STATE_KEY,
    STELLAR_SWIRL_WIND_BASE_MULTIPLIER,
    STELLAR_SWIRL_WIND_DAMAGE_KIND_KEY,
    STELLAR_SWIRL_WIND_DAMAGE_PROFILE_KEY,
    STELLAR_SWIRL_WIND_DAMAGE_TAG,
    STELLAR_SWIRL_WIND_GATE_DEFINITION_KEY,
    STELLAR_SWIRL_WIND_GATE_WINDOW_FRAMES,
)
from genshin_sim.core.systems.reaction.models import (
    AreaAroundPositionSelection,
    CurrentSubjectSelection,
    ElementalTransitionEffect,
    OccurrenceCause,
    ReactionDefinition,
    ReactionEffectExecutionScope,
    ReactionEffectGroup,
    ReactionEvaluationRequest,
    ReactionOccurrence,
    ReactionResolution,
    ReactionTriggerSignature,
    SpatialEntityCreationEffect,
    StateReactionProfile,
    StellarReactionDamageImpactEffect,
    StellarSwirlVortexStatePlanningIntent,
)
from genshin_sim.core.systems.reaction.states import (
    STELLAR_SWIRL_VORTEX_LIFETIME_FRAMES,
    ReactionStateInstanceRef,
)


def _participant_order_key(ref: ElementalSourceRef) -> tuple[str, str]:
    return (ref.source_key, ref.instance_id or "")


def stellar_swirl_wind_participants(
    request: ReactionEvaluationRequest,
) -> tuple[ElementalSourceRef, ...]:
    """冻结一次星扩散·风的参与者：触发者 + 目标冰 Aura 活跃贡献者。

    风不附着，触发者参与反应的唯一形态是触发；冰贡献者在反应发生时仍处于
    目标冰 Aura 的活跃贡献列表（剩余量 > 0）且被本次反应消费。请求内的
    AuraView 是反应发生时的冻结观察，列表中的贡献即满足"本应自然存在"。
    参与者按角色身份（source_key）集合语义去重并规范化为无 instance_id 的
    角色 ref：触发者引用可能携带攻击根身份，贡献者引用来自 Aura 快照，
    同一角色不得重复计入。
    """

    character_source_keys = {
        item.source_key
        for item in request.character_source_refs
        if item.source_key.startswith("character:")
    }
    if request.source_ref.source_key.startswith("character:"):
        character_source_keys.add(request.source_ref.source_key)
    source_keys = {request.source_ref.source_key} & character_source_keys
    cryo = request.observed_aura.component_for(AuraKind.CRYO)
    if cryo is not None:
        source_keys.update(
            item.contributor_ref.source_key
            for item in cryo.contributions
            if item.contributor_ref.source_key in character_source_keys
        )
    canonical = tuple(
        sorted(
            (ElementalSourceRef(key) for key in source_keys),
            key=_participant_order_key,
        )
    )
    return canonical


class StellarSwirlRule:
    def evaluate(
        self, request: ReactionEvaluationRequest, definition: ReactionDefinition
    ) -> ReactionResolution | None:
        if STELLAR_SWIRL_CAPABILITY_KEY not in request.reaction_capability_keys:
            return None
        if not any(
            item.source_key == request.source_ref.source_key
            for item in request.character_source_refs
        ):
            return None
        if request.incoming_element is not Element.ANEMO:
            return None
        aura_kind, direction = AuraKind.CRYO, STELLAR_SWIRL_INCOMING_ANEMO_ON_CRYO
        aura = request.observed_aura.component_for(aura_kind)
        if aura is None or aura.current_amount.is_zero:
            return None
        profile = definition.profile_for(direction)
        if not isinstance(profile, StateReactionProfile):
            raise ValueError("星扩散方向必须使用 ReactionStateProfile")
        # 消费关系与普通扩散一致：风按 2 倍关系匹配，aura 侧减半。
        incoming_consumed = request.incoming_amount.minimum(aura.current_amount * AuraAmount(2))
        aura_consumed = incoming_consumed / AuraAmount(2)
        occurrence_ref = f"{request.interaction_id}:occurrence:{request.order}"
        instance_ref = ReactionStateInstanceRef(
            f"reaction-state:stellar-swirl-vortex:{occurrence_ref}"
        )
        spatial_ref = f"reaction_object:stellar_swirl_vortex:{occurrence_ref}"
        participants = stellar_swirl_wind_participants(request)
        vortex_planning = StellarSwirlVortexStatePlanningIntent(
            intent_ref=f"{occurrence_ref}:stellar-swirl-vortex-plan",
            parent_occurrence_ref=occurrence_ref,
            instance_ref=instance_ref,
            subject_ref=request.subject_ref,
            space_entity_ref=spatial_ref,
            trigger_source_ref=request.source_ref,
            scope_ref=STELLAR_SWIRL_VORTEX_SCOPE,
            created_frame=request.frame,
            expires_at_frame=request.frame + STELLAR_SWIRL_VORTEX_LIFETIME_FRAMES,
            reaction_participants=participants,
        )
        group_ref = f"{occurrence_ref}:effect_group:0"
        wind_effect = StellarReactionDamageImpactEffect(
            effect_ref=f"{group_ref}:effect:0",
            effect_group_ref=group_ref,
            effect_order=0,
            parent_occurrence_ref=occurrence_ref,
            main_attack_tag=STELLAR_SWIRL_WIND_DAMAGE_TAG,
            damage_profile_key=STELLAR_SWIRL_WIND_DAMAGE_PROFILE_KEY,
            damage_element=Element.ANEMO,
            damage_kind_key=STELLAR_SWIRL_WIND_DAMAGE_KIND_KEY,
            stellar_base_multiplier=STELLAR_SWIRL_WIND_BASE_MULTIPLIER,
            trigger_source_ref=request.source_ref,
            participant_refs=participants,
            can_crit=True,
            gate_definition_key=STELLAR_SWIRL_WIND_GATE_DEFINITION_KEY,
            audit_tags=(STELLAR_SWIRL_REACTION_KEY, "wind"),
        )
        wind_group = ReactionEffectGroup(
            effect_group_ref=group_ref,
            parent_occurrence_ref=occurrence_ref,
            execution_scope=ReactionEffectExecutionScope.NEXT_SETTLEMENT_ROUND,
            emission_order=0,
            target_selection=CurrentSubjectSelection(
                selection_ref=f"{group_ref}:target-selection",
                subject_ref=request.subject_ref,
            ),
            effects=(wind_effect,),
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
                incoming_consumed=incoming_consumed,
                incoming_remaining=request.incoming_amount - incoming_consumed,
                aura_before=aura.current_amount,
                aura_consumed=aura_consumed,
                aura_remaining=aura.current_amount - aura_consumed,
            ),
            effect_groups=(wind_group,),
            stellar_swirl_vortex_state_planning=vortex_planning,
            spatial_entity_creation=SpatialEntityCreationEffect(
                effect_ref=f"{occurrence_ref}:stellar-swirl-vortex-spatial-create",
                parent_occurrence_ref=occurrence_ref,
                space_entity_ref=spatial_ref,
                owner_key=STELLAR_SWIRL_VORTEX_SCOPE,
                source_key=instance_ref.value,
                tags=(STELLAR_SWIRL_VORTEX_STATE_KEY, STELLAR_SWIRL_VORTEX_SPATIAL_PROFILE_KEY),
                created_frame=request.frame,
                expires_at_frame=request.frame + STELLAR_SWIRL_VORTEX_LIFETIME_FRAMES,
            ),
        )
        return ReactionResolution(request, occurrence, None)


def stellar_swirl_definition() -> ReactionDefinition:
    return ReactionDefinition(
        STELLAR_SWIRL_REACTION_KEY,
        STELLAR_SWIRL_HANDLER_KEY,
        (
            ReactionTriggerSignature(
                Element.ANEMO, AuraKind.CRYO, STELLAR_SWIRL_INCOMING_ANEMO_ON_CRYO
            ),
        ),
        (
            StateReactionProfile(
                STELLAR_SWIRL_ANEMO_ON_CRYO_PROFILE_KEY,
                STELLAR_SWIRL_REACTION_KEY,
                STELLAR_SWIRL_INCOMING_ANEMO_ON_CRYO,
                Element.ANEMO,
            ),
        ),
        StellarSwirlRule(),
        selection_priority=110,
    )


def stellar_swirl_explosion_effect_group(
    *,
    effect_group_ref: str,
    parent_occurrence_ref: str,
    anchor_position: Vector3,
    level: int,
    trigger_source_ref: ElementalSourceRef,
    participant_refs: tuple[ElementalSourceRef, ...],
) -> ReactionEffectGroup:
    """构造风旋爆炸的星扩散·冰 Effect group。

    爆炸不被视为触发反应：effect group 以风旋生命周期内最后一次星扩散·风
    的 occurrence 作为因果锚点，不发 REACTION_OCCURRED。伤害源与参与者
    来自风旋账本；范围半径按等级两档切换，高度仅作资料记录。
    """

    radius = (
        STELLAR_SWIRL_EXPLOSION_RADIUS_LARGE if level >= 3 else STELLAR_SWIRL_EXPLOSION_RADIUS_SMALL
    )
    multiplier = (
        STELLAR_SWIRL_ICE_BASE_MULTIPLIER_HIGH
        if level >= 3
        else STELLAR_SWIRL_ICE_BASE_MULTIPLIER_LOW
    )
    effect = StellarReactionDamageImpactEffect(
        effect_ref=f"{effect_group_ref}:effect:0",
        effect_group_ref=effect_group_ref,
        effect_order=0,
        parent_occurrence_ref=parent_occurrence_ref,
        main_attack_tag=STELLAR_SWIRL_ICE_DAMAGE_TAG,
        damage_profile_key=STELLAR_SWIRL_ICE_DAMAGE_PROFILE_KEY,
        damage_element=Element.CRYO,
        damage_kind_key=STELLAR_SWIRL_ICE_DAMAGE_KIND_KEY,
        stellar_base_multiplier=multiplier,
        trigger_source_ref=trigger_source_ref,
        participant_refs=participant_refs,
        can_crit=True,
        attached_aura_element=Element.CRYO,
        attached_aura_amount=AuraAmount.one(),
        aura_application_profile_key=STELLAR_SWIRL_ICE_AURA_APPLICATION_PROFILE_KEY,
        audit_tags=(STELLAR_SWIRL_REACTION_KEY, "ice_explosion"),
        cause=OccurrenceCause(parent_occurrence_ref),
    )
    return ReactionEffectGroup(
        effect_group_ref=effect_group_ref,
        parent_occurrence_ref=parent_occurrence_ref,
        execution_scope=ReactionEffectExecutionScope.NEXT_SETTLEMENT_ROUND,
        # 爆炸组可能与其因果锚点 occurrence 的风伤害组同根结算，
        # emission_order 固定为 1 以避免结算 work_id 冲突。
        emission_order=1,
        # 爆炸只作用于敌对目标：显式声明 hostile 资格策略，不继承
        # ``AreaAroundPositionSelection`` 的 ``bloom_damage`` 默认值，避免
        # "不自伤"依赖伤害 Effect 类型联合而非意图表达。范围内角色改由
        # 跳跃能力 Buff 通道承接，不受冰伤害、不被附着。
        target_selection=AreaAroundPositionSelection(
            selection_ref=f"{effect_group_ref}:target-selection",
            center=anchor_position,
            radius=radius,
            eligibility_policy_key="reaction_target.hostile_effect",
        ),
        effects=(effect,),
    )


def stellar_swirl_gate_definitions() -> tuple[ReactionDamageGateDefinition, ...]:
    """风扩散·风的单目标短时去重 Gate：窗口内至多承受一次风伤害。"""

    return (
        ReactionDamageGateDefinition(
            STELLAR_SWIRL_WIND_GATE_DEFINITION_KEY,
            STELLAR_SWIRL_WIND_DAMAGE_KIND_KEY,
            STELLAR_SWIRL_WIND_GATE_WINDOW_FRAMES,
            1,
        ),
    )


def stellar_swirl_damage_profiles() -> tuple[DamageProfile, ...]:
    """星扩散风/冰主攻击标签到独立星烁公式的稳定映射。"""

    return (
        DamageProfile(
            FORMULA_KEY_STELLAR_REACTION,
            frozenset({STELLAR_SWIRL_WIND_DAMAGE_TAG}),
        ),
        DamageProfile(
            FORMULA_KEY_STELLAR_REACTION,
            frozenset({STELLAR_SWIRL_ICE_DAMAGE_TAG}),
        ),
    )


def stellar_swirl_ice_aura_application_profile() -> AuraApplicationProfile:
    """星扩散冰爆炸 1U 冰附着使用的常规持久 Aura 附着 Profile。"""

    return AuraApplicationProfile(
        profile_key=STELLAR_SWIRL_ICE_AURA_APPLICATION_PROFILE_KEY,
        decay_profile_policy=AuraDecayProfilePolicy.REGULAR_FROM_RAW_AMOUNT,
    )
