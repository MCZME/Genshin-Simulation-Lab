from __future__ import annotations

from typing import cast

import pytest

from genshin_sim.core.coordination.elemental_reaction import (
    ElementalInteractionBatchRecord,
    ElementalSettlementCoordinator,
    ElementalSettlementQueueError,
    ElementalSettlementRoundLimitError,
    ElementalSettlementWork,
    ElementalSettlementWorkQueue,
    NoAuraElectroHydroCoexistencePolicy,
    SimultaneousElementApplicationBatch,
    SimultaneousElementApplicationPolicyError,
    SimultaneousElementApplicationPolicyRegistry,
    SimultaneousElementApplicationPolicyResult,
    SimultaneousElementApplicationStrategy,
)
from genshin_sim.core.elements import (
    AuraAmount,
    Element,
    ElementalSourceRef,
    ElementalSubjectRef,
    TransformativeReactionSourceKind,
)
from genshin_sim.core.systems.aura import AuraView
from genshin_sim.core.systems.reaction import (
    CapturedTransformativeScalingBasis,
    CurrentSubjectSelection,
    OccurrenceCause,
    ReactionGeneratedImpact,
    ReactionGeneratedImpactBatch,
    ReactionGeneratedImpactDamageComponent,
    ReactionGeneratedImpactProvenance,
    SwirlEmissionSelection,
    TransformativeSourceObservation,
)

ROOT_WORK_ID = "root:swirl"
SOURCE = ElementalSourceRef("character:slot_1", ROOT_WORK_ID)
TARGET = ElementalSubjectRef.target("target:target_1")


def test_generated_impact_batch_keeps_positive_application_and_optional_damage_separate():
    batch = _generated_batch()

    assert tuple(item.element for item in batch.impacts) == (Element.PYRO, Element.HYDRO)
    assert batch.impacts[0].damage_component is not None
    assert batch.impacts[1].damage_component is None
    assert batch.impacts[1].elemental_amount == AuraAmount("39/20")
    assert isinstance(batch.target_selection, SwirlEmissionSelection)
    assert batch.target_selection.exclude_anchor
    assert batch.target_selection.radius == 6.0


def test_generated_impact_batch_rejects_unknown_parent_occurrence():
    impact = _impact(
        ref="impact:orphan",
        order=0,
        element=Element.PYRO,
        parent_occurrence_ref="occurrence:other",
    )

    with pytest.raises(ValueError, match="provenance 必须引用父 occurrence"):
        ReactionGeneratedImpactBatch(
            emission_batch_ref="emission:orphan",
            parent_root_work_ref=ROOT_WORK_ID,
            parent_occurrence_refs=("occurrence:swirl",),
            settlement_round=1,
            target_selection=SwirlEmissionSelection("selection:orphan", TARGET),
            source_ref=SOURCE,
            captured_source_observation=_source_observation(),
            impacts=(impact,),
        )


def test_generated_impact_batch_derives_occurrence_projection_from_causes():
    impact = _impact(
        ref="impact:projected",
        order=0,
        element=Element.PYRO,
        parent_occurrence_ref="occurrence:projected",
    )
    batch = ReactionGeneratedImpactBatch(
        emission_batch_ref="emission:projected",
        parent_root_work_ref=ROOT_WORK_ID,
        parent_occurrence_refs=(),
        settlement_round=1,
        target_selection=SwirlEmissionSelection("selection:projected", TARGET),
        source_ref=SOURCE,
        captured_source_observation=_source_observation(),
        impacts=(impact,),
        causes=(OccurrenceCause("occurrence:projected"),),
    )

    assert batch.parent_occurrence_refs == ("occurrence:projected",)


def test_generated_impact_batch_accepts_captured_basis_for_scheduled_application():
    impact = _impact(
        ref="impact:captured-basis",
        order=0,
        element=Element.PYRO,
        parent_occurrence_ref="occurrence:captured-basis",
    )
    basis = CapturedTransformativeScalingBasis(
        basis_ref="basis:periodic-pyro",
        captured_frame=0,
        source_ref=SOURCE,
        source_kind=TransformativeReactionSourceKind.CHARACTER,
        source_level=90,
        elemental_mastery=0.0,
        reaction_bonus=0.0,
        reaction_profile_key="reaction_profile:periodic-pyro",
        damage_profile_key="damage_profile:periodic-pyro",
        level_multiplier_table_key="character",
        level_multiplier=1446.853,
        source_observation_ref="observation:periodic-pyro",
        source_owner_slot=1,
    )
    batch = ReactionGeneratedImpactBatch(
        emission_batch_ref="emission:captured-basis",
        parent_root_work_ref=ROOT_WORK_ID,
        parent_occurrence_refs=("occurrence:captured-basis",),
        settlement_round=1,
        target_selection=CurrentSubjectSelection("selection:captured-basis", TARGET),
        source_ref=SOURCE,
        captured_source_observation=basis,
        impacts=(impact,),
    )

    assert batch.captured_source_observation == basis


def test_settlement_queue_freezes_current_round_and_requires_strict_child_rounds():
    queue = ElementalSettlementWorkQueue(ROOT_WORK_ID, maximum_settlement_round=3)
    first = ElementalSettlementWork(
        work_id="work:round:1",
        root_work_id=ROOT_WORK_ID,
        parent_work_id=ROOT_WORK_ID,
        frame=0,
        settlement_round=1,
        payload=_generated_batch(),
    )
    queue.enqueue(first)

    assert queue.freeze_next_round() == (first,)
    with pytest.raises(ElementalSettlementQueueError, match="当前 settlement_round 已冻结"):
        queue.enqueue(
            ElementalSettlementWork(
                work_id="work:round:1:late",
                root_work_id=ROOT_WORK_ID,
                parent_work_id=ROOT_WORK_ID,
                frame=0,
                settlement_round=1,
                payload=_generated_batch(),
            )
        )

    second = ElementalSettlementWork(
        work_id="work:round:2",
        root_work_id=ROOT_WORK_ID,
        parent_work_id=first.work_id,
        frame=0,
        settlement_round=2,
        payload=_generated_batch(),
    )
    queue.enqueue(second)
    queue.complete_active_round()

    assert queue.freeze_next_round() == (second,)
    queue.complete_active_round()
    assert queue.is_empty


def test_settlement_queue_rejects_work_beyond_explicit_round_limit():
    queue = ElementalSettlementWorkQueue(ROOT_WORK_ID, maximum_settlement_round=1)

    with pytest.raises(ElementalSettlementRoundLimitError) as error:
        queue.enqueue(
            ElementalSettlementWork(
                work_id="work:round:2",
                root_work_id=ROOT_WORK_ID,
                parent_work_id=ROOT_WORK_ID,
                frame=0,
                settlement_round=2,
                payload=_generated_batch(),
            )
        )

    assert error.value.root_work_id == ROOT_WORK_ID
    assert error.value.attempted_round == 2
    assert error.value.maximum_settlement_round == 1


def test_child_generated_batch_uses_the_next_round_instead_of_its_root_round_declaration():
    queue = ElementalSettlementWorkQueue(ROOT_WORK_ID, maximum_settlement_round=3)
    parent = ElementalSettlementWork(
        work_id="work:round:1",
        root_work_id=ROOT_WORK_ID,
        parent_work_id=ROOT_WORK_ID,
        frame=0,
        settlement_round=1,
        payload=_generated_batch(),
    )
    queue.enqueue(parent)
    assert queue.freeze_next_round() == (parent,)
    record = ElementalInteractionBatchRecord(
        batch_id="batch:round:1",
        root_work_id=ROOT_WORK_ID,
        frame=0,
        settlement_round=1,
        work_ids=(parent.work_id,),
        icd_request_ids=(),
        aura_transition_interaction_ids=(),
        reaction_occurrence_refs=(),
        damage_request_ids=(),
        generated_impact_batches=(_generated_batch(),),
    )

    ElementalSettlementCoordinator._enqueue_record_follow_up_work(  # noqa: SLF001
        queue,
        record,
        parent,
        record,
    )
    queue.complete_active_round()

    (child,) = queue.freeze_next_round()
    assert child.settlement_round == 2
    assert ":round:2:" in child.work_id


def test_unregistered_simultaneous_application_fails_with_stable_audit_payload():
    generated = _generated_batch().impacts
    batch = SimultaneousElementApplicationBatch(
        batch_ref="simultaneous:target:1",
        frame=0,
        settlement_round=1,
        root_work_id=ROOT_WORK_ID,
        subject_ref=TARGET,
        emission_batch_ref="emission:swirl",
        source_ref=SOURCE,
        observed_aura=AuraView(TARGET),
        applications=generated,
    )

    with pytest.raises(SimultaneousElementApplicationPolicyError) as error:
        SimultaneousElementApplicationPolicyRegistry().resolve(batch)

    payload = error.value.to_dict()
    assert payload["reason"] == "no_matching_policy"
    assert payload["root_work_id"] == ROOT_WORK_ID
    assert payload["subject_ref"] == {"kind": "target", "entity_id": "target:target_1"}
    assert payload["candidate_policy_keys"] == ()
    assert payload["source_ref"] == SOURCE.to_dict()
    applications = cast(tuple[dict[str, object], ...], payload["applications"])
    assert tuple(item["element"] for item in applications) == ("pyro", "hydro")


def test_simultaneous_policy_returns_explicit_commutative_result():
    batch = SimultaneousElementApplicationBatch(
        batch_ref="simultaneous:target:1",
        frame=0,
        settlement_round=1,
        root_work_id=ROOT_WORK_ID,
        subject_ref=TARGET,
        emission_batch_ref="emission:swirl",
        source_ref=SOURCE,
        observed_aura=AuraView(TARGET),
        applications=_generated_batch().impacts,
    )
    registry = SimultaneousElementApplicationPolicyRegistry((_CommutativePolicy(),))

    result = registry.resolve(batch)

    assert result.policy_key == "simultaneous.test.commutative"
    assert result.strategy is SimultaneousElementApplicationStrategy.SUPPORTED_COMMUTATIVE


def test_no_aura_electro_hydro_policy_supports_coexistence_without_an_ordered_reaction():
    batch = SimultaneousElementApplicationBatch(
        batch_ref="simultaneous:target:electro-hydro",
        frame=0,
        settlement_round=1,
        root_work_id=ROOT_WORK_ID,
        subject_ref=TARGET,
        emission_batch_ref="emission:swirl",
        source_ref=SOURCE,
        observed_aura=AuraView(TARGET),
        applications=(
            _impact(
                ref="impact:electro",
                order=0,
                element=Element.ELECTRO,
                parent_occurrence_ref="occurrence:swirl",
            ),
            _impact(
                ref="impact:hydro",
                order=1,
                element=Element.HYDRO,
                parent_occurrence_ref="occurrence:swirl",
            ),
        ),
    )

    result = SimultaneousElementApplicationPolicyRegistry(
        (NoAuraElectroHydroCoexistencePolicy(),)
    ).resolve(batch)

    assert result.policy_key == NoAuraElectroHydroCoexistencePolicy.policy_key
    assert result.strategy is SimultaneousElementApplicationStrategy.SUPPORTED_COMMUTATIVE


def test_no_aura_electro_hydro_policy_rejects_duplicate_element_applications():
    batch = SimultaneousElementApplicationBatch(
        batch_ref="simultaneous:target:duplicate-hydro",
        frame=0,
        settlement_round=1,
        root_work_id=ROOT_WORK_ID,
        subject_ref=TARGET,
        emission_batch_ref="emission:swirl",
        source_ref=SOURCE,
        observed_aura=AuraView(TARGET),
        applications=(
            _impact(
                ref="impact:electro",
                order=0,
                element=Element.ELECTRO,
                parent_occurrence_ref="occurrence:swirl",
            ),
            _impact(
                ref="impact:hydro:one",
                order=1,
                element=Element.HYDRO,
                parent_occurrence_ref="occurrence:swirl",
            ),
            _impact(
                ref="impact:hydro:two",
                order=2,
                element=Element.HYDRO,
                parent_occurrence_ref="occurrence:swirl",
            ),
        ),
    )

    with pytest.raises(SimultaneousElementApplicationPolicyError, match="no_matching_policy"):
        SimultaneousElementApplicationPolicyRegistry(
            (NoAuraElectroHydroCoexistencePolicy(),)
        ).resolve(batch)


def test_simultaneous_policy_cannot_return_another_registered_policy_key():
    batch = SimultaneousElementApplicationBatch(
        batch_ref="simultaneous:target:1",
        frame=0,
        settlement_round=1,
        root_work_id=ROOT_WORK_ID,
        subject_ref=TARGET,
        emission_batch_ref="emission:swirl",
        source_ref=SOURCE,
        observed_aura=AuraView(TARGET),
        applications=_generated_batch().impacts,
    )
    registry = SimultaneousElementApplicationPolicyRegistry((_MismatchedPolicy(), _PassivePolicy()))

    with pytest.raises(ValueError, match="必须属于当前评估策略"):
        registry.resolve(batch)


def _generated_batch() -> ReactionGeneratedImpactBatch:
    return ReactionGeneratedImpactBatch(
        emission_batch_ref="emission:swirl",
        parent_root_work_ref=ROOT_WORK_ID,
        parent_occurrence_refs=("occurrence:swirl",),
        settlement_round=1,
        target_selection=SwirlEmissionSelection("selection:swirl", TARGET),
        source_ref=SOURCE,
        captured_source_observation=_source_observation(),
        impacts=(
            _impact(
                ref="impact:hydro",
                order=1,
                element=Element.HYDRO,
                parent_occurrence_ref="occurrence:swirl",
            ),
            _impact(
                ref="impact:pyro",
                order=0,
                element=Element.PYRO,
                parent_occurrence_ref="occurrence:swirl",
                has_damage=True,
            ),
        ),
    )


def _impact(
    *,
    ref: str,
    order: int,
    element: Element,
    parent_occurrence_ref: str,
    has_damage: bool = False,
) -> ReactionGeneratedImpact:
    return ReactionGeneratedImpact(
        generated_impact_ref=ref,
        emission_order=order,
        element=element,
        elemental_amount=AuraAmount("39/20"),
        aura_application_profile_key="aura_application_profile.swirl.pending_review",
        provenance=ReactionGeneratedImpactProvenance(
            provenance_ref=f"provenance:{ref}",
            parent_occurrence_ref=parent_occurrence_ref,
            reaction_profile_key=f"reaction_profile:{ref}",
        ),
        damage_component=(
            ReactionGeneratedImpactDamageComponent(
                main_attack_tag="reaction.swirl",
                damage_profile_key="damage_profile.reaction.swirl",
                damage_element=Element.PYRO,
                gate_definition_key="reaction_gate.swirl.damage",
                damage_kind_key="reaction_damage.swirl.pyro",
            )
            if has_damage
            else None
        ),
    )


def _source_observation() -> TransformativeSourceObservation:
    return TransformativeSourceObservation(
        source_ref=SOURCE,
        source_kind=TransformativeReactionSourceKind.CHARACTER,
        source_level=90,
        elemental_mastery=0.0,
        level_multiplier_table_key="character",
        level_multiplier=1446.853,
        source_observation_ref="source-observation:swirl",
        source_owner_slot=1,
    )


class _CommutativePolicy:
    policy_key = "simultaneous.test.commutative"

    def evaluate(
        self,
        batch: SimultaneousElementApplicationBatch,
    ) -> SimultaneousElementApplicationPolicyResult:
        del batch
        return SimultaneousElementApplicationPolicyResult(
            policy_key=self.policy_key,
            strategy=SimultaneousElementApplicationStrategy.SUPPORTED_COMMUTATIVE,
        )


class _MismatchedPolicy:
    policy_key = "simultaneous.test.mismatched"

    def evaluate(
        self,
        batch: SimultaneousElementApplicationBatch,
    ) -> SimultaneousElementApplicationPolicyResult:
        del batch
        return SimultaneousElementApplicationPolicyResult(
            policy_key=_PassivePolicy.policy_key,
            strategy=SimultaneousElementApplicationStrategy.SUPPORTED_COMMUTATIVE,
        )


class _PassivePolicy:
    policy_key = "simultaneous.test.passive"

    def evaluate(
        self,
        batch: SimultaneousElementApplicationBatch,
    ) -> SimultaneousElementApplicationPolicyResult | None:
        del batch
        return None
