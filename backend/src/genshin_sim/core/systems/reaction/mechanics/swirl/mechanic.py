"""普通扩散的单 Aura 决策与派生 Impact 声明。"""

from __future__ import annotations

from dataclasses import dataclass, replace

from genshin_sim.core.elements import AuraAmount, AuraKind, Element
from genshin_sim.core.systems.aura import (
    AuraApplicationProfile,
    AuraDecayProfilePolicy,
    AuraView,
)
from genshin_sim.core.systems.damage import (
    DamageProfile,
    DamageReactionCapability,
    TransformativeReactionInput,
)
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_TRANSFORMATIVE_REACTION
from genshin_sim.core.systems.reaction.gates import ReactionDamageGateDefinition
from genshin_sim.core.systems.reaction.models import (
    CapturedTransformativeScalingBasis,
    CurrentSubjectSelection,
    ElementalTransitionEffect,
    GeneratedDamageImpactEffect,
    ReactionDecisionSequence,
    ReactionDecisionStep,
    ReactionDefinition,
    ReactionEffectExecutionScope,
    ReactionEffectGroup,
    ReactionEvaluationRequest,
    ReactionGeneratedImpact,
    ReactionGeneratedImpactBatch,
    ReactionGeneratedImpactDamageComponent,
    ReactionGeneratedImpactProvenance,
    ReactionOccurrence,
    ReactionResolution,
    ReactionTriggerSignature,
    SwirlEmissionSelection,
    TransformativeReactionProfile,
)

SWIRL_REACTION_KEY = "reaction.swirl"
SWIRL_HANDLER_KEY = "reaction_handler.swirl"
SWIRL_DAMAGE_PROFILE_KEY = "damage_profile.reaction.swirl"
SWIRL_AURA_APPLICATION_PROFILE_KEY = "aura_application_profile.reaction.swirl"
SWIRL_BASE_MULTIPLIER = 0.6
PYRO_SWIRL_GATE_DEFINITION_KEY = "reaction_gate.swirl.pyro.damage"
HYDRO_SWIRL_GATE_DEFINITION_KEY = "reaction_gate.swirl.hydro.damage"
ELECTRO_SWIRL_GATE_DEFINITION_KEY = "reaction_gate.swirl.electro.damage"
CRYO_SWIRL_GATE_DEFINITION_KEY = "reaction_gate.swirl.cryo.damage"

PYRO_SWIRL = "incoming_anemo_on_pyro"
HYDRO_SWIRL = "incoming_anemo_on_hydro"
ELECTRO_SWIRL = "incoming_anemo_on_electro"
CRYO_SWIRL = "incoming_anemo_on_cryo"
FROZEN_SWIRL = "incoming_anemo_on_frozen"


class SwirlSelectionError(RuntimeError):
    """当前实现没有可信规则处理的多候选扩散。"""


@dataclass(frozen=True, slots=True)
class _SwirlCandidate:
    aura_kind: AuraKind
    direction_key: str
    output_element: Element
    damage_element: Element
    gate_definition_key: str
    damage_kind_key: str


_SINGLE_AURA_CANDIDATES = (
    _SwirlCandidate(
        AuraKind.PYRO,
        PYRO_SWIRL,
        Element.PYRO,
        Element.PYRO,
        PYRO_SWIRL_GATE_DEFINITION_KEY,
        "reaction_damage.swirl.pyro",
    ),
    _SwirlCandidate(
        AuraKind.HYDRO,
        HYDRO_SWIRL,
        Element.HYDRO,
        Element.HYDRO,
        HYDRO_SWIRL_GATE_DEFINITION_KEY,
        "reaction_damage.swirl.hydro",
    ),
    _SwirlCandidate(
        AuraKind.ELECTRO,
        ELECTRO_SWIRL,
        Element.ELECTRO,
        Element.ELECTRO,
        ELECTRO_SWIRL_GATE_DEFINITION_KEY,
        "reaction_damage.swirl.electro",
    ),
    _SwirlCandidate(
        AuraKind.CRYO,
        CRYO_SWIRL,
        Element.CRYO,
        Element.CRYO,
        CRYO_SWIRL_GATE_DEFINITION_KEY,
        "reaction_damage.swirl.cryo",
    ),
    _SwirlCandidate(
        AuraKind.FROZEN,
        FROZEN_SWIRL,
        Element.CRYO,
        Element.CRYO,
        CRYO_SWIRL_GATE_DEFINITION_KEY,
        "reaction_damage.swirl.cryo",
    ),
)


class SwirlRule:
    def evaluate(
        self,
        request: ReactionEvaluationRequest,
        definition: ReactionDefinition,
    ) -> ReactionResolution | None:
        if request.incoming_element is not Element.ANEMO:
            return None
        candidate, aura_before = _single_candidate(request)
        if candidate is None:
            return None
        occurrence, profile = _occurrence_for(request, definition, candidate, aura_before)
        return _single_resolution(
            request,
            occurrence=occurrence,
            profile=profile,
            candidate=candidate,
            emitted_amount=_emitted_amount(request.incoming_amount, aura_before),
        )

    def evaluate_multiple_aura(
        self,
        request: ReactionEvaluationRequest,
        definition: ReactionDefinition,
    ) -> ReactionResolution | None:
        """处理已确认的感电与冻结双扩散，不依赖 Definition 顺序。"""

        if request.incoming_element is not Element.ANEMO:
            return None
        candidates = _available_candidates(request)
        candidate_by_kind = {
            candidate.aura_kind: (candidate, amount) for candidate, amount in candidates
        }
        if len(candidate_by_kind) != 2:
            return None
        kinds = frozenset(candidate_by_kind)
        if kinds == frozenset((AuraKind.ELECTRO, AuraKind.HYDRO)):
            first, first_amount = candidate_by_kind[AuraKind.ELECTRO]
            second, second_amount = candidate_by_kind[AuraKind.HYDRO]
            return _two_occurrence_resolution(
                request,
                definition,
                first_candidate=first,
                first_aura_before=first_amount,
                second_candidate=second,
                second_aura_before=second_amount,
            )
        if kinds == frozenset((AuraKind.HYDRO, AuraKind.FROZEN)):
            first, first_amount = candidate_by_kind[AuraKind.HYDRO]
            second, second_amount = candidate_by_kind[AuraKind.FROZEN]
            return _two_occurrence_resolution(
                request,
                definition,
                first_candidate=first,
                first_aura_before=first_amount,
                second_candidate=second,
                second_aura_before=second_amount,
            )
        if kinds == frozenset((AuraKind.CRYO, AuraKind.FROZEN)):
            first, first_amount = candidate_by_kind[AuraKind.CRYO]
            frozen, frozen_amount = candidate_by_kind[AuraKind.FROZEN]
            return _hidden_cryo_frozen_resolution(
                request,
                definition,
                cryo_candidate=first,
                cryo_aura_before=first_amount,
                frozen_candidate=frozen,
                frozen_aura_before=frozen_amount,
            )
        return None


def _occurrence_for(
    request: ReactionEvaluationRequest,
    definition: ReactionDefinition,
    candidate: _SwirlCandidate,
    aura_before: AuraAmount,
) -> tuple[ReactionOccurrence, TransformativeReactionProfile]:
    profile = definition.profile_for(candidate.direction_key)
    if not isinstance(profile, TransformativeReactionProfile):
        raise ValueError("扩散方向必须使用 TransformativeReactionProfile")
    observation = request.transformative_source_observation
    if observation is None:
        raise ValueError("扩散需要已捕获的剧变来源观察")

    incoming_before = request.incoming_amount
    incoming_consumed = incoming_before.minimum(aura_before * AuraAmount(2))
    aura_consumed = incoming_consumed / AuraAmount(2)
    occurrence_ref = f"{request.interaction_id}:occurrence:{request.order}"
    group_ref = f"{occurrence_ref}:effect_group:0"
    basis = _captured_basis(request, profile, group_ref)
    center_effect = GeneratedDamageImpactEffect(
        effect_ref=f"{group_ref}:effect:0",
        effect_group_ref=group_ref,
        effect_order=0,
        parent_occurrence_ref=occurrence_ref,
        main_attack_tag=SWIRL_REACTION_KEY,
        damage_profile_key=profile.damage_profile_key,
        damage_element=profile.damage_element,
        gate_definition_key=profile.gate_definition_key,
        damage_kind_key=profile.damage_kind_key,
        captured_scaling_basis=basis,
        transformative_base_multiplier=profile.base_multiplier,
        audit_tags=(SWIRL_REACTION_KEY, candidate.output_element.value, "center"),
    )
    group = ReactionEffectGroup(
        effect_group_ref=group_ref,
        parent_occurrence_ref=occurrence_ref,
        execution_scope=ReactionEffectExecutionScope.NEXT_SETTLEMENT_ROUND,
        emission_order=0,
        target_selection=CurrentSubjectSelection(
            selection_ref=f"{group_ref}:target_selection",
            subject_ref=request.subject_ref,
        ),
        effects=(center_effect,),
    )
    occurrence = ReactionOccurrence(
        occurrence_ref=occurrence_ref,
        interaction_id=request.interaction_id,
        reaction_key=definition.reaction_key,
        direction_key=candidate.direction_key,
        profile_key=profile.profile_key,
        source_ref=request.source_ref,
        subject_ref=request.subject_ref,
        transition=ElementalTransitionEffect(
            aura_kind=candidate.aura_kind,
            incoming_before=incoming_before,
            incoming_consumed=incoming_consumed,
            incoming_remaining=incoming_before - incoming_consumed,
            aura_before=aura_before,
            aura_consumed=aura_consumed,
            aura_remaining=aura_before - aura_consumed,
        ),
        effect_groups=(group,),
    )
    return occurrence, profile


def _single_resolution(
    request: ReactionEvaluationRequest,
    *,
    occurrence: ReactionOccurrence,
    profile: TransformativeReactionProfile,
    candidate: _SwirlCandidate,
    emitted_amount: AuraAmount,
) -> ReactionResolution:
    return ReactionResolution(
        request,
        occurrence,
        None,
        generated_impact_batches=(
            _emission_batch(
                request,
                occurrence_profiles=((occurrence, profile, candidate),),
                emitted_amount=emitted_amount,
            ),
        ),
    )


def _two_occurrence_resolution(
    request: ReactionEvaluationRequest,
    definition: ReactionDefinition,
    *,
    first_candidate: _SwirlCandidate,
    first_aura_before: AuraAmount,
    second_candidate: _SwirlCandidate,
    second_aura_before: AuraAmount,
) -> ReactionResolution:
    first_request = _request_for_candidate(
        request,
        first_candidate,
        request.incoming_amount,
        request.order,
    )
    first, first_profile = _occurrence_for(
        first_request,
        definition,
        first_candidate,
        first_aura_before,
    )
    if not first.transition.aura_remaining.is_zero or first.transition.incoming_remaining.is_zero:
        return _single_resolution(
            request,
            occurrence=first,
            profile=first_profile,
            candidate=first_candidate,
            emitted_amount=_emitted_amount(first_request.incoming_amount, first_aura_before),
        )
    second_request = _request_for_candidate(
        request,
        second_candidate,
        first.transition.incoming_remaining,
        request.order + 1,
    )
    second, second_profile = _occurrence_for(
        second_request,
        definition,
        second_candidate,
        second_aura_before,
    )
    emitted_amount = _emitted_amount(second_request.incoming_amount, second_aura_before)
    return ReactionResolution(
        request,
        first,
        None,
        ReactionDecisionSequence(
            (
                _decision_step(0, first),
                _decision_step(1, second),
            )
        ),
        generated_impact_batches=(
            _emission_batch(
                request,
                occurrence_profiles=(
                    (first, first_profile, first_candidate),
                    (second, second_profile, second_candidate),
                ),
                emitted_amount=emitted_amount,
            ),
        ),
    )


def _hidden_cryo_frozen_resolution(
    request: ReactionEvaluationRequest,
    definition: ReactionDefinition,
    *,
    cryo_candidate: _SwirlCandidate,
    cryo_aura_before: AuraAmount,
    frozen_candidate: _SwirlCandidate,
    frozen_aura_before: AuraAmount,
) -> ReactionResolution:
    """冻结藏冰先消费藏冰；后续冻元素消费不额外产生冰扩散 occurrence。"""

    cryo_request = _request_for_candidate(
        request,
        cryo_candidate,
        request.incoming_amount,
        request.order,
    )
    occurrence, profile = _occurrence_for(
        cryo_request,
        definition,
        cryo_candidate,
        cryo_aura_before,
    )
    if (
        not occurrence.transition.aura_remaining.is_zero
        or occurrence.transition.incoming_remaining.is_zero
    ):
        return _single_resolution(
            request,
            occurrence=occurrence,
            profile=profile,
            candidate=cryo_candidate,
            emitted_amount=_emitted_amount(cryo_request.incoming_amount, cryo_aura_before),
        )
    frozen_request = _request_for_candidate(
        request,
        frozen_candidate,
        occurrence.transition.incoming_remaining,
        request.order + 1,
    )
    frozen_transition = _transition_for(frozen_request, frozen_candidate, frozen_aura_before)
    return ReactionResolution(
        request,
        occurrence,
        None,
        ReactionDecisionSequence(
            (
                _decision_step(0, occurrence),
                ReactionDecisionStep(
                    1,
                    (frozen_candidate.direction_key,),
                    (frozen_transition,),
                    (),
                    (),
                ),
            )
        ),
        generated_impact_batches=(
            _emission_batch(
                request,
                occurrence_profiles=((occurrence, profile, cryo_candidate),),
                emitted_amount=_emitted_amount(
                    frozen_request.incoming_amount,
                    frozen_aura_before,
                ),
            ),
        ),
    )


def _emission_batch(
    request: ReactionEvaluationRequest,
    *,
    occurrence_profiles: tuple[
        tuple[ReactionOccurrence, TransformativeReactionProfile, _SwirlCandidate], ...
    ],
    emitted_amount: AuraAmount,
) -> ReactionGeneratedImpactBatch:
    parent_root_work_ref = request.source_ref.instance_id
    if parent_root_work_ref is None:
        raise ValueError("扩散派生元素需要 source_ref.instance_id 作为父 RootWork 身份")
    observation = request.transformative_source_observation
    if observation is None:
        raise ValueError("扩散派生元素需要已捕获的剧变来源观察")
    anchor_occurrence = occurrence_profiles[0][0]
    impacts = tuple(
        ReactionGeneratedImpact(
            generated_impact_ref=f"{occurrence.occurrence_ref}:emission:0",
            emission_order=index,
            element=candidate.output_element,
            elemental_amount=emitted_amount,
            aura_application_profile_key=SWIRL_AURA_APPLICATION_PROFILE_KEY,
            provenance=ReactionGeneratedImpactProvenance(
                provenance_ref=f"{occurrence.occurrence_ref}:emission:0:provenance",
                parent_occurrence_ref=occurrence.occurrence_ref,
                reaction_profile_key=profile.profile_key,
            ),
            damage_component=_range_damage_component(profile, candidate),
        )
        for index, (occurrence, profile, candidate) in enumerate(occurrence_profiles)
    )
    return ReactionGeneratedImpactBatch(
        emission_batch_ref=f"{anchor_occurrence.occurrence_ref}:emission_batch:0",
        parent_root_work_ref=parent_root_work_ref,
        parent_occurrence_refs=tuple(
            occurrence.occurrence_ref for occurrence, _, _ in occurrence_profiles
        ),
        settlement_round=1,
        target_selection=SwirlEmissionSelection(
            selection_ref=f"{anchor_occurrence.occurrence_ref}:emission_selection",
            anchor_subject_ref=request.subject_ref,
        ),
        source_ref=request.source_ref,
        captured_source_observation=observation,
        impacts=impacts,
    )


def _request_for_candidate(
    request: ReactionEvaluationRequest,
    candidate: _SwirlCandidate,
    incoming_amount: AuraAmount,
    order: int,
) -> ReactionEvaluationRequest:
    component = request.observed_aura.component_for(candidate.aura_kind)
    if component is None:
        raise ValueError("扩散候选缺少对应 Aura")
    trigger_context = request.trigger_context
    if trigger_context is None or trigger_context.elemental_application is None:
        raise ValueError("扩散候选需要元素施加 Trigger Context")
    return replace(
        request,
        order=order,
        incoming_amount=incoming_amount,
        observed_aura=AuraView(request.subject_ref, (component,)),
        observed_frozen_state=(
            request.observed_frozen_state if candidate.aura_kind is AuraKind.FROZEN else None
        ),
        trigger_context=replace(
            trigger_context,
            elemental_application=replace(
                trigger_context.elemental_application,
                amount=incoming_amount,
            ),
        ),
    )


def _transition_for(
    request: ReactionEvaluationRequest,
    candidate: _SwirlCandidate,
    aura_before: AuraAmount,
) -> ElementalTransitionEffect:
    incoming_consumed = request.incoming_amount.minimum(aura_before * AuraAmount(2))
    aura_consumed = incoming_consumed / AuraAmount(2)
    return ElementalTransitionEffect(
        aura_kind=candidate.aura_kind,
        incoming_before=request.incoming_amount,
        incoming_consumed=incoming_consumed,
        incoming_remaining=request.incoming_amount - incoming_consumed,
        aura_before=aura_before,
        aura_consumed=aura_consumed,
        aura_remaining=aura_before - aura_consumed,
    )


def _decision_step(step_ordinal: int, occurrence: ReactionOccurrence) -> ReactionDecisionStep:
    return ReactionDecisionStep(
        step_ordinal,
        (occurrence.direction_key,),
        (occurrence.transition,),
        (),
        (occurrence,),
    )


def swirl_definition() -> ReactionDefinition:
    profiles = tuple(
        TransformativeReactionProfile(
            profile_key=f"reaction_profile.swirl.{candidate.direction_key}",
            reaction_key=SWIRL_REACTION_KEY,
            direction_key=candidate.direction_key,
            trigger_element=Element.ANEMO,
            damage_profile_key=SWIRL_DAMAGE_PROFILE_KEY,
            damage_element=candidate.damage_element,
            base_multiplier=SWIRL_BASE_MULTIPLIER,
            gate_definition_key=candidate.gate_definition_key,
            damage_kind_key=candidate.damage_kind_key,
        )
        for candidate in _SINGLE_AURA_CANDIDATES
    )
    return ReactionDefinition(
        reaction_key=SWIRL_REACTION_KEY,
        handler_key=SWIRL_HANDLER_KEY,
        trigger_signatures=tuple(
            ReactionTriggerSignature(
                Element.ANEMO,
                candidate.aura_kind,
                candidate.direction_key,
            )
            for candidate in _SINGLE_AURA_CANDIDATES
        ),
        profiles=profiles,
        rule=SwirlRule(),
    )


def swirl_aura_application_profile() -> AuraApplicationProfile:
    """扩散派生 Aura 使用的生产常规附着 Profile。"""

    return AuraApplicationProfile(
        profile_key=SWIRL_AURA_APPLICATION_PROFILE_KEY,
        decay_profile_policy=AuraDecayProfilePolicy.REGULAR_FROM_RAW_AMOUNT,
    )


def swirl_damage_profile() -> DamageProfile:
    """普通扩散使用的生产剧变 Damage Profile。"""

    return DamageProfile(
        formula_key=FORMULA_KEY_TRANSFORMATIVE_REACTION,
        main_attack_tags=frozenset({SWIRL_REACTION_KEY}),
        reaction_capabilities=frozenset({DamageReactionCapability.SECONDARY_AMPLIFYING}),
    )


def swirl_gate_definitions() -> tuple[ReactionDamageGateDefinition, ...]:
    """普通扩散四种输出元素各自使用的生产 Damage Gate。"""

    return (
        ReactionDamageGateDefinition(
            PYRO_SWIRL_GATE_DEFINITION_KEY,
            "reaction_damage.swirl.pyro",
            30,
            2,
        ),
        ReactionDamageGateDefinition(
            HYDRO_SWIRL_GATE_DEFINITION_KEY,
            "reaction_damage.swirl.hydro",
            30,
            2,
        ),
        ReactionDamageGateDefinition(
            ELECTRO_SWIRL_GATE_DEFINITION_KEY,
            "reaction_damage.swirl.electro",
            30,
            2,
        ),
        ReactionDamageGateDefinition(
            CRYO_SWIRL_GATE_DEFINITION_KEY,
            "reaction_damage.swirl.cryo",
            30,
            2,
        ),
    )


class SwirlGeneratedImpactDamageInputAdapter:
    """将扩散范围派生 Impact 映射为捕获式剧变公式输入。"""

    def transformative_input(
        self,
        *,
        batch: ReactionGeneratedImpactBatch,
        impact: ReactionGeneratedImpact,
    ) -> TransformativeReactionInput:
        component = impact.damage_component
        if component is None:
            raise ValueError("水扩散 emission 没有 Damage 组件")
        if component.main_attack_tag != SWIRL_REACTION_KEY:
            raise ValueError("扩散 Damage 组件必须使用普通扩散主攻击标签")
        if component.damage_profile_key != SWIRL_DAMAGE_PROFILE_KEY:
            raise ValueError("扩散 Damage 组件必须使用普通扩散 Damage Profile")
        expected = _range_damage_spec_for(impact.element)
        if expected is None:
            raise ValueError("普通扩散范围 Damage 只支持火、雷、冰输出")
        if (
            component.damage_element,
            component.gate_definition_key,
            component.damage_kind_key,
        ) != expected:
            raise ValueError("扩散 Damage 组件与派生元素不一致")
        if impact.provenance.reaction_profile_key not in _SWIRL_PROFILE_KEYS:
            raise ValueError("扩散派生 Impact 必须引用普通扩散 Profile")
        source = batch.captured_source_observation
        occurrence_ref = impact.provenance.parent_occurrence_ref
        if occurrence_ref is None:
            raise ValueError("普通扩散派生 Impact 必须具有 occurrence cause")
        return TransformativeReactionInput(
            occurrence_ref=occurrence_ref,
            reaction_profile_key=impact.provenance.reaction_profile_key,
            source_kind=source.source_kind,
            source_level=source.source_level,
            level_multiplier_table_key=source.level_multiplier_table_key,
            level_multiplier=source.level_multiplier,
            elemental_mastery=source.elemental_mastery,
            mastery_bonus=16 * source.elemental_mastery / (source.elemental_mastery + 2000),
            reaction_bonus=0.0,
            base_multiplier=SWIRL_BASE_MULTIPLIER,
        )


def _single_candidate(
    request: ReactionEvaluationRequest,
) -> tuple[_SwirlCandidate | None, AuraAmount]:
    matches = _available_candidates(request)
    if not matches:
        return None, AuraAmount.zero()
    if len(matches) != 1:
        aura_kinds = ", ".join(sorted(candidate.aura_kind.value for candidate, _ in matches))
        raise SwirlSelectionError(f"当前扩散机制只支持单 Aura；需要显式双扩散候选：{aura_kinds}")
    return matches[0]


def _available_candidates(
    request: ReactionEvaluationRequest,
) -> tuple[tuple[_SwirlCandidate, AuraAmount], ...]:
    return tuple(
        (candidate, component.current_amount)
        for candidate in _SINGLE_AURA_CANDIDATES
        if (component := request.observed_aura.component_for(candidate.aura_kind)) is not None
        and not component.current_amount.is_zero
    )


def _emitted_amount(incoming_before: AuraAmount, aura_before: AuraAmount) -> AuraAmount:
    if aura_before * AuraAmount(2) > incoming_before:
        return incoming_before * AuraAmount(5) / AuraAmount(4) + AuraAmount("0.95")
    return aura_before * AuraAmount(5) / AuraAmount(4) + AuraAmount("0.95")


def _captured_basis(
    request: ReactionEvaluationRequest,
    profile: TransformativeReactionProfile,
    group_ref: str,
) -> CapturedTransformativeScalingBasis:
    observation = request.transformative_source_observation
    assert observation is not None
    return CapturedTransformativeScalingBasis(
        basis_ref=f"{group_ref}:basis",
        captured_frame=request.frame,
        source_ref=observation.source_ref,
        source_kind=observation.source_kind,
        source_level=observation.source_level,
        elemental_mastery=observation.elemental_mastery,
        reaction_bonus=0.0,
        reaction_profile_key=profile.profile_key,
        damage_profile_key=profile.damage_profile_key,
        level_multiplier_table_key=observation.level_multiplier_table_key,
        level_multiplier=observation.level_multiplier,
        source_observation_ref=observation.source_observation_ref,
        source_owner_slot=observation.source_owner_slot,
    )


def _range_damage_component(
    profile: TransformativeReactionProfile,
    candidate: _SwirlCandidate,
) -> ReactionGeneratedImpactDamageComponent | None:
    if candidate.output_element is Element.HYDRO:
        return None
    return ReactionGeneratedImpactDamageComponent(
        main_attack_tag=SWIRL_REACTION_KEY,
        damage_profile_key=profile.damage_profile_key,
        damage_element=profile.damage_element,
        gate_definition_key=profile.gate_definition_key,
        damage_kind_key=profile.damage_kind_key,
    )


_SWIRL_PROFILE_KEYS = frozenset(
    f"reaction_profile.swirl.{candidate.direction_key}" for candidate in _SINGLE_AURA_CANDIDATES
)


def _range_damage_spec_for(
    element: Element,
) -> tuple[Element, str, str] | None:
    if element is Element.PYRO:
        return (
            Element.PYRO,
            PYRO_SWIRL_GATE_DEFINITION_KEY,
            "reaction_damage.swirl.pyro",
        )
    if element is Element.ELECTRO:
        return (
            Element.ELECTRO,
            ELECTRO_SWIRL_GATE_DEFINITION_KEY,
            "reaction_damage.swirl.electro",
        )
    if element is Element.CRYO:
        return (
            Element.CRYO,
            CRYO_SWIRL_GATE_DEFINITION_KEY,
            "reaction_damage.swirl.cryo",
        )
    return None
