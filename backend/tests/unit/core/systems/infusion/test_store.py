from __future__ import annotations

import pytest

from genshin_sim.core.elements import Element
from genshin_sim.core.systems.infusion import (
    InfusionInstanceRef,
    InfusionMode,
    InfusionMutationPlan,
    InfusionPlanConflictError,
    InfusionStore,
    InfusionSystemError,
)
from tests.helpers.infusion import CHARACTER_2, make_definition, make_record


def test_store_add_query_and_due_boundaries():
    definition = make_definition(duration_frames=4)
    store = InfusionStore()
    first = store.add(make_record(InfusionInstanceRef(1), definition, expires_at_frame=4))
    second = store.add(
        make_record(
            InfusionInstanceRef(2),
            definition,
            character_ref=CHARACTER_2,
            created_frame=1,
            last_applied_frame=1,
            expires_at_frame=5,
        )
    )
    assert store.version == 2
    assert store.require(InfusionInstanceRef(1)) is first
    assert store.records == (first, second)
    assert store.active(0) == (first,)
    assert store.active(0, character_ref=CHARACTER_2) == ()
    assert store.active(1, character_ref=CHARACTER_2) == (second,)
    assert store.active(1, definition_key=definition.definition_key) == (first, second)
    assert store.active(1, mode=InfusionMode.INFUSION) == (first, second)
    assert store.active(1, element=Element.PYRO) == (first, second)
    assert store.due_at(4) == (first,)
    assert store.due_at(5) == (first, second)

    with pytest.raises(InfusionSystemError, match="重复"):
        store.add(first)
    with pytest.raises(InfusionSystemError, match="不存在"):
        store.require(InfusionInstanceRef(99))


def test_store_validate_rejects_stale_or_duplicate_plans():
    definition = make_definition()
    store = InfusionStore()
    allocated = store.allocate_ref()
    assert allocated == InfusionInstanceRef(1)
    assert store.allocate_ref() == InfusionInstanceRef(2)

    record = make_record(InfusionInstanceRef(3), definition)
    store.add(record)
    plan = InfusionMutationPlan(
        operation_id="plan:ok",
        frame=0,
        expected_store_version=1,
        request_ids=("req:1",),
        expected_records=(record,),
        replacement_records=(record,),
    )
    store.validate(plan)
    store.commit_prevalidated(plan)
    assert store.version == 2

    stale = InfusionMutationPlan(
        operation_id="plan:stale",
        frame=0,
        expected_store_version=1,
        request_ids=("req:2",),
    )
    with pytest.raises(InfusionPlanConflictError, match="版本冲突"):
        store.validate(stale)

    duplicate = InfusionMutationPlan(
        operation_id="plan:ok",
        frame=0,
        expected_store_version=2,
        request_ids=("req:3",),
    )
    with pytest.raises(InfusionPlanConflictError, match="已提交"):
        store.validate(duplicate)

    reused_request = InfusionMutationPlan(
        operation_id="plan:new",
        frame=0,
        expected_store_version=2,
        request_ids=("req:1",),
    )
    with pytest.raises(InfusionPlanConflictError, match="request_id"):
        store.validate(reused_request)


def test_store_commit_requires_expected_prevalue():
    definition = make_definition()
    store = InfusionStore()
    record = make_record(InfusionInstanceRef(1), definition)
    store.add(record)
    replaced = make_record(
        InfusionInstanceRef(1),
        definition,
        created_frame=1,
        last_applied_frame=1,
        expires_at_frame=11,
    )
    bad = InfusionMutationPlan(
        operation_id="plan:bad",
        frame=1,
        expected_store_version=1,
        request_ids=("req:1",),
        replacement_records=(replaced,),
    )
    with pytest.raises(InfusionPlanConflictError, match="缺少完整前值"):
        store.validate(bad)
    assert store.version == 1

    good = InfusionMutationPlan(
        operation_id="plan:good",
        frame=1,
        expected_store_version=1,
        request_ids=("req:2",),
        expected_records=(record,),
        replacement_records=(record,),
    )
    store.validate(good)
    store.commit_prevalidated(good)
    assert store.version == 2
