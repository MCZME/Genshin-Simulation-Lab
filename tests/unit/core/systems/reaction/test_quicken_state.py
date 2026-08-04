"""QuickenState 与三类状态计划意图的纯 Reaction 行为测试。"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from genshin_sim.core.elements import (
    ElementalSourceRef,
    ElementalStateLinkRef,
    ElementalSubjectRef,
)
from genshin_sim.core.events import EventType, GameEvent
from genshin_sim.core.simulation import SimulationContext
from genshin_sim.core.systems.reaction import (
    QuickenState,
    QuickenStateCoverageIntent,
    QuickenStateEstablishmentIntent,
    QuickenStateTerminationIntent,
    QuickenStateTerminationReason,
    ReactionRegistry,
    ReactionRuntime,
    ReactionStateInstanceRef,
    ReactionStateSlot,
    ReactionStateSlotKey,
    create_default_reaction_bootstrap,
)

SOURCE = ElementalSourceRef("character:slot_1")
TARGET = ElementalSubjectRef.target("target:target_1")
LINK = ElementalStateLinkRef("elemental-state-link:quicken")
_OCCURRENCE = "interaction:quicken:occurrence:0"


def _registry() -> ReactionRegistry:
    return create_default_reaction_bootstrap().reaction_registry


def test_quicken_state_create_with_default_last_update_is_deterministic() -> None:
    runtime = ReactionRuntime(_registry())
    planner = runtime.begin_state_batch(0, "quicken-create")
    created = planner.create_quicken(
        subject_ref=TARGET,
        quicken_aura_link_ref=LINK,
        created_by_occurrence_ref=_OCCURRENCE,
    )
    runtime.commit_prevalidated_state_plan(planner.seal())

    assert isinstance(created, QuickenState)
    assert created.slot_key == ReactionStateSlotKey(TARGET, ReactionStateSlot.QUICKEN)
    assert created.created_by_occurrence_ref == _OCCURRENCE
    assert created.last_updated_by_occurrence_ref == _OCCURRENCE
    assert created.created_frame == 0
    assert created.revision == 1
    assert created.next_required_frame is None
    assert runtime.quicken_state_for(TARGET) == created
    # QuickenState 没有独立 next_required_frame，不延长仿真
    assert runtime.next_required_frame() is None
    snapshot = cast(list[dict[str, object]], runtime.snapshot(0).to_dict()["state_records"])
    assert snapshot == [
        {
            "slot": "quicken",
            "scope_key": "shared",
            "subject": {"kind": "target", "entity_id": "target:target_1"},
            "instance_ref": created.instance_ref.value,
            "next_required_frame": None,
            "quicken_aura_link_ref": LINK.link_key,
            "created_frame": 0,
            "created_by_occurrence_ref": _OCCURRENCE,
            "last_updated_by_occurrence_ref": _OCCURRENCE,
            "revision": 1,
        }
    ]


def test_quicken_state_does_not_duplicate_create_and_planner_reads_working_view() -> None:
    runtime = ReactionRuntime(_registry())
    planner = runtime.begin_state_batch(0, "quicken-first")
    planner.create_quicken(
        subject_ref=TARGET,
        quicken_aura_link_ref=LINK,
        created_by_occurrence_ref=_OCCURRENCE,
    )
    with pytest.raises(ValueError, match="完整替换"):
        planner.create_quicken(
            subject_ref=TARGET,
            quicken_aura_link_ref=LINK,
            created_by_occurrence_ref=_OCCURRENCE,
        )
    assert planner.quicken_for(TARGET) is not None


def test_quicken_state_coverage_preserves_identity_and_requires_revision_increment() -> None:
    runtime = ReactionRuntime(_registry())
    create = runtime.begin_state_batch(0, "quicken-create")
    created = create.create_quicken(
        subject_ref=TARGET,
        quicken_aura_link_ref=LINK,
        created_by_occurrence_ref=_OCCURRENCE,
    )
    runtime.commit_prevalidated_state_plan(create.seal())

    coverage_occurrence = "interaction:quicken:occurrence:1"
    refresh = runtime.begin_state_batch(0, "quicken-coverage")
    refreshed = refresh.replace_quicken(
        replace(
            created,
            last_updated_by_occurrence_ref=coverage_occurrence,
            revision=created.revision + 1,
        )
    )
    runtime.commit_prevalidated_state_plan(refresh.seal())

    assert refreshed.instance_ref == created.instance_ref
    assert refreshed.quicken_aura_link_ref == created.quicken_aura_link_ref
    assert refreshed.created_by_occurrence_ref == created.created_by_occurrence_ref
    assert refreshed.created_frame == created.created_frame
    assert refreshed.last_updated_by_occurrence_ref == coverage_occurrence
    assert refreshed.revision == 2

    bad = runtime.begin_state_batch(0, "quicken-bad-coverage")
    with pytest.raises(ValueError, match="必须递增 revision"):
        bad.replace_quicken(
            replace(
                refreshed,
                last_updated_by_occurrence_ref="interaction:quicken:occurrence:2",
            )
        )
    # 修改主体会让 slot_key 变化，planner 在按 slot 查找前值时即发现不存在活动记录。
    with pytest.raises(ValueError, match="不存在可替换的 QuickenState"):
        bad.replace_quicken(
            replace(
                refreshed,
                subject_ref=ElementalSubjectRef.target("target:other"),
                revision=refreshed.revision + 1,
            )
        )


def test_quicken_state_replace_rejects_identity_loss() -> None:
    runtime = ReactionRuntime(_registry())
    create = runtime.begin_state_batch(0, "quicken-create")
    created = create.create_quicken(
        subject_ref=TARGET,
        quicken_aura_link_ref=LINK,
        created_by_occurrence_ref=_OCCURRENCE,
    )
    runtime.commit_prevalidated_state_plan(create.seal())

    other_link = ElementalStateLinkRef("elemental-state-link:other")
    wrong_link = runtime.begin_state_batch(0, "quicken-wrong-link")
    with pytest.raises(ValueError, match="保留激元素 Link"):
        wrong_link.replace_quicken(
            replace(
                created,
                quicken_aura_link_ref=other_link,
                revision=created.revision + 1,
            )
        )


def test_quicken_state_remove_requires_existing_instance() -> None:
    runtime = ReactionRuntime(_registry())
    planner = runtime.begin_state_batch(0, "quicken-create")
    created = planner.create_quicken(
        subject_ref=TARGET,
        quicken_aura_link_ref=LINK,
        created_by_occurrence_ref=_OCCURRENCE,
    )
    runtime.commit_prevalidated_state_plan(planner.seal())

    remove = runtime.begin_state_batch(0, "quicken-remove")
    removed = remove.remove_quicken(subject_ref=TARGET)
    runtime.commit_prevalidated_state_plan(remove.seal())

    assert removed == created
    assert runtime.quicken_state_for(TARGET) is None

    stale = runtime.begin_state_batch(0, "quicken-stale-remove")
    with pytest.raises(ValueError, match="不存在可移除的 QuickenState"):
        stale.remove_quicken(subject_ref=TARGET)


def test_quicken_state_remove_validates_expected_instance_ref() -> None:
    runtime = ReactionRuntime(_registry())
    planner = runtime.begin_state_batch(0, "quicken-create")
    planner.create_quicken(
        subject_ref=TARGET,
        quicken_aura_link_ref=LINK,
        created_by_occurrence_ref=_OCCURRENCE,
    )
    runtime.commit_prevalidated_state_plan(planner.seal())

    wrong_ref = ReactionStateInstanceRef("reaction-state-instance:other")
    remove = runtime.begin_state_batch(0, "quicken-remove-mismatch")
    with pytest.raises(ValueError, match="实例前值冲突"):
        remove.remove_quicken if False else remove.remove_quicken(
            subject_ref=TARGET, expected_instance_ref=wrong_ref
        )


def test_quicken_state_publishes_reaction_state_changed_fact() -> None:
    context = SimulationContext()
    runtime = ReactionRuntime(_registry())
    planner = runtime.begin_state_batch(0, "quicken-event")
    planner.create_quicken(
        subject_ref=TARGET,
        quicken_aura_link_ref=LINK,
        created_by_occurrence_ref=_OCCURRENCE,
    )
    receipt = runtime.commit_prevalidated_state_plan(planner.seal())
    events: list[GameEvent] = []
    context.events.subscribe(EventType.REACTION_STATE_CHANGED, events.append)

    runtime.publish_committed_state_facts(context, receipt)

    assert [event.event_type for event in events] == [EventType.REACTION_STATE_CHANGED]
    payload = cast(dict[str, object], events[0].payload.to_dict()["after"])
    assert payload["quicken_aura_link_ref"] == LINK.link_key
    assert payload["last_updated_by_occurrence_ref"] == _OCCURRENCE
    assert payload["revision"] == 1


def test_quicken_state_establishment_intent_validates_payload() -> None:
    intent = QuickenStateEstablishmentIntent(
        intent_ref="intent:quicken:establish",
        subject_ref=TARGET,
        occurrence_ref=_OCCURRENCE,
        frame=0,
        quicken_aura_link_ref=LINK,
    )
    assert intent.frame == 0
    with pytest.raises(ValueError, match="quicken_aura_link_ref 必须是 ElementalStateLinkRef"):
        QuickenStateEstablishmentIntent(  # type: ignore[arg-type]
            intent_ref="intent:quicken:establish",
            subject_ref=TARGET,
            occurrence_ref=_OCCURRENCE,
            frame=0,
            quicken_aura_link_ref="not-a-link",  # type: ignore[arg-type]
        )


def test_quicken_state_coverage_intent_validates_revision_and_link() -> None:
    intent = QuickenStateCoverageIntent(
        intent_ref="intent:quicken:coverage",
        subject_ref=TARGET,
        occurrence_ref="interaction:quicken:occurrence:1",
        frame=0,
        expected_state_instance_ref=ReactionStateInstanceRef("reaction-state-instance:1"),
        expected_state_revision=1,
        quicken_aura_link_ref=LINK,
    )
    assert intent.expected_state_revision == 1
    with pytest.raises(ValueError, match="expected_state_revision 必须是正整数"):
        QuickenStateCoverageIntent(
            intent_ref="intent:quicken:coverage",
            subject_ref=TARGET,
            occurrence_ref="interaction:quicken:occurrence:1",
            frame=0,
            expected_state_instance_ref=ReactionStateInstanceRef("reaction-state-instance:1"),
            expected_state_revision=0,
            quicken_aura_link_ref=LINK,
        )
    with pytest.raises(ValueError, match="quicken_aura_link_ref 必须是 ElementalStateLinkRef"):
        QuickenStateCoverageIntent(  # type: ignore[arg-type]
            intent_ref="intent:quicken:coverage",
            subject_ref=TARGET,
            occurrence_ref="interaction:quicken:occurrence:1",
            frame=0,
            expected_state_instance_ref=ReactionStateInstanceRef("reaction-state-instance:1"),
            expected_state_revision=1,
            quicken_aura_link_ref="not-a-link",  # type: ignore[arg-type]
        )


def test_quicken_state_termination_intent_constraints() -> None:
    intent = QuickenStateTerminationIntent(
        intent_ref="intent:quicken:terminate",
        subject_ref=TARGET,
        frame=5,
        expected_state_instance_ref=ReactionStateInstanceRef("reaction-state-instance:1"),
        expected_state_revision=1,
        reason=QuickenStateTerminationReason.QUICKEN_DEPLETED,
    )
    assert intent.reason is QuickenStateTerminationReason.QUICKEN_DEPLETED
    with pytest.raises(ValueError, match="reason 必须是 QuickenStateTerminationReason"):
        QuickenStateTerminationIntent(  # type: ignore[arg-type]
            intent_ref="intent:quicken:terminate",
            subject_ref=TARGET,
            frame=5,
            expected_state_instance_ref=ReactionStateInstanceRef("reaction-state-instance:1"),
            expected_state_revision=1,
            reason="depleted",  # type: ignore[arg-type]
        )
