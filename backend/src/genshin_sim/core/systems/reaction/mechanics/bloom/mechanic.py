"""普通绽放的两个元素方向。"""

from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.core.elements import AuraAmount, AuraKind, Element
from genshin_sim.core.systems.damage import DamageProfile
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_TRANSFORMATIVE_REACTION
from genshin_sim.core.systems.reaction.gates import ReactionDamageGateDefinition
from genshin_sim.core.systems.reaction.mechanics.bloom.keys import (
    BLOOM_DENDRO_ON_HYDRO_PROFILE_KEY,
    BLOOM_EXPLOSION_REACTION_KEY,
    BLOOM_HANDLER_KEY,
    BLOOM_HYDRO_ON_DENDRO_PROFILE_KEY,
    BLOOM_HYDRO_ON_QUICKEN_PROFILE_KEY,
    BLOOM_REACTION_KEY,
    BURGEON_REACTION_KEY,
    DENDRO_ON_HYDRO,
    HYDRO_ON_DENDRO,
    HYDRO_ON_QUICKEN,
    HYPERBLOOM_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.bloom.profiles import (
    BLOOM_EXPLOSION_DAMAGE_PROFILE,
    BURGEON_DAMAGE_PROFILE,
    HYPERBLOOM_DAMAGE_PROFILE,
)
from genshin_sim.core.systems.reaction.mechanics.dendro_core import (
    DENDRO_CORE_SPATIAL_PROFILE_KEY,
    DENDRO_CORE_STATE_KEY,
    plan_dendro_core_creation,
)
from genshin_sim.core.systems.reaction.models import (
    AreaAroundPositionSelection,
    BloomReactionProfile,
    CurrentSubjectSelection,
    DynamicTransformativeScalingBasis,
    ElementalTransitionEffect,
    GeneratedDamageImpactEffect,
    OccurrenceCause,
    ReactionDecisionSequence,
    ReactionDecisionStep,
    ReactionDefinition,
    ReactionEffectExecutionScope,
    ReactionEffectGroup,
    ReactionEntryKind,
    ReactionEvaluationRequest,
    ReactionOccurrence,
    ReactionResolution,
    ReactionTriggerSignature,
)
from genshin_sim.core.systems.reaction.states import (
    DendroCoreState,
    DendroCoreTerminationReason,
    SprawlingShotResolution,
    SprawlingShotState,
)


class BloomRule:
    def evaluate(
        self,
        request: ReactionEvaluationRequest,
        definition: ReactionDefinition,
    ) -> ReactionResolution | None:
        if request.incoming_amount.is_zero:
            return None
        direction, aura_kind = _direction_for(request)
        if direction is None or aura_kind is None:
            return None
        aura_amount = _amount_for(request, aura_kind)
        if aura_amount.is_zero:
            return None
        profile = definition.profile_for(direction)
        if not isinstance(profile, BloomReactionProfile):
            raise ValueError("普通绽放方向必须使用 BloomReactionProfile")
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


class _NoopStateTriggerRule:
    def evaluate(self, request, definition):
        return None


def bloom_definition() -> ReactionDefinition:
    return ReactionDefinition(
        BLOOM_REACTION_KEY,
        BLOOM_HANDLER_KEY,
        (
            ReactionTriggerSignature(Element.HYDRO, AuraKind.DENDRO, HYDRO_ON_DENDRO),
            ReactionTriggerSignature(Element.HYDRO, AuraKind.QUICKEN, HYDRO_ON_QUICKEN),
            ReactionTriggerSignature(Element.DENDRO, AuraKind.HYDRO, DENDRO_ON_HYDRO),
        ),
        (
            BloomReactionProfile(
                BLOOM_HYDRO_ON_DENDRO_PROFILE_KEY,
                BLOOM_REACTION_KEY,
                HYDRO_ON_DENDRO,
                Element.HYDRO,
                AuraKind.DENDRO,
                DENDRO_CORE_STATE_KEY,
                DENDRO_CORE_SPATIAL_PROFILE_KEY,
            ),
            BloomReactionProfile(
                BLOOM_HYDRO_ON_QUICKEN_PROFILE_KEY,
                BLOOM_REACTION_KEY,
                HYDRO_ON_QUICKEN,
                Element.HYDRO,
                AuraKind.QUICKEN,
                DENDRO_CORE_STATE_KEY,
                DENDRO_CORE_SPATIAL_PROFILE_KEY,
            ),
            BloomReactionProfile(
                BLOOM_DENDRO_ON_HYDRO_PROFILE_KEY,
                BLOOM_REACTION_KEY,
                DENDRO_ON_HYDRO,
                Element.DENDRO,
                AuraKind.HYDRO,
                DENDRO_CORE_STATE_KEY,
                DENDRO_CORE_SPATIAL_PROFILE_KEY,
            ),
        ),
        BloomRule(),
    )


def bloom_explosion_definition() -> ReactionDefinition:
    return _state_definition(BLOOM_EXPLOSION_REACTION_KEY, BLOOM_HANDLER_KEY)


def hyperbloom_definition() -> ReactionDefinition:
    return _state_definition(HYPERBLOOM_REACTION_KEY, "reaction_handler.hyperbloom")


def burgeon_definition() -> ReactionDefinition:
    return _state_definition(BURGEON_REACTION_KEY, "reaction_handler.burgeon")


def bloom_damage_profiles() -> tuple[DamageProfile, ...]:
    return (
        DamageProfile(
            formula_key=FORMULA_KEY_TRANSFORMATIVE_REACTION,
            main_attack_tags=frozenset({BLOOM_EXPLOSION_REACTION_KEY}),
        ),
        DamageProfile(
            formula_key=FORMULA_KEY_TRANSFORMATIVE_REACTION,
            main_attack_tags=frozenset({HYPERBLOOM_REACTION_KEY}),
        ),
        DamageProfile(
            formula_key=FORMULA_KEY_TRANSFORMATIVE_REACTION,
            main_attack_tags=frozenset({BURGEON_REACTION_KEY}),
        ),
    )


def bloom_gate_definitions() -> tuple[ReactionDamageGateDefinition, ...]:
    return (
        ReactionDamageGateDefinition(
            "reaction_gate.bloom_family.damage",
            "bloom_family",
            30,
            2,
        ),
    )


@dataclass(frozen=True, slots=True)
class BloomTerminalReaction:
    """一个已终结核心或蔓生弹的可审计 occurrence 及可选后续伤害。"""

    occurrence: ReactionOccurrence
    effect_group: ReactionEffectGroup | None = None

    def __post_init__(self) -> None:
        if self.effect_group is not None and self.effect_group.parent_occurrence_ref != (
            self.occurrence.occurrence_ref
        ):
            raise ValueError("终态 Effect group 必须归属终态 occurrence")


def bloom_explosion_terminal_reaction(
    *,
    core: DendroCoreState,
    center,
    effect_group_ref: str,
    reason: DendroCoreTerminationReason,
) -> BloomTerminalReaction:
    if reason not in {
        DendroCoreTerminationReason.EXPIRED,
        DendroCoreTerminationReason.CAPACITY_EVICTED,
    }:
        raise ValueError("绽放爆炸只接受到期或容量淘汰终结原因")
    return _terminal_reaction(
        occurrence_ref=f"{effect_group_ref}:occurrence:0",
        interaction_id=f"reaction-terminal:{effect_group_ref}",
        parent_occurrence_ref=core.created_by_occurrence_ref,
        source_ref=core.core_creator_ref,
        subject_ref=core.subject_ref,
        reaction_key=BLOOM_EXPLOSION_REACTION_KEY,
        direction_key=reason.value,
        profile=BLOOM_EXPLOSION_DAMAGE_PROFILE,
        center=center,
        effect_group_ref=effect_group_ref,
        dynamic_basis=core.dynamic_scaling_basis,
    )


def bloom_explosion_effect_group(
    *,
    core: DendroCoreState,
    center,
    effect_group_ref: str,
) -> ReactionEffectGroup:
    """兼容入口：新代码应携带完整终态 occurrence。"""

    terminal = bloom_explosion_terminal_reaction(
        core=core,
        center=center,
        effect_group_ref=effect_group_ref,
        reason=DendroCoreTerminationReason.EXPIRED,
    )
    assert terminal.effect_group is not None
    return terminal.effect_group


def burgeon_terminal_reaction(
    *,
    core: DendroCoreState,
    trigger_source_ref,
    center,
    effect_group_ref: str,
) -> BloomTerminalReaction:
    return _terminal_reaction(
        occurrence_ref=f"{effect_group_ref}:occurrence:0",
        interaction_id=f"reaction-terminal:{effect_group_ref}",
        parent_occurrence_ref=core.created_by_occurrence_ref,
        source_ref=trigger_source_ref,
        subject_ref=core.subject_ref,
        reaction_key=BURGEON_REACTION_KEY,
        direction_key=DendroCoreTerminationReason.BURGEON_TRIGGERED.value,
        profile=BURGEON_DAMAGE_PROFILE,
        center=center,
        effect_group_ref=effect_group_ref,
    )


def burgeon_effect_group(
    *,
    core: DendroCoreState,
    trigger_source_ref,
    center,
    effect_group_ref: str,
) -> ReactionEffectGroup:
    terminal = burgeon_terminal_reaction(
        core=core,
        trigger_source_ref=trigger_source_ref,
        center=center,
        effect_group_ref=effect_group_ref,
    )
    assert terminal.effect_group is not None
    return terminal.effect_group


def hyperbloom_trigger_occurrence(
    *,
    core: DendroCoreState,
    trigger_source_ref,
    occurrence_ref: str,
) -> ReactionOccurrence:
    return _terminal_reaction(
        occurrence_ref=occurrence_ref,
        interaction_id=f"reaction-terminal:{occurrence_ref}",
        parent_occurrence_ref=core.created_by_occurrence_ref,
        source_ref=trigger_source_ref,
        subject_ref=core.subject_ref,
        reaction_key=HYPERBLOOM_REACTION_KEY,
        direction_key=DendroCoreTerminationReason.HYPERBLOOM_TRIGGERED.value,
        profile=HYPERBLOOM_DAMAGE_PROFILE,
    ).occurrence


def hyperbloom_resolution_reaction(
    *,
    shot: SprawlingShotState,
    resolution: SprawlingShotResolution,
    center,
    effect_group_ref: str,
) -> BloomTerminalReaction:
    return _terminal_reaction(
        occurrence_ref=f"{effect_group_ref}:occurrence:0",
        interaction_id=f"reaction-terminal:{effect_group_ref}",
        parent_occurrence_ref=shot.trigger_occurrence_ref,
        source_ref=shot.trigger_source_ref,
        subject_ref=shot.selected_target_ref,
        reaction_key=HYPERBLOOM_REACTION_KEY,
        direction_key=resolution.value,
        profile=HYPERBLOOM_DAMAGE_PROFILE,
        center=(None if resolution is SprawlingShotResolution.LOST else center),
        effect_group_ref=(None if resolution is SprawlingShotResolution.LOST else effect_group_ref),
        dynamic_basis=shot.dynamic_scaling_basis,
        target_selection=(
            None
            if resolution is SprawlingShotResolution.LOST
            else CurrentSubjectSelection(
                selection_ref=f"{effect_group_ref}:target-selection",
                subject_ref=shot.selected_target_ref,
                center=center,
                radius=HYPERBLOOM_DAMAGE_PROFILE.radius,
            )
        ),
    )


def hyperbloom_arrived_effect_group(
    *,
    shot: SprawlingShotState,
    center,
    effect_group_ref: str,
) -> ReactionEffectGroup:
    terminal = hyperbloom_resolution_reaction(
        shot=shot,
        resolution=SprawlingShotResolution.ARRIVED,
        center=center,
        effect_group_ref=effect_group_ref,
    )
    assert terminal.effect_group is not None
    return terminal.effect_group


def _terminal_reaction(
    *,
    occurrence_ref: str,
    interaction_id: str,
    parent_occurrence_ref: str,
    source_ref,
    subject_ref,
    reaction_key: str,
    direction_key: str,
    profile,
    center=None,
    effect_group_ref: str | None = None,
    dynamic_basis: DynamicTransformativeScalingBasis | None = None,
    target_selection=None,
) -> BloomTerminalReaction:
    if (center is None) != (effect_group_ref is None):
        raise ValueError("终态伤害位置与 Effect group 必须同时存在或同时缺失")
    effect_group = (
        None
        if effect_group_ref is None
        else _termination_effect_group(
            parent_occurrence_ref=occurrence_ref,
            source_ref=source_ref,
            center=center,
            effect_group_ref=effect_group_ref,
            reaction_key=reaction_key,
            profile=profile,
            dynamic_basis=dynamic_basis,
            target_selection=target_selection,
        )
    )
    zero = AuraAmount.zero()
    occurrence = ReactionOccurrence(
        occurrence_ref=occurrence_ref,
        interaction_id=interaction_id,
        reaction_key=reaction_key,
        direction_key=direction_key,
        profile_key=profile.profile_key,
        source_ref=source_ref,
        subject_ref=subject_ref,
        transition=ElementalTransitionEffect(
            aura_kind=AuraKind.DENDRO,
            incoming_before=zero,
            incoming_consumed=zero,
            incoming_remaining=zero,
            aura_before=zero,
            aura_consumed=zero,
            aura_remaining=zero,
        ),
        effect_groups=() if effect_group is None else (effect_group,),
        parent_occurrence_ref=parent_occurrence_ref,
    )
    return BloomTerminalReaction(occurrence, effect_group)


def _termination_effect_group(
    *,
    parent_occurrence_ref: str,
    source_ref,
    center,
    effect_group_ref: str,
    reaction_key: str,
    profile,
    dynamic_basis: DynamicTransformativeScalingBasis | None = None,
    target_selection=None,
) -> ReactionEffectGroup:
    basis = dynamic_basis or DynamicTransformativeScalingBasis(
        basis_ref=f"{effect_group_ref}:dynamic-basis",
        source_ref=source_ref,
        source_observation_profile_key="reaction_source_observation.character_transformative",
        reaction_profile_key=profile.profile_key,
        damage_profile_key=profile.damage_profile_key,
    )
    effect = GeneratedDamageImpactEffect(
        effect_ref=f"{effect_group_ref}:effect:0",
        effect_group_ref=effect_group_ref,
        effect_order=0,
        parent_occurrence_ref=parent_occurrence_ref,
        main_attack_tag=reaction_key,
        damage_profile_key=profile.damage_profile_key,
        damage_element=profile.damage_element,
        gate_definition_key=profile.gate_definition_key,
        damage_kind_key=profile.damage_kind_key,
        transformative_base_multiplier=profile.monster_multiplier,
        character_transformative_base_multiplier=profile.character_multiplier,
        captured_scaling_basis=basis,
        audit_tags=(reaction_key,),
        cause=OccurrenceCause(parent_occurrence_ref),
    )
    return ReactionEffectGroup(
        effect_group_ref=effect_group_ref,
        parent_occurrence_ref=parent_occurrence_ref,
        execution_scope=ReactionEffectExecutionScope.NEXT_SETTLEMENT_ROUND,
        emission_order=0,
        target_selection=target_selection
        or AreaAroundPositionSelection(
            selection_ref=f"{effect_group_ref}:target-selection",
            center=center,
            radius=profile.radius,
        ),
        effects=(effect,),
    )


def _state_definition(reaction_key: str, handler_key: str) -> ReactionDefinition:
    return ReactionDefinition(
        reaction_key,
        handler_key,
        (),
        (),
        _NoopStateTriggerRule(),
        entry_kind=ReactionEntryKind.STATE_TRIGGER,
    )


def _direction_for(request: ReactionEvaluationRequest) -> tuple[str | None, AuraKind | None]:
    if request.incoming_element is Element.HYDRO:
        if not _amount_for(request, AuraKind.DENDRO).is_zero:
            return HYDRO_ON_DENDRO, AuraKind.DENDRO
        if not _amount_for(request, AuraKind.QUICKEN).is_zero:
            return HYDRO_ON_QUICKEN, AuraKind.QUICKEN
    elif request.incoming_element is Element.DENDRO:
        if not _amount_for(request, AuraKind.HYDRO).is_zero:
            return DENDRO_ON_HYDRO, AuraKind.HYDRO
    return None, None


def _amount_for(request: ReactionEvaluationRequest, aura_kind: AuraKind) -> AuraAmount:
    component = request.observed_aura.component_for(aura_kind)
    return AuraAmount.zero() if component is None else component.current_amount
