from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from genshin_sim.core.elements import ElementalStateLinkRef, ElementalSubjectRef
from genshin_sim.core.systems.reaction import (
    ReactionEstablishmentGateDecision,
    ReactionEstablishmentGateDefinition,
    ReactionRuntime,
    ReactionStoreConflictError,
    ReactionStoreMutationPlan,
    create_default_reaction_bootstrap,
)
from genshin_sim.core.systems.reaction.establishment_gates import (
    ReactionEstablishmentGateMutationPlan,
    ReactionEstablishmentGateRequest,
)

TARGET_ONE = ElementalSubjectRef.target("target:one")
TARGET_TWO = ElementalSubjectRef.target("target:two")
DEFINITION = ReactionEstablishmentGateDefinition(
    "reaction_gate.test.establishment",
    window_frames=60,
    max_occurrences=1,
)


def test_establishment_gate_shares_one_target_slot_across_occurrences_and_reopens_at_boundary():
    runtime = _runtime()

    first = _prepare(runtime, frame=10, subject_ref=TARGET_ONE, occurrence_ref="occurrence:one")
    blocked = _prepare(runtime, frame=69, subject_ref=TARGET_ONE, occurrence_ref="occurrence:two")
    other_target = _prepare(
        runtime, frame=69, subject_ref=TARGET_TWO, occurrence_ref="occurrence:three"
    )
    reopened = _prepare(runtime, frame=70, subject_ref=TARGET_ONE, occurrence_ref="occurrence:four")

    assert first.decision is ReactionEstablishmentGateDecision.ALLOWED
    assert blocked.decision is ReactionEstablishmentGateDecision.ESTABLISHMENT_GATE_BLOCKED
    assert other_target.decision is ReactionEstablishmentGateDecision.ALLOWED
    assert reopened.decision is ReactionEstablishmentGateDecision.ALLOWED
    records_by_subject = {
        record.slot_key.subject_ref: record for record in runtime.establishment_gate_records
    }
    assert len(records_by_subject) == 2
    assert records_by_subject[TARGET_ONE].last_occurrence_ref == "occurrence:four"


def test_establishment_gate_uses_virtual_projection_without_blocked_write():
    runtime = _runtime()
    planner = runtime.begin_establishment_gate_batch(0, "establishment:batch")
    first = planner.prepare(
        _request(frame=0, subject_ref=TARGET_ONE, occurrence_ref="occurrence:one")
    )
    blocked = planner.prepare(
        _request(frame=0, subject_ref=TARGET_ONE, occurrence_ref="occurrence:two")
    )
    plan = planner.seal()

    runtime.commit_prevalidated_establishment_gate_plan(plan)

    assert first.decision is ReactionEstablishmentGateDecision.ALLOWED
    assert blocked.decision is ReactionEstablishmentGateDecision.ESTABLISHMENT_GATE_BLOCKED
    assert len(plan.replacement_records) == 1
    assert runtime.version == 1
    snapshot = runtime.snapshot(0).to_dict()
    records = cast(list[dict[str, object]], snapshot["establishment_gate_records"])
    assert records[0]["last_occurrence_ref"] == "occurrence:one"


def test_establishment_gate_plan_is_stale_after_another_gate_commit():
    runtime = _runtime()
    stale = runtime.begin_establishment_gate_batch(0, "establishment:stale")
    stale.prepare(_request(frame=0, subject_ref=TARGET_ONE, occurrence_ref="occurrence:stale"))

    _prepare(runtime, frame=0, subject_ref=TARGET_TWO, occurrence_ref="occurrence:winner")

    with pytest.raises(ReactionStoreConflictError, match="已经过期"):
        runtime.commit_prevalidated_establishment_gate_plan(stale.seal())


def test_establishment_gate_replacement_requires_the_current_complete_preimage():
    runtime = _runtime()
    _prepare(runtime, frame=0, subject_ref=TARGET_ONE, occurrence_ref="occurrence:original")
    record = runtime.establishment_gate_records[0]
    invalid_plan = ReactionEstablishmentGateMutationPlan(
        operation_id="establishment:missing-preimage",
        frame=0,
        expected_store_version=runtime.version,
        resolutions=(),
        expected_records=(),
        replacement_records=(
            replace(
                record,
                last_occurrence_ref="occurrence:overwritten",
                revision=record.revision + 1,
            ),
        ),
    )

    with pytest.raises(ReactionStoreConflictError, match="缺少完整前值"):
        runtime.commit_prevalidated_establishment_gate_plan(invalid_plan)

    assert runtime.establishment_gate_records[0] == record


def test_establishment_gate_requires_a_normalized_frame_for_prepare_and_commit():
    runtime = _runtime()

    with pytest.raises(ValueError, match="已经完成规范化"):
        runtime.begin_establishment_gate_batch(1, "establishment:future")

    runtime.update_frame(None, 1)
    planner = runtime.begin_establishment_gate_batch(1, "establishment:normalized")
    planner.prepare(_request(frame=1, subject_ref=TARGET_ONE, occurrence_ref="occurrence:one"))
    plan = planner.seal()
    runtime.update_frame(None, 2)

    with pytest.raises(ReactionStoreConflictError, match="尚未规范化"):
        runtime.commit_prevalidated_establishment_gate_plan(plan)


def test_composite_store_plan_commits_establishment_gate_and_state_with_one_version_increment():
    runtime = _runtime()
    state_planner = runtime.begin_state_batch(0, "establishment-state")
    state_planner.create_frozen(
        subject_ref=TARGET_ONE,
        state_link_ref=ElementalStateLinkRef("elemental-state-link:establishment"),
    )
    damage_gate_plan = runtime.begin_gate_batch(0, "establishment-empty-damage").seal()
    establishment_gate_planner = runtime.begin_establishment_gate_batch(
        0,
        "establishment-composite",
    )
    establishment_gate_planner.prepare(
        _request(frame=0, subject_ref=TARGET_ONE, occurrence_ref="occurrence:composite")
    )

    receipt = runtime.commit_prevalidated_store_mutation_plan(
        ReactionStoreMutationPlan(
            damage_gate_plan,
            state_planner.seal(),
            establishment_gate_planner.seal(),
        )
    )

    assert receipt.version == 1
    assert receipt.establishment_gate_receipt is not None
    assert runtime.frozen_state_for(TARGET_ONE) is not None
    assert runtime.establishment_gate_records[0].last_occurrence_ref == "occurrence:composite"


def _runtime() -> ReactionRuntime:
    return ReactionRuntime(
        create_default_reaction_bootstrap().reaction_registry,
        establishment_gate_definitions=(DEFINITION,),
    )


def _prepare(
    runtime: ReactionRuntime,
    *,
    frame: int,
    subject_ref: ElementalSubjectRef,
    occurrence_ref: str,
):
    if runtime.normalized_through_frame != frame:
        runtime.update_frame(None, frame)
    operation_id = f"establishment:{subject_ref.entity_id}:{frame}:{runtime.version}"
    planner = runtime.begin_establishment_gate_batch(frame, operation_id)
    resolution = planner.prepare(
        _request(frame=frame, subject_ref=subject_ref, occurrence_ref=occurrence_ref)
    )
    runtime.commit_prevalidated_establishment_gate_plan(planner.seal())
    return resolution


def _request(
    *,
    frame: int,
    subject_ref: ElementalSubjectRef,
    occurrence_ref: str,
) -> ReactionEstablishmentGateRequest:
    return ReactionEstablishmentGateRequest(
        gate_request_ref=f"request:{occurrence_ref}",
        frame=frame,
        definition=DEFINITION,
        subject_ref=subject_ref,
        occurrence_ref=occurrence_ref,
    )
